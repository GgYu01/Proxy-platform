# ADR-0011: 远端部署进入 authority handoff 合同，operator Web 暂不直接上线

## Status

Accepted

## Context

前两个阶段已经把 `proxy-platform` 收敛成薄平台壳：

- 它已经有统一的主机登记册、观测回报和订阅派生模型；
- 它已经有统一的 `job plan -> audit -> apply` 合同；
- 它已经有本地 operator Web 控制台。

但到第三阶段，出现了一个不能再回避的问题：

- 用户要的是“远端可部署、可维护、可审计”的平台能力；
- 现有下游 authority 仍然在 `remote_proxy` 和 `infra_core`；
- 当前仓库如果直接接 SSH 和远端生命周期脚本，就会滑成第二控制面。

换句话说，现在最需要固定的不是“再多一个按钮”，而是“平台层把远端动作交接给谁、以什么格式交接、交接之后谁负责执行和回退”。

## Decision

### 1. `deploy_host` / `decommission_host` 的 `apply` 改为 authority handoff

当前这两类 job 的 `apply` 不再表示“平台已经执行了远端动作”，而是表示“平台已经生成了正式移交单”。

也就是说：

- `inventory_only` 的 `apply`
  直接改登记册。
- `authority_handoff` 的 `apply`
  只负责生成 `state/jobs/handoffs/<job>.yaml`。

### 2. authority adapter 进入 manifest，成为平台合同的一部分

平台现在把下游 authority 入口显式写进 manifest，而不是散在 runbook 或人工口头说明里。

当前 adapter 至少要写清楚：

- 适用的 `job_kind`
- 适用拓扑，例如 `standalone_vps` / `infra_core_sidecar`
- 下游 owner repo
- 入口类型，是 `service_script` 还是 `runbook_only`
- downstream entrypoint
- 本地 review prerequisite，也就是平台壳在生成移交单前必须真实看到的 repo/path/env
- downstream execution prerequisite，也就是真正执行方现场还要再确认的路径
- rollback owner 与 rollback hint

### 3. 拓扑明确拆成两类，不再混用

#### `standalone_vps`

- authority 仍然在 `remote_proxy`
- `deploy_host` 当前 handoff 到 `./scripts/service.sh cliproxy-plus install`
- `decommission_host` 当前仍是 runbook 型 handoff，因为下游没有统一 decommission 命令

#### `infra_core_sidecar`

- compose 生命周期 authority 仍然在 `infra_core`
- `proxy-platform` 只能把 operator 引到 `repos/remote_proxy/docs/deploy/infra-core-ubuntu-online.md`
- `/mnt/hdo/infra-core` 被记录为 downstream execution prerequisite，不再误伤本地 apply
- 明确禁止在 `/mnt/hdo/infra-core` 里直接跑 `remote_proxy/install.sh`

### 4. operator Web 继续保持本地控制台，不在本 ADR 中直接上线公网

当前 operator Web 已经有价值，但它依赖私有登记册，也没有正式认证和发布入口。

因此本 ADR 明确：

- 当前 Web 是本地 operator 控制台
- 当前没有正式公网域名
- 当前不做“直接发布上线”的承诺
- 真正上线前，必须再补一份部署 ADR，明确运行面、认证入口和发布 owner

### 5. 固定发布物与回退策略

对于未来正式上线的 operator Web，优先选择固定发布物，而不是直接让远端环境自由安装源码依赖。

当前先固定策略，不在本阶段直接落远端部署：

- 发布物原则：固定、可复现、可审计
- 回退原则：优先受控回退；若自动回退条件不足，必须保留人工回退说明和明确 owner

## Consequences

### Positive

- 平台 finally 有了正式的远端移交合同，而不是继续停留在“dry-run 说明文字”。
- reviewer 能先审 adapter 和移交单，再决定是否允许远端执行。
- `remote_proxy` / `infra_core` 的 authority 继续成立。
- 站在 operator 视角，当前每类远端动作下一步去哪执行已经有固定答案。

### Negative

- `deploy_host` / `decommission_host` 虽然现在允许 `apply`，但这不等于远端部署已经完成。
- 当前仍然没有正式公网域名。
- `standalone_vps` 的 decommission 还没有统一脚本，只能先走 runbook 型 handoff。

## What This Is Not

这份决定不是：

- 把 `proxy-platform` 做成新的 SSH 控制面；
- 把 `remote_proxy` 的生命周期逻辑搬进当前仓库；
- 宣布当前 operator Web 已经完成正式上线。

## Related Decisions

- [ADR-0001-thin-shell-platform.md](/workspaces/proxy-platform/docs/adr/ADR-0001-thin-shell-platform.md)
- [ADR-0009-repository-ownership-matrix.md](/workspaces/proxy-platform/docs/adr/ADR-0009-repository-ownership-matrix.md)
- [ADR-0010-mutation-job-flow-boundary.md](/workspaces/proxy-platform/docs/adr/ADR-0010-mutation-job-flow-boundary.md)
