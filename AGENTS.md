# AGENTS.md

`proxy-platform` 是统一入口薄平台壳仓库，不是新的控制面内核，也不是私有 inventory/secrets 真相源。

## Scope

- 本仓库负责统一 CLI / 未来 Web 工作台 / 编排层 / manifest / 平台级文档治理。
- 本仓库负责平台状态模型：主机登记册、观测回报、订阅派生与后续 job schema 的统一定义。
- 本仓库可以引用下游仓库，但不应复制它们的业务内核与私有真相内容。
- 下游仓库各自的实现细节、私有 secrets、运行时状态仍以原仓库为准。
- `/workspaces/proxy-platform/repos/` 下的是权威工作树。
- `/workspaces/proxy-platform/archive/` 下的是分析副本、历史快照和临时材料，不是源码真相源。

## Hard Boundaries

- 不在本仓库提交 `Proxy_ops_private` 的真实 secrets、inventory、生成产物。
- 不在本仓库重写 `CliProxy-control-plane` 的 `/v1` 网关和 worker southbound 逻辑。
- 不在本仓库直接实现 destructive 远端写操作，除非先有 dry-run、审计日志和明确的 job schema。
- 不把订阅文本、页面列表或临时脚本输出当成原始真相；它们只能是派生结果。
- `remote_browser` 在本阶段只作为可选 provider 插槽，不默认进入核心主链工作流。

## Delivery Workflow

- 先写计划，再写失败测试，再写最小实现。
- 新命令必须先有帮助文案与可验证输出，再扩展副作用。
- 任何平台级决策都要同步写入 `docs/adr/`。
- 任何新增 adapter 或 command 都必须补最小测试。
- 涉及仓库边界调整时，先做 ownership review，再决定代码落点。

## Documentation Contract

- `README.md` 是用户入口。
- `docs/adr/` 记录架构决策。
- `docs/agent-governance/project/` 记录平台级 agent/harness 解释。
- `docs/review-checklists/` 记录人工与 agent 评审清单。

## Review Focus

- 是否保持薄平台壳边界，没有滑向“第二控制面”。
- 是否保护 private/public 边界。
- 是否把复杂性收敛到 manifest、adapter、job schema，而不是散落在 README 和人工步骤里。
- 是否把共享平台判断逻辑留在 `proxy-platform`，而不是散回 `remote_proxy` 或 `Proxy_ops_private`。
