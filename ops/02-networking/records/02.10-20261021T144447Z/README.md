# 02.10 原用户失败批次与后续恢复

原始 all 在 applications 失败，随后恢复被 Istiod 自动生成 ConfigMap 的误判阻断。原始 all 与第一次 recover 日志均保持原样。

修复识别规则后，第二次 recover 完整通过：ok=245 changed=72 unreachable=0 failed=0 skipped=8 rescued=0 ignored=0。回执见 state/closed.json、postcheck.json 和 summary-recover-20261021T151319Z-4kUn7U.json。

本批是失败后恢复，不能算实验通过。最终正式验收见 [R2](../02.10-20261021T154100Z-agent-r2/README.md)。
