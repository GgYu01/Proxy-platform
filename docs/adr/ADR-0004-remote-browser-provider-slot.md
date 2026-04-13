# ADR-0004: 为 remote_browser 预留 provider 插槽

## Status

Accepted

## Context

`remote_browser` 目前不属于代理主链核心，但属于可部署远端工作负载的一种实现。

## Decision

第一阶段不将 `remote_browser` 纳入核心主链流程，但在 manifest 和 adapter 层预留正式 provider 插槽。

## Consequences

### Positive

- 不打乱主链收敛
- 为后续 provider 扩展保留正式挂点

### Negative

- 首阶段用户仍需通过平台壳外的运行时说明完成 browser 实际部署
