# ADR-0013: public 只读视图消费脱敏快照，运行时副本通过 reviewed sync 回到 private truth 工作树

## Status

Accepted

## Context

到 `ADR-0012` 为止，`proxy-platform` 已经有了正式部署的 operator Web，也已经把 `.runtime-workspace` 和发布物拆开。

但这里还剩两条真正影响长期维护的桥：

- public 只读入口不能继续靠“public 模式临时穿透 private registry”来取数据；
- operator 页面改动落在 `.runtime-workspace` 之后，也不能再靠人工 `cp` 或肉眼对比去回写 `repos/proxy_ops_private`。

换句话说，当前真正要解决的问题不是“再加两个命令”，而是：

- 如何让 public 只读视图有稳定、可审计、不会泄露 private 字段的输入；
- 如何让运行时副本回到 private truth 工作树时，仍然保持薄平台壳边界，而不是演化成新的 Git 控制面。

## Decision

### 1. public 模式正式只消费脱敏快照

当前 public 只读入口固定消费两份文件：

- `state/public/host_console.json`
- `state/public/subscriptions.json`

在这个项目里，它们等于“对外只读现场板”。

它们回答的是：

- 哪些主机可以公开展示
- 当前公开订阅入口长什么样

它们不回答：

- 私有维护地址是什么
- SSH 怎么登陆
- 平台真相源原始 YAML 长什么样

### 2. public 快照必须从 operator 真相导出，而不是手写维护

当前正式入口是：

- `proxy_platform exports export-public`

也就是说，public 快照是 operator 真相和观测状态的派生结果，不是另起一套手工维护文件。

### 3. public 快照必须保持脱敏边界

当前 public host snapshot 只保留：

- `name`
- `provider`
- `deployment_topology`
- `runtime_service`
- `observed_health`
- `should_publish`
- `publish_reason`

当前不会带入：

- `host`
- `ssh_port`
- `base_port`
- `change_policy`

### 4. `.runtime-workspace` 回写 private truth 时必须先 plan 后 apply

当前正式入口是：

- `proxy_platform exports plan-sync-private`
- `proxy_platform exports apply-sync-private --confirm`

在这个项目里，这条链路等于“把线上运行时副本搬回本地私有工作树的受控移交单”。

它解决的是：

- 不再手工 copy inventory 文件
- 不再靠肉眼猜哪些行该覆盖
- 不再把运行时副本误当成 Git 真相源

### 5. private truth sync 当前只覆盖 inventory 文件

当前允许被 reviewed sync 覆盖的只有：

- `repos/proxy_ops_private/inventory/nodes.yaml`
- `repos/proxy_ops_private/inventory/subscriptions.yaml`

这份决定明确排除：

- secrets
- generated artifacts
- 自动 Git commit
- 自动 Git push

### 6. private truth sync 必须校验 source/target 漂移

`apply-sync-private` 当前必须同时满足：

- runtime source digest 没变
- target digest 没变
- 操作者显式确认 `--confirm`

如果中间有人改了任意一侧文件，旧 plan 失效，必须重新 plan。

## Consequences

### Positive

- public 模式终于有了正式输入，不再需要解释“为什么 public 可以临时读 private registry”。
- public 视图和 operator 真相之间的桥被固定成文件合同，reviewer 更容易判断有没有泄露 private 字段。
- `.runtime-workspace` 回写 private truth 有了明确入口，不再依赖手工 copy。
- private truth sync 继续保持“桥接层”定位，没有把 `proxy-platform` 变成 Git 自动提交控制面。

### Negative

- public 快照需要显式导出，不是每次变更后自动发布。
- private truth sync 目前只到本地工作树，不会自动 commit/push 到远端 Git 真相源。
- 如果 operator 和 private truth 在 plan/apply 之间分别发生变化，必须重新生成 sync plan。

## What This Is Not

这份决定不是：

- 允许 public 入口直接读取 private registry；
- 允许页面直接把 `.runtime-workspace` 自动推送到 private Git 仓库；
- 允许 `proxy-platform` 接管 private secrets 或生成物真相源。

## Related Decisions

- [ADR-0008-platform-state-model.md](/workspaces/proxy-platform/docs/adr/ADR-0008-platform-state-model.md)
- [ADR-0010-mutation-job-flow-boundary.md](/workspaces/proxy-platform/docs/adr/ADR-0010-mutation-job-flow-boundary.md)
- [ADR-0012-operator-web-infra-core-deployment.md](/workspaces/proxy-platform/docs/adr/ADR-0012-operator-web-infra-core-deployment.md)
