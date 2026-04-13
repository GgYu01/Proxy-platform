# ADR-0003: 保持 CliProxy-control-plane 作为 northbound 内核

## Status

Accepted

## Context

`CliProxy-control-plane` 已经拥有统一 `/v1` 网关、pool/group/worker 调度和 operator UI。

## Decision

`proxy-platform` 只集成和编排 control-plane，不重写其 northbound `/v1` 与 southbound worker 逻辑。

## Consequences

### Positive

- 避免第二控制面
- 降低功能重复与协议漂移风险

### Negative

- 平台壳需要设计清晰的 adapter 边界
