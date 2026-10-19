"""仅在管理 Mac 使用已有受限中间 CA；口令只在入口进程内存中存在。"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[5]
PUBLIC = ROOT / 'ops/00-preparation/pki/public'
PRIVATE = Path.home() / '.cnpl-secrets/gateway/lab-primary'
PROFILES = {
    'primary': ['demo.svc.internal.egon.top', 'grpc-demo.svc.internal.egon.top'],
    'foreign': ['demo.svc.internal.egon.top', 'grpc-demo.svc.internal.egon.top'],
    'compare': ['demo.svc.internal.egon.top'],
    'backend': ['backend.svc.internal.egon.top'],
}


def require(value, message):
    if not value:
        raise ValueError(message)


def fingerprint(cert):
    return cert.fingerprint(hashes.SHA256()).hex()


def authority():
    base = Path(os.environ.get('CNPL_PKI_DIR', str(Path.home() / 'cnpl-pki'))).resolve()
    root = PUBLIC / 'cnpl-lab-root-ca.crt'
    issuer = PUBLIC / 'cnpl-lab-issuing-ca.crt'
    require((base / 'intermediate/intermediate.key').is_file(), '缺少现有中间 CA 私钥')
    require(issuer.read_bytes() == (base / 'intermediate/intermediate.crt').read_bytes(), '中间 CA 与仓库公开信任证书不同')
    reply = subprocess.run(['openssl', 'verify', '-CAfile', str(root), str(issuer)], capture_output=True, text=True, timeout=10)
    require(reply.returncode == 0, '已有中间 CA 不能被公开根证书验证')
    cert = x509.load_pem_x509_certificate(issuer.read_bytes())
    require(cert.not_valid_after_utc > datetime.now(timezone.utc) + timedelta(days=15), '中间 CA 有效期不足')
    for names in PROFILES.values():
        require(all(name.endswith('.internal.egon.top') for name in names), '证书名称越过既有中间 CA 名称约束')
    return {'private_dir': base, 'root': root, 'issuer': issuer, 'certificate': cert}


def describe(cert_path, key_path, names, auth):
    cert = x509.load_pem_x509_certificate(Path(cert_path).read_bytes())
    key = serialization.load_pem_private_key(Path(key_path).read_bytes(), password=None)
    public = lambda value: value.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    require(public(key.public_key()) == public(cert.public_key()), '叶证书与私钥不匹配')
    require(set(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)) == set(names), '叶证书 SAN 不同')
    require(cert.not_valid_before_utc <= datetime.now(timezone.utc) < cert.not_valid_after_utc - timedelta(days=1), '叶证书尚未生效或接近过期')
    for name in names:
        reply = subprocess.run(['openssl', 'verify', '-verify_hostname', name, '-CAfile', str(auth['root']), '-untrusted', str(auth['issuer']), str(cert_path)], capture_output=True, text=True, timeout=10)
        require(reply.returncode == 0, '叶证书链、SAN 或名称约束校验失败')
    return {'certificate': str(cert_path), 'private_key': str(key_path), 'fullchain': str(Path(cert_path).with_name('fullchain.crt')), 'sha256': fingerprint(cert), 'sans': names, 'not_after': cert.not_valid_after_utc.isoformat()}


def existing(records, auth):
    path = Path(records) / 'state/tls.json'
    if not path.exists():
        return None
    saved = json.loads(path.read_text())
    require(set(saved) == set(PROFILES), '原 TLS 身份记录不完整')
    for name, names in PROFILES.items():
        item = saved[name]
        require(Path(item['private_key']).resolve().is_relative_to(PRIVATE.resolve()), 'TLS 私钥路径越过管理端私有目录')
        current = describe(item['certificate'], item['private_key'], names, auth)
        require(current['sha256'] == item['sha256'], 'TLS 公共指纹与原记录不同')
    return saved


def issue(records, context, password):
    auth = authority()
    cached = existing(records, auth)
    if cached:
        return cached
    try:
        key = serialization.load_pem_private_key((auth['private_dir'] / 'intermediate/intermediate.key').read_bytes(), password=password)
    except (ValueError, TypeError):
        raise ValueError('中间 CA 口令不正确，尚未执行任何集群变更') from None
    public = lambda value: value.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    require(public(key.public_key()) == public(auth['certificate'].public_key()), '中间 CA 密钥与当前公开证书不同')
    folder = PRIVATE / context['run']
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(folder, 0o700)
    result = {}
    for profile, names in PROFILES.items():
        directory = folder / profile
        directory.mkdir(mode=0o700, exist_ok=True)
        leaf_key = ec.generate_private_key(ec.SECP256R1())
        stamp = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'cloud-native-platform-lab'),
                x509.NameAttribute(NameOID.COMMON_NAME, names[0]),
            ]))
            .issuer_name(auth['certificate'].subject)
            .public_key(leaf_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(stamp - timedelta(minutes=5))
            .not_valid_after(stamp + timedelta(days=14))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(name) for name in names]), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA384())
        )
        cert_path, key_path = directory / 'server.crt', directory / 'server.key'
        key_path.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        os.chmod(key_path, 0o600)
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (directory / 'fullchain.crt').write_bytes(cert_path.read_bytes() + auth['issuer'].read_bytes())
        result[profile] = describe(cert_path, key_path, names, auth)
    state = Path(records) / 'state'
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    (state / 'tls.json').write_text(json.dumps(result, indent=2) + '\n')
    os.chmod(state / 'tls.json', 0o600)
    return result
