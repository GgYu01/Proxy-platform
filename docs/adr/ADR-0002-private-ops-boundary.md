# ADR-0002: 保持 Proxy_ops_private 作为私有真相源

## Status

Accepted

## Context

`Proxy_ops_private` 负责 inventory、secrets、generated artifacts 与 rollout/apply/check 脚本，这些内容不应进入公开平台壳仓库。

## Decision

继续保持 `Proxy_ops_private` 私有独立，通过 manifest 与 adapter 接入，而不是复制内容到 `proxy-platform`。

## Consequences

### Positive

- 保护 private/public 边界
- 维持运维真相源唯一性

### Negative

- 需要额外的 operator mode 检测与帮助系统
