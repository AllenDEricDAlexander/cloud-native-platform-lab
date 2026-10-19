#!/usr/bin/env bash
set -euo pipefail
# 只输出 CRI 相关的四个字段，不显示完整运行时配置。
containerd config dump | awk '
  /^[[:space:]]*\[/ {section=$0; gsub(/[\047"]/, "", section); sub(/^[[:space:]]+/, "", section); sub(/[[:space:]]+$/, "", section)}
  /^version[[:space:]]*=/ {version=$3}
  section=="[plugins.io.containerd.cri.v1.images.pinned_images]" && $1=="sandbox" {sandbox=$3;gsub(/[\047"]/, "", sandbox)}
  section=="[plugins.io.containerd.cri.v1.runtime]" && $1=="enable_selinux" {selinux=$3}
  section=="[plugins.io.containerd.cri.v1.runtime.containerd.runtimes.runc.options]" && $1=="SystemdCgroup" {systemd=$3}
  END {
    if(version!="3" || sandbox!~/^harbor[.]k8s[.]internal[.]egon[.]top\/bootstrap\/pause@sha256:[0-9a-f]+$/ || split(sandbox,parts,"sha256:")!=2 || length(parts[2])!=64 || selinux!="true" || systemd!="true") exit 1;
    printf "{\"version\":3,\"sandbox\":\"%s\",\"selinux\":true,\"systemd_cgroup\":true}\n",sandbox
  }'
