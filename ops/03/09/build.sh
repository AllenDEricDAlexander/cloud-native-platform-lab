#!/usr/bin/env bash
# 仅编译/打包源输入，不启动应用、容器或集群。
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
go=${CNPL03_GO:-$HOME/.cnpl/toolchains/go1.27.2/go/bin/go}
[[ -x $go ]] || { echo '缺少既有 Go 工具链；设置 CNPL03_GO' >&2; exit 1; }
export GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local CGO_ENABLED=0
cd "$root/operator"
"$go" test ./...
mkdir -p "$root/bin"
GOOS=linux GOARCH=amd64 "$go" build -trimpath -buildvcs=false -ldflags='-s -w -buildid=' -o "$root/bin/demoapp-operator" .
shasum -a 256 "$root/bin/demoapp-operator" > "$root/bin/sha256.txt"
GOOS=linux GOARCH=amd64 "$go" build -trimpath -buildvcs=false -ldflags='-s -w -buildid=' -o "$root/bin/demo-app" "$root/demo/main.go"
shasum -a 256 "$root/bin/demo-app" >> "$root/bin/sha256.txt"
printf '已生成 linux/amd64 二进制；镜像仅由 build01 VM 的 build-vm 动作构建。\n'
