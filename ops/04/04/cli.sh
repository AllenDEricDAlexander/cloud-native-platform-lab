#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../lib/common.sh"
jenkins_cli() {
    verify_file "$(required .jenkins.cli_file)" "$(required .jenkins.cli_sha256)"
    private_file "$(required .jenkins.auth_file)"
    [[ $(required .jenkins.url) == https://jenkins.k8s.internal.egon.top ]] || die 'Jenkins 地址与登记入口不符'
    java -jar "$(required .jenkins.cli_file)" -s "$(required .jenkins.url)" -auth "@$(required .jenkins.auth_file)" "$@"
}
