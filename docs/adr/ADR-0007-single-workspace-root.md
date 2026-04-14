# ADR-0007: 统一使用 /workspaces/proxy-platform 作为单根工作区

## Status

Accepted

## Context

此前平台相关仓库散落在多个父路径下：

- `proxy-platform`、`remote_proxy`、`proxy_ops_private` 位于 `/workspaces/proxy_own/`
- 活跃的 `cliproxy-control-plane` 位于 `/workspaces/temp/cliproxy-control-plane`
- `multi_repo_arch_analysis/` 下还保留了分析副本

这种布局虽然短期可用，但会带来三个持续性问题：

1. 平台壳 manifest 指向的 `local_override_path` 与真实活跃工作树不一致。
2. 用户和 agent 无法快速判断哪个路径才是权威入口。
3. 分析副本、临时目录和真实源码目录混放，容易让文档、脚本和自动化流程引用错误路径。

## Decision

统一将 `/workspaces/proxy-platform` 设为平台唯一权威根：

- 平台壳仓库自身位于 `/workspaces/proxy-platform`
- 所有权威下游仓库收敛到 `/workspaces/proxy-platform/repos/`
- 分析副本和历史临时材料收敛到 `/workspaces/proxy-platform/archive/`

迁移策略如下：

- 非权威旧路径中的计划、日志和历史材料归档到 `archive/`
- 旧兼容路径在迁移完成后直接移除
- 文档、manifest、help 输出和后续自动化一律以新根为准

## Consequences

### Positive

- 用户与 agent 都只有一个明确入口。
- `platform.manifest.yaml` 可以直接表达真实权威路径。
- `repos/` 与 `archive/` 的职责边界清晰，降低误用分析副本的风险。
- 后续实现真正的 repo-of-repos materialization 时，不需要再次调整工作区语义。

### Negative

- 需要一次性整理现有本地目录并清理旧路径引用。
- 一些 shell 历史、临时脚本和外部文档如果仍引用旧路径，需要手工更新。
