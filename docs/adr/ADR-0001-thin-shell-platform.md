# ADR-0001: 使用薄平台壳而不是四仓硬合并

## Status

Accepted

## Context

现有能力分布在四个仓库中，但真实职责边界已经形成。问题在于缺少统一入口与正式编排层，而不是缺少一个新的全量核心仓库。

## Decision

建立 `proxy-platform` 作为薄平台壳仓库，只负责统一入口、manifest、adapter、job schema 与平台治理文档。

## Consequences

### Positive

- 统一用户入口
- 保留现有边界
- 支持后续渐进式接入 Web / job runner

### Negative

- 平台壳必须严格防止演变为重复控制面
