# proxy-platform 实施计划

## 目标

实现统一入口仓库 `proxy-platform` 的第一波可交付骨架：

- 平台级 `AGENTS.md`
- `README.md`
- `platform.manifest.yaml`
- ADR 初稿
- 可测试的 CLI 薄壳
- `doctor / init / sync / repos list / manifest validate` 最小闭环

## 范围边界

- 本阶段不重写 `CliProxy-control-plane` 业务内核。
- 本阶段不搬运 `Proxy_ops_private` 的私有真相内容。
- 本阶段不实现真实远端部署写操作，只提供 manifest、状态检查、工作区初始化与 dry-run 编排壳。
- Web 工作台本阶段只建目录与架构占位，不做完整前端实现。

## 阶段

1. `completed` 初始化仓库与计划文件
2. `completed` 编写实施计划文档
3. `completed` 编写失败测试
4. `completed` 实现 CLI、manifest 与基础文档骨架
5. `completed` 运行验证并完成本轮非真机验证

## 风险

- 私有仓库 submodule URL 暂时无法在当前环境下完成真实拉取验证，需要通过 manifest 和 local-path 检测支持 operator mode。
- 如果实现过度膨胀为第二控制面，则偏离当前阶段目标。
- 当前仍未实现自动安装/切换系统运行时；平台壳只负责诊断和建议，不直接改宿主机。
