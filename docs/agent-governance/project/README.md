# 平台级 Agent Governance

本目录记录 `proxy-platform` 对 OpenAI Codex / Anthropic Claude Code / MetaHarness 类规范的项目化解释。

当前约束：

- 分层 `AGENTS.md`
- 子代理只做边界清晰的 side work
- destructive 动作必须先 dry-run
- 平台级架构决策必须进入 ADR
- 平台状态必须区分“登记册真相、观测回报、派生视图”
- agent 修改仓库边界时，必须先做 ownership matrix review
- 依赖 private registry 的入口必须显式声明 `operator` 模式，不允许 public 模式隐式穿透
