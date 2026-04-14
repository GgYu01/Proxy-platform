# ADR-0008: 平台状态采用“主机登记册 + 观测回报 + 派生视图”

## Status

Accepted

## Context

当前 `proxy-platform` 只有工作区仓库盘点和宿主机 toolchain 诊断能力，还没有正式的平台状态模型。

这导致三个长期问题：

- 页面显示、订阅生成和远端健康判断没有统一依据。
- `remote_proxy` 与 `Proxy_ops_private` 容易各自带一点平台逻辑，边界继续漂移。
- 后续 Web / job runner / probe / local provider lifecycle 没有共同对象模型。

## Decision

平台状态统一拆成三层：

1. 主机登记册
   平台认可的“现场清单”，回答“哪些主机应当存在于平台视野里”。
2. 观测回报
   probe 或远端 agent 提供的“现场观测”，回答“这些主机现在实际是什么状态”。
3. 派生视图
   页面展示、订阅成员、后续 job 入口都只从前两层派生，不再自己维护另一份真相。

首批状态语义如下：

- 期望状态只区分 `enabled` / `disabled`
- 观测状态只区分 `healthy` / `degraded` / `down` / `unknown`
- 订阅包含规则默认只看登记册是否启用、是否允许进入订阅
- 观测状态影响页面标记和审计，不自动把主机从订阅里移除
- 第一阶段所有直接读取私有登记册的视图都只在 `operator` 模式开放；`public` 模式未来只能消费脱敏后的派生状态源，不能直接越过 private 边界读取登记册

## Consequences

### Positive

- 订阅文本、页面列表和健康聚合都降级为“派生结果”，不再冒充原始真相。
- `Proxy_ops_private` 可以继续保存私有现场事实，而共享判断逻辑回到 `proxy-platform`。
- 后续引入 Web、probe、job schema 和本地 provider supervisor 时有统一落点。

### Negative

- 需要补新的状态 schema、只读 CLI、测试和文档。
- 后续接入远端写操作前，必须先把审计和 job schema 补齐。
