#!/bin/bash
# 断网验收用例（00.10.04）：在构建客户端 build01 上以 root 运行；构建以普通用户 builder 执行。
# 由 playbooks/offline-acceptance.yml 部署为 /usr/local/sbin/cnpl-offline-smoke 并调用。
#
# 用法：cnpl-offline-smoke [--clean] [--expect-offline]
#   --clean           先清空 builder 的各语言本地缓存、dnf 缓存与本地镜像（阶段 B，证明内容来自内部服务）
#   --expect-offline  先确认本机不能直连外网、也不能经 OpenWrt 代理出网（阶段 B）
# 每项输出一行：check=<名称> result=PASS|FAIL seconds=<秒> <最后一行输出>；失败时附最后 15 行输出。
# 一项失败不影响后续各项；有任何失败时退出码为 1。
set -uo pipefail
export LC_ALL=C.UTF-8

B=builder
WORK=/home/$B/work/offline-smoke
GIT_URL=https://gitlab.svc.internal.egon.top/lab/offline-smoke.git
IMAGE=harbor.k8s.internal.egon.top/dockerhub/library/busybox:1.37.0
CLEAN=no EXPECT_OFFLINE=no FAILED=0
for a in "$@"; do
  case $a in
    --clean) CLEAN=yes ;;
    --expect-offline) EXPECT_OFFLINE=yes ;;
    *) echo "未知参数：$a" >&2; exit 2 ;;
  esac
done

run() {
  local name=$1; shift
  local start out rc
  start=$(date +%s)
  out=$("$@" 2>&1); rc=$?
  if [ $rc -eq 0 ]; then
    echo "check=${name} result=PASS seconds=$(( $(date +%s) - start )) $(printf '%s' "$out" | tail -n1)"
  else
    FAILED=1
    echo "check=${name} result=FAIL seconds=$(( $(date +%s) - start )) rc=${rc}"
    printf '%s\n' "$out" | tail -n 15 | sed 's/^/    | /'
  fi
}

# 以 builder 执行（加载 ~/.cnpl-build-env）。runuser -u 不改 HOME，必须显式设置，
# 否则 ~ 与各工具的用户配置（settings.xml、.npmrc、pip.conf 等）都会指向 /root。
as_b() { runuser -u "$B" -- env HOME="/home/$B" USER="$B" bash -c "cd ~ && source ~/.cnpl-build-env && $1"; }

echo "== 断网验收 $(date -Is) clean=${CLEAN} expect_offline=${EXPECT_OFFLINE}"

if [ "$EXPECT_OFFLINE" = yes ]; then
  run no-internet bash -c '! curl -sS -m 8 -o /dev/null https://www.google.com 2>/dev/null && ! curl -sS -m 8 -o /dev/null https://dl.rockylinux.org 2>/dev/null && echo "直连外网失败（符合预期）"'
  run no-proxy bash -c '! curl -sS -m 8 -o /dev/null -x http://192.168.9.10:7890 https://www.google.com 2>/dev/null && echo "经 OpenWrt 代理出网失败（符合预期）"'
fi

if [ "$CLEAN" = yes ]; then
  as_b 'rm -rf ~/.m2/repository ~/.npm ~/.cache/pip ~/.nuget/packages ~/.local/share/NuGet ~/.cargo/registry ~/.cargo/git ~/.conan2/p ~/.venvs ~/work/offline-smoke'
  dnf clean all >/dev/null 2>&1
  podman rmi -f "$IMAGE" >/dev/null 2>&1
  dnf -y remove tree >/dev/null 2>&1
  echo "已清空：Maven、npm、pip、NuGet、Cargo、Conan 缓存，dnf 缓存，本地镜像，tree"
fi

# 1. 内部 DNS 与 TLS（系统信任内部根 CA，不加 -k）
run dns-tls bash -c 'for u in https://harbor.k8s.internal.egon.top/api/v2.0/ping https://gitlab.svc.internal.egon.top/users/sign_in https://nexus.svc.internal.egon.top/service/rest/v1/status; do curl -sSf -o /dev/null --max-time 15 "$u" || exit 1; done; echo "harbor gitlab nexus 证书校验通过"'

# 2. RPM：元数据与软件包都经 Nexus
run rpm bash -c 'dnf -y -q install tree && rpm -q tree'

# 3. 镜像：经 Harbor 代理缓存拉取并运行
run image bash -c "podman pull -q $IMAGE >/dev/null && podman run --rm --network none $IMAGE echo image offline-ok"

# 4. Git：从 GitLab 克隆测试项目（公开项目，匿名 HTTPS）
run git as_b "rm -rf $WORK && git clone -q $GIT_URL $WORK && git -C $WORK log -1 --format='commit %h %s'"

# 5–11. 七类语言
# cpp：每次先登出 Conan 远端，用口令换取新令牌。Nexus 按令牌限流，沿用被限流的旧令牌会一直返回 429（第 110 节）。
run java as_b "cd $WORK/java && mvn -B -q package dependency:build-classpath -Dmdep.outputFile=cp.txt && java -cp target/classes:\$(cat cp.txt) lab.Hello"
run js as_b "cd $WORK/js && npm install -s && npx tsc hello.ts && node hello.js"
run python as_b "cd $WORK/python && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt && .venv/bin/python main.py"
run csharp as_b "cd $WORK/csharp && dotnet build -c Release -v q && dotnet bin/Release/net8.0/hello.dll"
run rust as_b "cd $WORK/rust && cargo build -q --release && ./target/release/offline-smoke"
run c as_b "cd $WORK/c && make -s && ./hello"
run cpp as_b "cd $WORK/cpp && python3 -m venv ~/.venvs/conan && ~/.venvs/conan/bin/pip install -q conan==2.33.0 \
  && export PATH=~/.venvs/conan/bin:\$PATH \
  && conan profile detect --force >/dev/null \
  && conan remote add nexus https://nexus.svc.internal.egon.top/repository/conan-proxy/ --force \
  && (conan remote disable conancenter >/dev/null 2>&1 || true) \
  && (conan remote logout nexus >/dev/null 2>&1 || true) \
  && conan install . --output-folder=build --build=missing -s build_type=Release >/dev/null \
  && cmake -S . -B build -DCMAKE_TOOLCHAIN_FILE=build/conan_toolchain.cmake -DCMAKE_BUILD_TYPE=Release >/dev/null \
  && cmake --build build >/dev/null && ./build/hello"

if [ "$FAILED" -eq 0 ]; then echo "== 全部通过"; else echo "== 有未通过项"; fi
exit "$FAILED"
