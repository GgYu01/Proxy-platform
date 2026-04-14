# Mutation Jobs 使用与维护说明

## 一句话结论

当前 `proxy-platform` 已经把主机增删和远端部署类动作统一收敛进 `job plan -> audit -> apply` 合同，其中远端类 `apply` 现在生成的是正式 authority handoff 移交单，不是页面或 CLI 直接 SSH 执行。

## 运行前提

下面所有命令默认使用仓库本地虚拟环境 `.venv/bin/python`。

- 如果你当前实际使用的是别的解释器路径，例如 `.venv_fix/bin/python`，把命令里的解释器替换掉即可。
- `operator` 模式依赖 `repos/proxy_ops_private/` 中的私有登记册。
- 计划文件、审计记录和移交单都会落在 `state/jobs/`，这是本地运行痕迹，不是提交到 Git 的源码目录。

## 它在当前项目里是什么

它不是远端执行引擎，也不是新的控制面内核。

在这个项目里，它更准确的定位是：

- 变更申请单格式
- 变更预演结果
- 变更审计记录
- 远端 authority handoff 移交单
- Web/CLI 共用的统一入口

换句话说，它解决的是“先把平台允许的变更固定成可审、可追踪、可扩展的合同”，不是“现在就把所有远端动作都直接做掉”。

## 它解决什么问题

它主要解决四件事：

1. 让 reviewer 能一眼看清这次改动到底是登记册变更，还是远端部署申请。
2. 让 Web 和 CLI 不再各自拼一套写操作逻辑。
3. 让远端部署类动作先有稳定的移交单，而不是继续靠口头约定或临时命令。
4. 让后续真正接远端执行器时，新增的是 adapter，不是重写整套平台语义。

## 它不是什么

它不是：

- `remote_proxy` 生命周期脚本的替代品
- `Proxy_ops_private` 真相源的替代品
- 已经能直接 SSH apply 的远端部署面板
- 已经完成正式上线的公网运维站点

## 当前支持的 job kind

### 1. `add_host`

- 作用：把新主机加入登记册。
- apply：允许。
- executor：`inventory_only`
- 效果：修改 `repos/proxy_ops_private/inventory/nodes.yaml` 并写审计。

### 2. `remove_host`

- 作用：把主机从登记册移除。
- apply：允许。
- executor：`inventory_only`
- 效果：修改登记册并写审计。

### 3. `deploy_host`

- 作用：为远端部署生成正式移交单。
- apply：允许。
- executor：`authority_handoff`
- 效果：把 reviewed plan 转成 `state/jobs/handoffs/<job>.yaml`。

### 4. `decommission_host`

- 作用：为远端摘除生成正式移交单。
- apply：允许。
- executor：`authority_handoff`
- 效果：生成 runbook 型移交单，明确后续要去哪条 authority path。

## 当前 authority handoff 适配层

### `remote_proxy_cliproxy_plus_standalone`

- 它是什么：独立 VPS 的 `cliproxy-plus` 生命周期移交单。
- 它解决什么：告诉 downstream owner 应该在 `remote_proxy` 仓库根目录执行 `./scripts/service.sh cliproxy-plus install`。
- 它不是什么：不是平台自己执行 install。

### `remote_proxy_cliproxy_plus_standalone_decommission`

- 它是什么：独立 VPS 的摘除移交单。
- 它解决什么：告诉 operator 去看 `repos/remote_proxy/docs/deploy/cliproxy-plus-standalone-vps.md`，按受控 runbook 做清理。
- 它不是什么：不是已经具备统一 decommission shell 命令。

### `remote_proxy_cliproxy_plus_infra_core_sidecar`

- 它是什么：`infra_core_sidecar` 拓扑的移交单。
- 它解决什么：明确要求 operator 去看 `repos/remote_proxy/docs/deploy/infra-core-ubuntu-online.md`，并把 compose 生命周期继续留在 `infra-core`；`/mnt/hdo/infra-core` 会作为 downstream execution prerequisite 被写进移交单，而不是误伤本地 apply。
- 它不是什么：不是让人在 `/mnt/hdo/infra-core` 里直接跑 `install.sh`。

## CLI 用法

### 新增主机

