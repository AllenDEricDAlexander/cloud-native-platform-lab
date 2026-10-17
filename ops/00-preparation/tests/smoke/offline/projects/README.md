# 断网验收的七类最小项目

每个项目只依赖一个固定版本的外部组件，构建时经 Nexus（只读账户）取得，不访问外网。
由 `../offline-smoke.sh` 在构建客户端上依次构建并运行；同一份内容同步到 GitLab 的 lab/offline-smoke，
客户端从 GitLab 克隆后构建（Git 检查）。

| 目录 | 语言 | 工具 | 固定依赖 | 经由 |
| --- | --- | --- | --- | --- |
| java | Java 21 | Maven 3.9 | org.apache.commons:commons-lang3:3.17.0（插件版本也固定） | maven-central |
| js | TypeScript | Node 22 / npm 10 | typescript@5.6.3 | npm-proxy |
| python | Python 3.12 | pip（venv） | requests==2.32.3 及其依赖 | pypi-proxy |
| csharp | C# | .NET SDK 8 | Newtonsoft.Json 13.0.3 | nuget.org-proxy |
| rust | Rust | Cargo 1.92 | itoa =1.0.11 | cargo-proxy |
| c | C | GCC 14 / make | 无 | — |
| cpp | C++ | GCC 14 / CMake / Conan 2.33.0 | nlohmann_json/3.11.3 | conan-proxy（Conan 本身经 pypi-proxy） |
