# ADR-0006: CLIProxyAPIPlus Worker 升级仍由 remote_proxy 生命周期脚本负责

## Status

Accepted

## Context

`proxy-platform` 是统一入口薄平台壳，但 `CLIProxyAPIPlus` worker 的真实部署、版本切换与宿主机状态边界仍然落在 `remote_proxy`。

现网调查显示：

- worker 运行形态是 `systemd + podman`，不是 `docker compose`；
- OAuth / auth 文件、`config.yaml`、日志目录通过 bind mount 保存在宿主机 `state/cliproxy-plus/`；
- usage 统计不是自动持久化数据库，而是进程内存聚合，需要在重建前后显式做 `/usage/export` 与 `/usage/import`。

如果平台壳直接接管 live service 文件修改，或者把远端热改当成长期入口，会破坏“薄平台壳 + 下游真相源”的边界。

## Decision

保留以下职责分工：

- `proxy-platform`
  只负责统一帮助、repo 编排、toolchain 诊断、runbook 与 ADR。
- `remote_proxy`
  继续作为 `cliproxy-plus` 的部署真相源，负责：
  - 生成 `config.yaml`
  - 生成 Quadlet / fallback systemd service
  - 执行 `update` / `switch-version`
  - 在重建前后执行 usage 备份恢复

升级 worker 的标准路径是：

1. 本地修改并评审 `remote_proxy` 仓库中的镜像版本或生命周期脚本。
2. 将远端主机同步到该已评审版本。
3. 在远端执行 `remote_proxy` 的生命周期命令，而不是手工改 `/etc/systemd/system/cliproxy-plus.service`。

## Consequences

### Positive

- 平台壳不会滑向第二个控制面。
- worker 升级路径有单一真相源。
- OAuth / config / logs 与 usage 保护路径的责任边界清晰。
- 后续 Web/CLI 只需要编排下游命令，不需要复制其部署细节。

### Negative

- 平台壳短期内只能提供指导、诊断和编排，不能直接替代下游生命周期脚本。
- 远端主机如果长期停留在旧版 `remote_proxy` 工作树，仍可能错过新的安全升级逻辑，因此需要明确的 repo 同步步骤。
