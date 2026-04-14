# Authority Handoff 使用说明

## 一句话结论

authority handoff 是 `proxy-platform` 给下游 authority 仓库或宿主机 owner 生成的正式移交单，它解决的是“下一步应该走哪条受控入口”，不是“平台已经代你执行完远端动作”。

## 在当前项目里它代表什么

在这个项目里，它等于一张“远端变更移交单”。

这张单子会把 reviewer 最关心的东西一次性写清楚：

- 这是哪个 job
- 目标主机是谁
- 目标拓扑是什么
- 要交给哪个下游 repo
- 应该走哪条入口或 runbook
- 需要哪些环境文件和关键参数
- 回退 owner 是谁

换句话说，它把“远端下一步动作”从口头说明，变成一个有路径、有责任边界、有审计关联的正式产物。

## 它是什么、解决什么、不是什么

### 它是什么

- reviewed plan 的派生产物
- 下游 authority 的执行说明单
- 回退 owner 和责任边界说明

### 它解决什么

- 避免页面和 CLI 各自输出一套不一致的远端操作说明
- 避免 operator 在“standalone-vps”和“infra-core-sidecar”之间混用脚本
- 让 reviewer 能先审移交合同，再决定是否真的去远端执行

### 它不是什么

- 不是实际部署结果
- 不是 secrets 真相源
- 不是正式公网站点的发布物

## 当前移交单长什么样

当前移交单会落在：

```text
state/jobs/handoffs/<job-id>.yaml
```

里面至少会有这些字段：

- `job_id`
- `job_kind`
- `host`
- `adapter`
- `required_paths`
- `required_env_files`
- `required_env_keys`
- `downstream_required_paths`
- `recommended_command`
- `rollback_owner`
- `rollback_hint`
- `review_steps`

## 操作流程

### 1. 先生成计划

```bash
.venv/bin/python -m proxy_platform jobs plan-deploy-host --mode operator --host-name lisahost
```

### 2. 审计划，而不是直接执行

重点看三件事：

- 目标主机和拓扑是不是对的
- adapter 指向的下游入口是不是对的
- rollback owner 和 hint 是否足够清楚

### 3. 显式 apply，生成移交单

```bash
.venv/bin/python -m proxy_platform jobs apply --mode operator --plan-file ./state/jobs/plans/<job>.json --confirm
```

这一步在当前阶段不是“直接远端执行”，而是“通过最终闸门后才允许落移交单”。

apply 前会重新校验：

- 当前 authority contract 没有变化
- 下游 entrypoint 仍然存在
- 本地 review prerequisite，也就是 `required_paths` / `required_env_files`，仍然满足

如果 handoff 里带了 `downstream_required_paths`，它表示“真正执行方现场必须再确认的路径”，会写进移交单和 review steps，但不会被误当成本地 apply 阻塞项。

### 4. 到下游 authority 去执行

- 如果是 `service_script` 型 handoff，就去对应 repo 根目录执行推荐命令。
- 如果是 `runbook_only` 型 handoff，就按 runbook 做受控操作。

## 当前三类 adapter 的后续动作

### `remote_proxy_cliproxy_plus_standalone`

- downstream owner：`remote_proxy`
- topology：`standalone_vps`
- handoff method：`service_script`
- 典型命令：`./scripts/service.sh cliproxy-plus install`

### `remote_proxy_cliproxy_plus_standalone_decommission`

- downstream owner：`remote_proxy`
- topology：`standalone_vps`
- handoff method：`runbook_only`
- 原因：下游还没有统一 decommission 脚本

### `remote_proxy_cliproxy_plus_infra_core_sidecar`

- downstream owner repo：`remote_proxy`
- topology：`infra_core_sidecar`
- handoff method：`runbook_only`
- 本地 apply 前提：只要求 `remote_proxy` 的 runbook 审阅面存在
- downstream execution prerequisite：`/mnt/hdo/infra-core`
- 关键限制：不要在 `/mnt/hdo/infra-core` 里直接跑 `install.sh`
- 责任边界：handoff surface 放在 `remote_proxy` 的 runbook，但实际 compose lifecycle owner 仍然是 `infra_core`

## 当前边界

当前平台壳只负责三件事：

- 生成计划
- 生成审计
- 生成移交单

当前平台壳不负责：

- 直接 SSH 到远端执行
- 在远端替你做自动回退
- 保存远端真实运行时 secrets

## 维护建议

- 新增 adapter 前，先补 ADR。
- 新增 adapter 时，先补 manifest 校验和最小测试。
- 如果下游 authority 入口变化，先改 adapter，再改 runbook，不要只改 README 口头说明。
