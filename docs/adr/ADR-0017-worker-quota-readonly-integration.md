# ADR-0017: Worker quota view stays read-only and authority-owned

## Status

Accepted

## Context

`proxy-platform` 的 operator Web 需要让值守人员看到“每个远端 worker 对应不同 oauth 文件的最新配额和 probe 状态”。

这类数据已经由 `repos/cliproxy-control-plane` 通过权威接口暴露：

- `/api/accounts/latest-view`
- `/api/tactical-stats/overview`

如果在 `proxy-platform` 里重新实现 probe、quota 汇总或 worker/account 调度，就会把薄平台壳再次写成第二控制面。

## Decision

在 `proxy-platform` 的 operator Web 中新增只读 `worker-quotas` 视图，但保持下面三条边界：

- 数据权威继续留在 `cliproxy-control-plane`
- `proxy-platform` 只做 read-only 拉取、分组展示和 operator 导航入口
- 不在 `proxy-platform` 暴露 probe 刷新、quota 变更、worker 写操作或账号池治理入口

## Consequences

### Positive

- 满足 operator 对 worker/oauth 配额可见性的需求
- 保持 `proxy-platform` 的 thin-shell 边界
- 避免 duplicate probe logic、quota drift 和第二控制面问题

### Negative

- 页面可用性依赖 `cliproxy-control-plane` 权威接口可达
- 部署时需要额外配置 control-plane 只读连接参数