```bash
.venv/bin/python -m proxy_platform jobs plan-add-host --mode operator --spec ./host.yaml
.venv/bin/python -m proxy_platform jobs apply --mode operator --plan-file ./state/jobs/plans/<job>.json --confirm
```

### 移除主机

```bash
.venv/bin/python -m proxy_platform jobs plan-remove-host --mode operator --host-name vmrack1
.venv/bin/python -m proxy_platform jobs apply --mode operator --plan-file ./state/jobs/plans/<job>.json --confirm
```

### 生成远端部署移交单

```bash
.venv/bin/python -m proxy_platform jobs plan-deploy-host --mode operator --host-name lisahost
.venv/bin/python -m proxy_platform jobs apply --mode operator --plan-file ./state/jobs/plans/<deploy-job>.json --confirm
```

### 生成远端摘除移交单

```bash
.venv/bin/python -m proxy_platform jobs plan-decommission-host --mode operator --host-name lisahost
.venv/bin/python -m proxy_platform jobs apply --mode operator --plan-file ./state/jobs/plans/<decommission-job>.json --confirm
```

### 查看审计

```bash
.venv/bin/python -m proxy_platform jobs audit-list --mode operator
```

## Web 用法

本地启动：

```bash
.venv/bin/python -m proxy_platform web --mode operator --host 127.0.0.1 --port 8765
```

本地访问：

```text
http://127.0.0.1:8765/
```

页面上现在有四类操作：

- 新增主机计划
- 移除主机计划
- deploy/decommission 移交单计划
- 对已生成计划做显式 apply

页面下半部分会显示最近的审计事件。

当前页面不会在“生成计划”时自动一起 apply。apply 必须单独确认，并且计划文件必须位于 `state/jobs/plans/` 这块受管目录里。

## `apply` 到底会做什么

### 对 `inventory_only`

- 写登记册
- 写审计
- 不涉及远端宿主机

### 对 `authority_handoff`

- 重新校验当前 manifest、authority contract 和本地 review prerequisite 没有漂移或缺失
- 如果 adapter 声明了 `downstream_required_paths`，把这些执行现场前提写进 handoff，交给真正执行方复核
- 生成 `state/jobs/handoffs/<job>.yaml`
- 写 `applied` 审计
- 不直接远端执行

换句话说，当前 `authority_handoff` 的 `apply` 结果是“移交单落地”，不是“远端部署已完成”。

## 当前怎么回退

### 登记册变更

- `add_host` 回退方式：再执行一次 `remove_host`
- `remove_host` 回退方式：再执行一次 `add_host`

### 远端部署类动作

当前回退 owner 仍然在下游 authority。

- `standalone_vps`
  当前 rollback owner 是 `remote_proxy`。
- `infra_core_sidecar`
  当前 rollback owner 是 `infra_core`。

也就是说，平台壳当前只负责把 rollback owner 和 rollback hint 写进移交单，还不负责替你在远端自动回退。

## 为什么现在不直接做远端执行

现象：

- 平台已经有 Web 和 CLI 入口，看起来很像“下一步就应该直接远端部署”。

直接原因：

- 远端真实执行脚本还在 `remote_proxy` 或 `infra_core`，平台仓库只掌握合同，不掌握宿主机生命周期 authority。

根因：

- 这个仓库的角色是“薄平台壳”，不是新的控制面内核。它应该统一 job contract 和移交语义，而不是复制 `remote_proxy` 或私有仓库里的真实生命周期逻辑。

为什么以前没暴露：

- 在只有只读页面和登记册变更时，远端 authority 问题还不明显；一旦开始加“部署按钮”，这个边界问题就必须正式落地。

## 相关文档

- [ADR-0010-mutation-job-flow-boundary.md](/workspaces/proxy-platform/docs/adr/ADR-0010-mutation-job-flow-boundary.md)
- [ADR-0011-authority-handoff-and-operator-deployment.md](/workspaces/proxy-platform/docs/adr/ADR-0011-authority-handoff-and-operator-deployment.md)
- [operator-web-console.md](/workspaces/proxy-platform/docs/runbooks/operator-web-console.md)
- [authority-handoff.md](/workspaces/proxy-platform/docs/runbooks/authority-handoff.md)
- [mutation-job-flow.md](/workspaces/proxy-platform/docs/review-checklists/mutation-job-flow.md)
