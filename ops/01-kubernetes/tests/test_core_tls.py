"""真实原生 Ansible/OpenSSL 和私有模板验证；密钥仅保留于临时目录。"""
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import yaml

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509.oid import ExtendedKeyUsageOID

BASE=Path(__file__).resolve().parents[1];ROOT=BASE.parents[1]


class CoreTLSIntegrationTest(unittest.TestCase):
    def test_real_native_tls_chain_reuse_private_modes_and_secret_formats(self):
        with tempfile.TemporaryDirectory(prefix='cnpl-core-tls-') as temporary:
            folder=Path(temporary).resolve();values=folder/'inputs.json'
            values.write_text(json.dumps({'core_root':str(ROOT),'core_private':str(folder),'core_run':'test-run','core_namespace':'unit','core_metrics_namespace':'unit','core_cluster_uid':'cluster','core_secret_value':'fixture-only','core_pull_secret_name':'fixture-pull','core_pull_config':{'auths':{'example.invalid':{'auth':'Zml4dHVyZTppbnZhbGlk'}}},'core_bound_token':'fixture.not-a-real.jwt'}))
            env=dict(os.environ,ANSIBLE_CONFIG=str(ROOT/'ops/00-preparation/ansible/ansible.cfg'))
            result=subprocess.run([str(Path.home()/'.venvs/cnpl-ansible/bin/ansible-playbook'),str(BASE/'tests/core-tls-smoke.yml'),'-e','@'+str(values)],capture_output=True,text=True,env=env,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout[-5000:]+result.stderr[-1000:])
            for name in ['metrics-server','app-tls']:
                directory=folder/name
                ca=x509.load_pem_x509_certificate((directory/'ca.crt').read_bytes());leaf=x509.load_pem_x509_certificate((directory/'tls.crt').read_bytes())
                ca.public_key().verify(leaf.signature,leaf.tbs_certificate_bytes,padding.PKCS1v15(),leaf.signature_hash_algorithm)
                self.assertEqual(leaf.issuer,ca.subject)
                self.assertIn(ExtendedKeyUsageOID.SERVER_AUTH,leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value)
                self.assertIn(name+'.unit.svc',leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName))
                key=serialization.load_pem_private_key((directory/'tls.key').read_bytes(),password=None)
                self.assertEqual(key.public_key().public_numbers(),leaf.public_key().public_numbers())
                self.assertEqual((directory/'tls.key').stat().st_mode & 0o777,0o600)
                self.assertEqual((directory/'ca.key').stat().st_mode & 0o777,0o600)
            expected={'opaque':'Opaque','tls-secret':'kubernetes.io/tls','metrics-secret':'kubernetes.io/tls','pull-secret':'kubernetes.io/dockerconfigjson'}
            for name,kind in expected.items():
                obj=yaml.safe_load((folder/(name+'.yaml')).read_text());self.assertEqual(obj['type'],kind)
                for value in obj['data'].values():self.assertTrue(base64.b64decode(value))
                self.assertEqual((folder/(name+'.yaml')).stat().st_mode & 0o777,0o600)
            review=yaml.safe_load((folder/'token-review.yaml').read_text());self.assertEqual(review['kind'],'TokenReview');self.assertEqual(review['spec']['audiences'],['core-lab-p10'])
            self.assertNotIn('-----BEGIN PRIVATE KEY',result.stdout)


if __name__=='__main__':unittest.main()
