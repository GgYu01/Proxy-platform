# ADR-0016: 把 webchat-openai-runtime 作为独立 provider runtime 纳入 proxy-platform 治理

## 状态

已采纳，2026-04-17

## 背景

当前 `proxy-platform` 已经明确是“统一入口薄平台壳”，它负责 repo 注册、平台状态模型、ADR、评审清单和工作台入口，但不负责接管下游业务内核。

新出现的需求不是再做一个控制面，而是把 DeepSeek / Qwen / Kimi / GLM 这类网页端 AI chat 会话，包装成可以被本地 agent、OpenAI SDK、后续 `new-api` 和 `CLIProxyAPIPlus` 统一调用的 OpenAI-compatible 运行时。

换句话说，这次新增的不是“平台多一个页面”，而是“平台多纳管一个执行内核仓库”：

- `proxy-platform` 负责把它登记进平台清单、文档和评审链路
- `webchat-openai-runtime` 负责浏览器会话执行、provider adapter、OpenAI-compatible 协议面和风险状态

如果把这两层混在一起，会同时带来三个问题：

- `proxy-platform` 会从薄平台壳滑向新的浏览器控制面
- 浏览器 profile、账号槽位、challenge/warning 这些运行态会失去清晰 owner
- 后续 `new-api`、`CLIProxyAPIPlus`、`cliproxy-control-plane` 的上游接入边界会变乱

## 决策

把 `repos/webchat-openai-runtime` 正式定义为：

- repo id: `webchat_openai_runtime`
- display name: `webchat-openai-runtime`
- role: `optional_provider_runtime`
- mode boundary: `operator`
- visibility: `public`

并明确它的职责是：

- 浏览器会话执行内核
- provider adapter 抽象与 Qwen-first 基准实现
- OpenAI-compatible `/v1/models`、`/v1/chat/completions`、`/v1/responses`
- 账号级 Qwen 登录工作台后端：启动/复用会话、暴露状态与截图、接收鼠标/键盘输入，并把当前登录态保存回账号池
- streaming、image/file 输入兼容面、tool relay、默认关闭的 hosted tool execution 骨架
- 风控感知状态、warning feeds、acceptance harness

同时明确它不负责：

- 租户、帐号池运营、计费、渠道治理
- `CliProxy-control-plane` 的 northbound `/v1` 控制面内核
- `Proxy_ops_private` 一类私有真相和 secrets

## 为什么这样做

这样拆分的好处不是“多一个仓库更好看”，而是把复杂性放回正确 owner：

- `proxy-platform` 继续负责“平台现场清单、治理文件、评审入口”
- `webchat-openai-runtime` 继续负责“浏览器怎么活、会话怎么存、网页怎么打、协议怎么回”
- 上层系统以后只需要把它当成标准 OpenAI-compatible 上游，而不需要理解网页端 provider 的具体 DOM 和 session 细节

在这个项目里，用项目语言解释就是：

- `proxy-platform` 管的是“它是谁、放在哪、怎么审、怎么接”
- `webchat-openai-runtime` 管的是“它怎么执行、怎么告警、怎么对外回包”

## 结果

正向结果：

- Qwen-first runtime 有了正式 repo 身份，不再只是本地试验目录
- 平台侧文档、manifest、agent governance 和评审清单都有了统一口径
- 账号级登录工作台的 owner 继续留在 runtime 本仓，而不是回流到根仓或上游控制面
- 后续把 runtime 接到 `new-api` 或 `CLIProxyAPIPlus` 时，边界更清楚

代价与边界：

- `proxy-platform` 只做纳管，不负责替 runtime 实现浏览器执行能力
- `webchat-openai-runtime` 仍需要自己维护 acceptance harness、runbook、warning feeds 和 live canary
- hosted tool execution 依旧默认关闭；如果后续要默认开启，需要单独 ADR 和审计面
