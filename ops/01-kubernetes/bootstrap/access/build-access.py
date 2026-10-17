#!/usr/bin/env python3
"""校验 kubeadm 签发材料，组合日常/管理机/恢复 Context；秘密仅写入仓库外私有目录。"""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import yaml


HERE = Path(__file__).resolve().parent
SERVER = 'https://api.k8s.internal.egon.top:6443'


class AccessValidationError(ValueError):
    """只承载可公开的校验原因；不附带配置正文或底层解析异常。"""


def private_write(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.access-')
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_identity(config, identity, ca_data):
    if len(config['clusters']) != 1 or len(config['users']) != 1:
        raise AccessValidationError('签发材料必须只含一个集群与用户。')
    cluster = config['clusters'][0]['cluster']
    if cluster['server'] != SERVER or cluster['certificate-authority-data'] != ca_data:
        raise AccessValidationError('签发材料的 API/CA 与原集群不一致。')
    user = config['users'][0]['user']
    if set(user) != {'client-certificate-data', 'client-key-data'}:
        raise AccessValidationError('仅接受内嵌客户端证书和密钥。')
    certificate = x509.load_pem_x509_certificate(base64.b64decode(user['client-certificate-data']))
    ca = x509.load_pem_x509_certificate(base64.b64decode(ca_data))
    certificate.verify_directly_issued_by(ca)
    key = serialization.load_pem_private_key(base64.b64decode(user['client-key-data']), password=None)
    def public_bytes(public_key):
        return public_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if public_bytes(key.public_key()) != public_bytes(certificate.public_key()):
        raise AccessValidationError('客户端证书与私钥不匹配。')
    names = [item.value for item in certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)]
    groups = [item.value for item in certificate.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)]
    if names != [identity['name']] or groups != ([identity['group']] if identity['group'] else []):
        raise AccessValidationError('证书 CN/O 与身份清单不符，普通身份不得带管理员组。')
    if ExtendedKeyUsageOID.CLIENT_AUTH not in certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value:
        raise AccessValidationError('证书缺少客户端认证用途。')
    now = datetime.now(timezone.utc)
    if certificate.not_valid_before_utc > now or certificate.not_valid_after_utc < now + timedelta(days=7):
        raise AccessValidationError('证书尚未生效或不足七天到期；保留旧材料，显式处理轮换。')
    maximum = timedelta(hours=int(identity['validity'].removesuffix('h')), minutes=10)
    # kubeadm 可沿用 CA.NotBefore；--validity-period 约束的是从签发时刻到 NotAfter。
    if certificate.not_valid_after_utc > now + maximum:
        raise AccessValidationError('证书到期时间超过当前身份策略允许的剩余期限。')
    return user, {
        'username': identity['name'], 'groups': groups, 'client': identity['client'], 'role': identity['role'],
        'not_before_utc': certificate.not_valid_before_utc.isoformat(),
        'not_after_utc': certificate.not_valid_after_utc.isoformat(),
        'sha256': certificate.fingerprint(hashes.SHA256()).hex(),
    }


def normal_config(identities, materials, ca_data):
    return {
        'apiVersion': 'v1', 'kind': 'Config',
        'clusters': [{'name': 'lab-primary', 'cluster': {'server': SERVER, 'certificate-authority-data': ca_data}}],
        'users': [{'name': identity['name'], 'user': materials[identity['name']]} for identity in identities],
        'contexts': [{'name': identity['context'], 'context': {'cluster': 'lab-primary', 'user': identity['name'], 'namespace': 'lab-core'}} for identity in identities],
        'current-context': next(identity['context'] for identity in identities if identity['role'] == 'reader'),
    }


