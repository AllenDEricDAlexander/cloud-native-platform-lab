#!/usr/bin/env bash
set -euo pipefail

install -d -m 0700 /root/lab-evidence/phase00
(
set -euxo pipefail
trap 'LAB_STEP_RC=$?; printf "step_exit=%s\n" "$LAB_STEP_RC"' EXIT
date -Is
test "$(hostnamectl --static)" = rocky10-base
test "$(systemctl is-enabled containerd || true)" = masked
test "$(getenforce)" = Enforcing
firewall-cmd --state
test "$(findmnt -rn -M /var/lib/containerd -o UUID)" = 1b36c022-c96c-4b0f-9570-d8e291ba03c0
command -v python3

install -d -m 0755 /etc/containerd/certs.d /etc/systemd/system/containerd.service.d
cp -a /etc/containerd/config.toml "/etc/containerd/config.toml.phase00.$(date +%Y%m%d%H%M%S).bak"
cat > /etc/containerd/config.toml <<'EOF'
version = 3
root = "/var/lib/containerd"
state = "/run/containerd"
disabled_plugins = []

[plugins."io.containerd.cri.v1.runtime"]
  enable_selinux = true
[plugins."io.containerd.cri.v1.runtime".containerd]
  default_runtime_name = "runc"
[plugins."io.containerd.cri.v1.runtime".containerd.runtimes.runc]
  runtime_type = "io.containerd.runc.v2"
  sandboxer = "podsandbox"
[plugins."io.containerd.cri.v1.runtime".containerd.runtimes.runc.options]
  SystemdCgroup = true

[plugins."io.containerd.cri.v1.images".registry]
  config_path = "/etc/containerd/certs.d"
EOF

python3 - <<'PY'
import tomllib
with open('/etc/containerd/config.toml', 'rb') as stream:
    config = tomllib.load(stream)
runtime = config['plugins']['io.containerd.cri.v1.runtime']
assert config['version'] == 3
assert config['root'] == '/var/lib/containerd'
assert config['disabled_plugins'] == []
assert runtime['enable_selinux'] is True
assert runtime['containerd']['runtimes']['runc']['options']['SystemdCgroup'] is True
print('CRI TOML configuration checks passed')
PY
containerd config dump > /root/lab-evidence/phase00/00.10.02-containerd-effective.toml

cat > /etc/systemd/system/containerd.service.d/10-runtime-mount.conf <<'EOF'
[Unit]
RequiresMountsFor=/var/lib/containerd
BindsTo=var-lib-containerd.mount
After=var-lib-containerd.mount
AssertPathIsMountPoint=/var/lib/containerd
EOF
restorecon -Rv /etc/containerd /etc/systemd/system/containerd.service.d /var/lib/containerd
systemctl unmask containerd.service
systemctl daemon-reload
systemd-analyze --generators=yes verify /usr/lib/systemd/system/containerd.service
systemctl enable --now containerd

systemctl is-enabled containerd
systemctl is-active containerd
systemctl show containerd -p RequiresMountsFor -p BindsTo -p After -p AssertResult
ctr plugins ls
ctr plugins ls | awk '$1 == "io.containerd.cri.v1" && ($2 == "runtime" || $2 == "images") { if ($NF != "ok") exit 1; seen++ } END { if (seen != 2) exit 1 }'
ps -eZ | grep '[c]ontainerd'
ls -lZ /run/containerd/containerd.sock
getenforce
firewall-cmd --state
journalctl -u containerd -b -n 40 --no-pager
) 2>&1 | tee -a /root/lab-evidence/phase00/00.10.02-containerd-configure.txt
