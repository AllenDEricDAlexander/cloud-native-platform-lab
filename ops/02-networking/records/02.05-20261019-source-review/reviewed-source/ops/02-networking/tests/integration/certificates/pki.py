"""只在 Mac 解密根 CA；新建独立受限签发身份，原有两份 CA 私钥不上传。"""
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
PUBLIC = ROOT / 'ops/00-preparation/pki/public/cnpl-lab-root-ca.crt'
PRIVATE = Path.home() / '.cnpl-secrets/certificates/lab-primary'
NAMES = ['demo.svc.internal.egon.top', 'grpc-demo.svc.internal.egon.top']


def require(value, reason):
    if not value:
        raise ValueError(reason)


def fingerprint(cert):
    return cert.fingerprint(hashes.SHA256()).hex()


def public(key):
    return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def authority():
    base = Path(os.environ.get('CNPL_PKI_DIR', str(Path.home() / 'cnpl-pki'))).resolve()
    require(PUBLIC.read_bytes() == (base / 'root/root.crt').read_bytes(), '离线根 CA 与公开信任根不一致')
    require((base / 'root/root.key').is_file(), '缺少既有加密根 CA 私钥')
    cert = x509.load_pem_x509_certificate(PUBLIC.read_bytes())
    basic = cert.extensions.get_extension_for_class(x509.BasicConstraints).value
    require(basic.ca and (basic.path_length is None or basic.path_length >= 1), '根 CA 不允许独立中间签发器')
    require(cert.not_valid_after_utc > datetime.now(timezone.utc) + timedelta(days=366), '根 CA 剩余有效期不足')
    return base, cert


def save_key(path, key):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    os.chmod(path, 0o600)


def describe(directory):
    cert = x509.load_pem_x509_certificate((directory / 'server.crt').read_bytes())
    key = serialization.load_pem_private_key((directory / 'server.key').read_bytes(), password=None)
    require(public(key.public_key()) == public(cert.public_key()), '证书与私钥不匹配')
    return {'certificate': str(directory / 'server.crt'), 'private_key': str(directory / 'server.key'), 'fullchain': str(directory / 'fullchain.crt'), 'sha256': fingerprint(cert), 'spki_sha256': hashlib.sha256(public(cert.public_key())).hexdigest(), 'not_after': cert.not_valid_after_utc.isoformat()}


def existing_issuer(context):
    directory = PRIVATE / context['cluster_uid'] / 'issuer'
    if not directory.exists():
        return None
    require(all((directory / n).is_file() for n in ['server.crt', 'server.key', 'fullchain.crt']), '专用签发器材料不完整，不能覆盖')
    value = describe(directory)
    cert = x509.load_pem_x509_certificate(Path(value['certificate']).read_bytes())
    basic = cert.extensions.get_extension_for_class(x509.BasicConstraints).value
    constraints = cert.extensions.get_extension_for_class(x509.NameConstraints).value
    require(basic.ca and basic.path_length == 0 and set(constraints.permitted_subtrees) == {x509.DNSName(n) for n in NAMES}, '专用签发器路径或名称约束改变')
    require(cert.not_valid_after_utc > datetime.now(timezone.utc) + timedelta(days=8), '专用签发器接近过期')
    result = subprocess.run(['openssl', 'verify', '-CAfile', str(PUBLIC), value['certificate']], capture_output=True, text=True, timeout=10)
    require(result.returncode == 0, '专用签发器不能由既有根 CA 验证')
    return value


def base_certificate(subject, issuer, key, days=1):
    now = datetime.now(timezone.utc)
    return (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=days)))


def prepare(records, context, password=None):
    base, root = authority()
    issuer = existing_issuer(context)
    if not issuer:
        require(password, '首次创建专用中间 CA 需要安全输入根 CA 口令')
        try:
            root_key = serialization.load_pem_private_key((base / 'root/root.key').read_bytes(), password=password)
        except (ValueError, TypeError):
            raise ValueError('根 CA 口令不正确，尚未执行集群变更') from None
        require(public(root_key.public_key()) == public(root.public_key()), '根 CA 密钥与公开证书不同')
        key = ec.generate_private_key(ec.SECP384R1())
        subject = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'cloud-native-platform-lab'), x509.NameAttribute(NameOID.COMMON_NAME, 'CNPL cert-manager ' + context['cluster_uid'])])
        cert = (base_certificate(subject, root.subject, key, 365)
                .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
                .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), True)
                .add_extension(x509.NameConstraints(permitted_subtrees=[x509.DNSName(n) for n in NAMES], excluded_subtrees=None), True)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), False)
                .sign(root_key, hashes.SHA384()))
        directory = PRIVATE / context['cluster_uid'] / 'issuer'
        save_key(directory / 'server.key', key)
        (directory / 'server.crt').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (directory / 'fullchain.crt').write_bytes((directory / 'server.crt').read_bytes() + PUBLIC.read_bytes())
        issuer = existing_issuer(context)
        del root_key
    issuer_cert = x509.load_pem_x509_certificate(Path(issuer['certificate']).read_bytes())
    issuer_key = serialization.load_pem_private_key(Path(issuer['private_key']).read_bytes(), password=None)
    cached = Path(records) / 'state/materials.json'
    if cached.exists():
        saved = json.loads(cached.read_text())
        require(saved['issuer']['sha256'] == issuer['sha256'], '本批签发身份改变')
        for value in saved['profiles'].values():
            path = Path(value['private_key']).parent
            require(path.resolve().is_relative_to(PRIVATE.resolve()) and describe(path)['sha256'] == value['sha256'], '测试叶证书材料改变')
        return saved
    foreign_key = ec.generate_private_key(ec.SECP384R1())
    foreign_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'isolated untrusted test authority')])
    foreign = (base_certificate(foreign_name, foreign_name, foreign_key, 2)
               .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
               .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), True)
               .add_extension(x509.SubjectKeyIdentifier.from_public_key(foreign_key.public_key()), False)
               .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(foreign_key.public_key()), False)
               .sign(foreign_key, hashes.SHA384()))
    profiles = {}
    for name in ['valid', 'san', 'unknown', 'incomplete', 'expired']:
        directory = PRIVATE / context['cluster_uid'] / context['run'] / name
        key = ec.generate_private_key(ec.SECP256R1())
        signer, signing_key = (foreign, foreign_key) if name == 'unknown' else (issuer_cert, issuer_key)
        dns = NAMES[1] if name == 'san' else NAMES[0]
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, dns)])
        builder = base_certificate(subject, signer.subject, key, 2)
        if name == 'expired':
            now = datetime.now(timezone.utc)
            builder = (x509.CertificateBuilder().subject_name(subject).issuer_name(signer.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
                       .not_valid_before(now - timedelta(days=2)).not_valid_after(now - timedelta(hours=1)))
        cert = (builder.add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
                .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), True)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(dns)]), False)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(signing_key.public_key()), False)
                .sign(signing_key, hashes.SHA384()))
        save_key(directory / 'server.key', key)
        (directory / 'server.crt').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        chain = b'' if name == 'incomplete' else signer.public_bytes(serialization.Encoding.PEM)
        (directory / 'fullchain.crt').write_bytes(cert.public_bytes(serialization.Encoding.PEM) + chain)
        profiles[name] = describe(directory)
    result = {'issuer': issuer, 'profiles': profiles, 'private_dir': str(PRIVATE / context['cluster_uid'] / context['run'])}
    cached.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    cached.write_text(json.dumps(result, indent=2) + '\n')
    os.chmod(cached, 0o600)
    return result
