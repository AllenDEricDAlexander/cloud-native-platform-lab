#!/usr/bin/env bash
set -euo pipefail
conan remote add nexus https://nexus.svc.internal.egon.top/repository/conan-proxy/ --force
conan remote disable conancenter
# 凭据使用 CI 注入的 CONAN_LOGIN_USERNAME_NEXUS/CONAN_PASSWORD_NEXUS；不写进镜像。
