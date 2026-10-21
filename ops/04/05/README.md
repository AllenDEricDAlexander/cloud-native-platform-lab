# 04.05 七语言源码与十四格交付

覆盖 04.05.01–08。examples 下七套源码/测试/原生包/Containerfile，build.sh 在选定 Builder 中执行，不在 Mac 启动服务。05/run.sh 默认只离线检查。export <language> <仓库外全新目录> 导出本批脚本和固定平台 include，随后由用户创建仓库/审查提交；不会覆盖已有目录或自动推送。

| 语言 | 构建/检查 | 运行与原生制品 |
| --- | --- | --- |
| Java | JDK21/Maven/Spring Boot/JUnit；JDK25、Gradle另作兼容对比 | jar、Java CA/内存/连接池按所选数据服务另核对 |
| Rust | fmt/Clippy/test/locked release | Linux glibc 二进制、原生 --native；musl交叉编译另验 |
| C | GCC/Clang、CMake/Ninja/CTest、ASan/UBSan | 计算内核、原生 --native、HTTP适配 |
| C++ | C++20、Conan锁/CMake/Ninja/CTest、ASan/UBSan | 无第三方运行依赖的计算服务；ABI记录到Builder报告 |
| C# | .NET10 locked restore/build、自测/publish | ASP.NET Core框架依赖主线；自包含和Windows另验 |
| JS/TS | npm ci、TypeScript typecheck/build、Node test | Node服务和静态页面；TS编译器属于Builder固定工具链 |
| Python | pip hash锁、Ruff/pytest/Wheel | 标准库计算/HTTP服务；build工具固定在Builder |

source依赖版本是待验证的固定样例，不能视为已预热。Java的3.5.0、.NET10、Python构建工具必须与00预热及Builder匹配；不匹配时先受审更新并锁定整棵依赖树，不联网临时升级。无外部依赖的Cargo/npm/NuGet/Conan/Python锁文件允许为空；不能伪造缺失包的校验和。Java还需在内部Nexus形成完整依赖闭包及校验清单。C++复用邻目录C的HTTP头，但计算内核、编译与交付独立。

所有服务提供/health、/ready、/version、/compute、/metrics，默认8080、非root、SIGTERM退出。FAIL_REQUESTS=true制造业务500，健康探针仍成功，供08验证真实灰度中止。revision随镜像固化；正式晋级不重新构建。请求日志为JSON；实际Trace导出、数据库集成/连接池、目标环境链接库和Java25/Gradle、.NET自包含等对比必须现场单独记录，当前不声称通过。

执行每格：固定同一提交→对应CI verify/package/security→合并本格GitOps MR→observe核对同一Digest/版本/真实请求→保存release/observed.json和CI原始链接。随后 matrix <14份observed.json> 检查组合完整性。分别构造编译错误、500坏版本、冷/暖/断外网任务和已知Digest回退；不能拿另一CI的镜像充数。总计14格与所有正常/失败路径均有证据后才可填写运行验收；回执完整不自动代表整个04完成。

每种语言的GitLab/Jenkins对照必须使用该语言同一源码SHA和Builder Digest；分应用仓库时不同语言可有不同SHA，不能强求七个独立仓库出现同一Git提交。单仓库矩阵也支持全部使用同一SHA。