def recovery_config(user, ca_data):
    targets = {'cp01': '192.168.9.101', 'cp02': '192.168.9.102', 'cp03': '192.168.9.103', 'vip': 'api.k8s.internal.egon.top'}
    return {
        'apiVersion': 'v1', 'kind': 'Config',
        'clusters': [{'name': 'lab-primary-' + name, 'cluster': {'server': f'https://{host}:6443', 'certificate-authority-data': ca_data}} for name, host in targets.items()],
        'users': [{'name': 'cnpl-recovery-admin', 'user': user}],
        'contexts': [{'name': 'lab-primary-recovery-' + name, 'context': {'cluster': 'lab-primary-' + name, 'user': 'cnpl-recovery-admin'}} for name in targets],
        'current-context': 'lab-primary-recovery-cp01',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--admin-kubeconfig', type=Path, required=True)
    parser.add_argument('--check-only', action='store_true', help='仅核验已有材料，不创建文件或修改权限')
    args = parser.parse_args()
    root = args.directory.resolve()
    repository = HERE.parents[3]
    if root.is_relative_to(repository):
        raise AccessValidationError('客户端秘密目录必须位于仓库外。')
    if not args.check_only:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root.chmod(0o700)
    admin = yaml.safe_load(args.admin_kubeconfig.read_text())
    context = next(item['context'] for item in admin['contexts'] if item['name'] == admin['current-context'])
    cluster = next(item['cluster'] for item in admin['clusters'] if item['name'] == context['cluster'])
    if cluster['server'] != SERVER:
        raise AccessValidationError('既有管理配置未指向实验 API。')
    ca_data = cluster['certificate-authority-data']
    identities = yaml.safe_load((HERE / 'identities.yaml').read_text())['phase01_access_identities']
    materials, report = {}, []
    for identity in identities:
        path = root / 'issued' / (identity['name'] + '.conf')
        if not args.check_only:
            path.chmod(0o600)
        try:
            materials[identity['name']], metadata = validate_identity(yaml.safe_load(path.read_text()), identity, ca_data)
        except AccessValidationError as error:
            raise AccessValidationError(identity['name'] + '：' + str(error)) from None
        report.append(metadata)
    if args.check_only:
        print(json.dumps({'status': 'ok', 'mode': 'check-only', 'identities': [item['username'] for item in report]}, ensure_ascii=False))
        return
    for client in ['mac', 'adminhost']:
        config = normal_config([item for item in identities if item['client'] == client], materials, ca_data)
        private_write(root / (client + '.conf'), yaml.safe_dump(config, sort_keys=False).encode())
    recovery = yaml.safe_dump(recovery_config(materials['cnpl-recovery-admin'], ca_data), sort_keys=False).encode()
    private_write(root / 'recovery/recovery.conf', recovery)
    public_report = json.dumps(report, ensure_ascii=False, indent=2).encode() + b'\n'
    private_write(root / 'certificates.json', public_report)
    instructions = (
        'Recovery identity: cnpl-recovery-admin; group system:masters. Contains a private key.\n'
        'Keep outside Git and ordinary KUBECONFIG. File mode 0600, directory 0700.\n'
        'Client certificate has a fixed expiry; no automatic renewal or individual certificate revocation.\n'
        'kubectl --kubeconfig recovery.conf --context lab-primary-recovery-cp01 get nodes\n'
        'Contexts: cp01/.101, cp02/.102, cp03/.103 and vip/API DNS. Never skip TLS verification.\n'
        'Direct IP contexts work without API VIP/DNS; a healthy API/etcd and network are still required.\n'
        'This is API recovery access, not an etcd/PKI/encryption-key backup. CA private keys are excluded.\n'
    ).encode()
    private_write(root / 'recovery/README.txt', instructions)
    package = io.BytesIO()
    with tarfile.open(fileobj=package, mode='w:gz') as archive:
        for name, data in [('recovery.conf', recovery), ('README.txt', instructions), ('certificates.json', public_report)]:
            info = tarfile.TarInfo(name)
            info.mode, info.size = 0o600, len(data)
            archive.addfile(info, io.BytesIO(data))
    private_write(root / 'recovery/recovery-kit.tar.gz', package.getvalue())
    print(json.dumps({'status': 'ok', 'message': 'Access material validated; client configs and recovery package generated outside Git.'}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, IndexError, TypeError, StopIteration, OSError, x509.ExtensionNotFound, InvalidSignature, yaml.YAMLError) as error:
        if isinstance(error, AccessValidationError):
            reason = str(error)
        elif isinstance(error, OSError):
            reason = '私有文件访问或写入失败；请检查文件存在性和权限。'
        elif isinstance(error, InvalidSignature):
            reason = '客户端证书签名未通过既有 CA 验证。'
        else:
            reason = '配置/证书/私钥格式或结构异常；原始内容保持隐藏。'
        print(json.dumps({'status': 'error', 'reason': reason, 'error_type': type(error).__name__}, ensure_ascii=False))
        raise SystemExit(1)
