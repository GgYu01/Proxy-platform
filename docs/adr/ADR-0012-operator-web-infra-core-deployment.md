# ADR-0012: Operator Web 以 infra-core 独立模块正式部署，运行态与发布物分离

## Status

Accepted

## Context

到 `ADR-0011` 为止，`proxy-platform` 已经把远端动作收敛成了 authority handoff 合同，也已经有本地 operator Web 控制台。

但项目里仍然有一个空档：

- 用户已经不是要“本地演示页”，而是要真正可访问、可维护、可回看的远端 operator 站点；
- 当前页面依赖私有主机登记册，又会产生计划、审计和移交单；
- 如果把这些运行态文件直接放在模块代码目录里，下一次重新部署就会把现场数据覆盖掉；
- 如果直接让远端宿主机自由装源码依赖，发布物就不稳定，也不利于回退。

换句话说，当前真正要解决的问题不是“怎么再加个按钮”，而是“怎样把 operator Web 正式挂到 `infra-core`，同时不破坏薄平台壳边界、不覆盖运行态数据、还能保留可回退的发布物”。

## Decision

### 1. operator Web 以 `infra-core` 独立模块方式正式部署

当前正式部署目标固定为：

- 宿主机：`gaoyx@112.28.134.53:52117`
- 模块根：`/mnt/hdo/infra-core/modules/proxy-platform-operator`
- 主入口：`https://proxy-platform-operator.svc.prod.lab.gglohh.top:27111/`

这里的“正式部署”指的是远端可访问、带认证、可维护的 operator 工作台，不是匿名公网门户。

### 2. 运行时工作区和发布物必须分开

模块运行面拆成三层：

- `/app`
  固定发布物。这里存放当前版本代码和 manifest。
- `.runtime-seed`
  首次部署或人工刷新时使用的最小 seed，包括：
  - 主机登记册
  - 订阅策略
  - authority review surface
- `.runtime-workspace`
  线上站点真正读写的工作区，包括：
  - 主机登记册副本
  - 计划
  - 审计
  - handoff

这样设计的直接目的，是防止 redeploy 把线上 operator 正在使用的工作区覆盖掉。

这里进一步细分成两类同步规则：

- operator 现场清单
  例如 `nodes.yaml`、`subscriptions.yaml`，保留 `.runtime-workspace` 里的运行态副本，不在 redeploy 时静默覆盖。
- authority review surface
  例如 `remote_proxy` 的脚本、env 模板和部署 runbook，每次启动都允许从 `.runtime-seed` 刷新到 `.runtime-workspace`，避免移交单继续引用过期模板。

### 3. 发布物固定为带版本标签的 OCI 镜像

部署脚本现在会在远端构建并写入固定镜像标签，例如：

- `proxy-platform-operator:a196b0143559`

这比“每次起容器都在线装依赖”更稳定，也为后续回退提供了清晰锚点。

### 4. operator Web 必须带认证入口，健康检查免认证

远端站点现在强制使用 HTTP Basic Auth。

- 页面和业务 API 需要认证
- `/health` 免认证

而且这里不是“尽量带认证”，而是“缺认证就拒绝启动”。

也就是说，正式部署运行入口必须 fail-closed，不能因为只少一个环境变量就降级成匿名站点，也不能接受仓库里已知的示例密码直接上线。

这解决的是“可以被值守系统探活”，同时不会把私有 operator 入口裸露出去。

### 5. redeploy 不得覆盖远端 `.env`

远端模块 `.env` 保存的是线上真实密码、域名、端口和镜像入口策略。

因此，部署脚本在重发模块时必须保留 `.env`，不能把它当作“每次都可以重新生成”的临时文件。

这解决的是两个风险：

- 避免把真实口令重置回示例值
- 避免因为 `.env` 被删除而触发错误配置上线

### 6. 正式上线后仍然保持 authority handoff 边界

即使页面已经远端可访问，当前 `deploy_host` / `decommission_host` 的 `apply` 语义仍然不变：

- `add_host` / `remove_host`
  允许修改运行时工作区里的登记册副本。
- `deploy_host` / `decommission_host`
  只生成 authority handoff 移交单。

也就是说，上线的是“受控工作台”，不是“第二控制面”。

### 7. 回退以“模块发布物回退”为主，宿主机生命周期回退仍属下游 owner

当前模块部署提供两种人工回退抓手：

- 回切上一版镜像标签
- 恢复 `.deploy-backups/` 下的模块源码快照

但远端代理节点本身的回退 owner 仍然是：

- `standalone_vps` -> `remote_proxy`
- `infra_core_sidecar` -> `infra_core`

## Consequences

### Positive

- operator Web 不再只是本地演示，而是有了正式的远端访问入口。
- redeploy 和运行态数据分开后，平台工作区不会在发版时被覆盖。
- redeploy 时保留 `.env` 后，线上口令和域名不会因为模块重发被重置。
- authority review surface 自动刷新后，下游 `remote_proxy` 模板更新能更快体现在 handoff 上。
- `/health` 只保留最小探活输出后，公网探活面不再额外暴露运行模式和工作区路径。
- reviewer 现在能同时检查：
  - 发布物
  - 认证入口
  - 运行态布局
  - handoff 边界
- `/health` 与 Basic Auth 分离后，监控和人工登录都更清晰。

### Negative

- 当前运行时工作区不会自动 Git commit / push 回 `Proxy_ops_private` 远端真相源；目前只提供 reviewed sync-back 到本地工作树，不提供自动上游提交。
- `18082` 直连端口虽然在宿主机内可用，但当前外部网络策略没有放通，所以主要入口仍然是域名 + `27111`。
- 当前已经有默认关闭、显式开启的 `redeploy_with_rollback.sh` 可选入口，但它仍然属于“部署失败后自动回切模块发布物”的有限回退，不等于完整的一键回退编排。

## What This Is Not

这份决定不是：

- 把 `proxy-platform` 升级成直接 SSH 的控制面；
- 让平台替代 `remote_proxy` / `infra_core` 的宿主机 authority；
- 把线上 operator 工作区误当成可以随 redeploy 覆盖的临时缓存。

## Related Decisions

- [ADR-0011-authority-handoff-and-operator-deployment.md](/workspaces/proxy-platform/docs/adr/ADR-0011-authority-handoff-and-operator-deployment.md)
- [ADR-0008-platform-state-model.md](/workspaces/proxy-platform/docs/adr/ADR-0008-platform-state-model.md)
- [ADR-0009-repository-ownership-matrix.md](/workspaces/proxy-platform/docs/adr/ADR-0009-repository-ownership-matrix.md)
- [ADR-0013-public-snapshot-and-private-truth-sync.md](/workspaces/proxy-platform/docs/adr/ADR-0013-public-snapshot-and-private-truth-sync.md)
