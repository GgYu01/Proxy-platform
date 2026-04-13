# ADR-0005: 采用 submodule pinning + manifest semantics

## Status

Accepted

## Context

仅用 submodule 无法表达 repo 角色、模式、visibility、optional/required 等平台语义；仅用 manifest 又缺少 Git 原生 pinning 和审计优势。

## Decision

采用 `git submodule` 固定依赖仓库版本，同时以 `platform.manifest.yaml` 描述角色、模式、可见性和默认路径。

## Consequences

### Positive

- 兼顾可审计性与平台语义表达
- 用户通过统一 CLI 使用，不需要直接理解底层细节

### Negative

- 需要同步维护 submodule 与 manifest
