# 平台级 Agent Governance

本目录记录 `proxy-platform` 对 OpenAI Codex / Anthropic Claude Code / MetaHarness 类规范的项目化解释。

当前约束：

- 分层 `AGENTS.md`
- 子代理只做边界清晰的 side work
- destructive 动作必须先 dry-run
- 平台级架构决策必须进入 ADR
