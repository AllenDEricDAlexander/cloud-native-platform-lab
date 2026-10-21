#!/usr/bin/env bash
# 在对应语言 Builder 内执行，不在管理端启动应用。
set -euo pipefail
set +x
language=${1:?指定语言}
root=$(cd "$(dirname "$0")" && pwd)
[[ $language =~ ^(java|rust|c|cpp|csharp|jsts|python)$ ]] || exit 2
cd "$root/examples/$language"
: "${SOURCE_REVISION:?完整源码 SHA}"
[[ $SOURCE_REVISION =~ ^[a-f0-9]{40}$ ]] || exit 2
[[ ! -L dist ]] || exit 2
mkdir -p dist
case "$language" in
    java)
        mvn -B -s "$root/../02/config/settings.xml" verify
        cp target/demo.jar dist/app.jar ;;
    rust)
        cargo fmt --check
        cargo clippy --locked --all-targets -- -D warnings
        cargo test --locked
        cargo build --release --locked
        cp target/release/cnpl-demo dist/app ;;
    c|cpp)
        if [[ $language == cpp ]]; then
            conan install . --lockfile=conan.lock --output-folder=build --build=missing -s build_type=Release
            cmake -S . -B build -G Ninja -DCMAKE_TOOLCHAIN_FILE=conan_toolchain.cmake -DCMAKE_BUILD_TYPE=Release
        else cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release; fi
        cmake --build build
        ctest --test-dir build --output-on-failure
        cmake -S . -B build-sanitize -G Ninja -DENABLE_SANITIZERS=ON -DCMAKE_BUILD_TYPE=Debug
        cmake --build build-sanitize
        ctest --test-dir build-sanitize --output-on-failure
        cp build/app dist/app ;;
    csharp)
        dotnet restore --locked-mode --configfile "$root/../02/config/NuGet.Config"
        dotnet build -c Release --no-restore
        dotnet run -c Release --no-build -- --self-test
        dotnet publish -c Release --no-restore --self-contained false -o dist/publish ;;
    jsts)
        NPM_CONFIG_USERCONFIG="$root/../02/config/npmrc" npm ci --ignore-scripts
        npm run typecheck
        npm run build
        npm test
        cp server.mjs dist/server.mjs
        cp -R public dist/public ;;
    python)
        python -m venv --system-site-packages .venv
        .venv/bin/python -m pip install --require-hashes --no-deps -r requirements.lock
        .venv/bin/python -m ruff check . --exclude .venv
        .venv/bin/python -m pytest tests -q
        .venv/bin/python -m build --no-isolation
        cp service.py dist/service.py ;;
esac
# 所有制品包含同一提交身份；运行期 /version 从该文件读取。
printf '%s\n' "$SOURCE_REVISION" > dist/revision
tar -cf dist/native.tar --exclude=native.tar -C dist .
jq -n --arg language "$language" --arg revision "$SOURCE_REVISION" '{language:$language,source_revision:$revision,unit_tests:"passed",integration_tests:"not_run",runtime_accepted:false}' > dist/tests.json
