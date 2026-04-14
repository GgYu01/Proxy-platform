# Mutation Jobs 使用与维护说明

## 一句话结论

当前 `proxy-platform` 已经把主机增删、部署、摘除统一收敛成了 job contract，但真正允许 apply 的只有登记册变更，远端部署类动作仍然只到 dry-run。

## 运行前提

下面所有命令默认使用仓库本地虚拟环境 `.venv/bin/python`。

- 如果你当前实际使用的是别的解释器路径，例如 `.venv_fix/bin/python`，把命令里的解释器替换掉即可。
- `operator` 模式依赖 `repos/proxy_ops_private/` 中的私有登记册。
- 计划文件和审计记录会落在 `state/jobs/`，这是本地运行痕迹，不是提交到 Git 的源码目录。

## 它在当前项目里是什么

它不是远端执行引擎，也不是新的控制面内核。

在这个项目里，它更准确的定位是：

- 变更申请单格式
- 变更预演结果
- 变更审计记录
- Web/CLI 共用的统一入口

换句话说，它解决的是“先把平台允许的变更固定成可审、可追踪、可扩展的合同”，不是“现在就把所有远端动作都做掉”。

## 它解决什么问题

它主要解决三件事：

1. 让 reviewer 能一眼看清这次改动到底是登记册变更，还是未来的远端动作。
2. 让 Web 和 CLI 不再各自拼一套写操作逻辑。
3. 让后续接入 authority adapter 时，有固定的 plan / audit / apply 落点。

## 它不是什么

它不是：

- `remote_proxy` 生命周期脚本的替代品
- `Proxy_ops_private` 真相源的替代品
- 已经能直接 SSH apply 的远端部署面板

## 当前支持的 job kind

### 1. `add_host`

- 作用：把新主机加入登记册。
- apply：允许。
- executor：`inventory_only`

### 2. `remove_host`

- 作用：把主机从登记册移除。
- apply：允许。
- executor：`inventory_only`

### 3. `deploy_host`

- 作用：预演未来远端部署流程会走哪条 authority path。
- apply：当前禁止。
- executor：`not_configured`

### 4. `decommission_host`

- 作用：预演未来远端摘除流程会走哪条 authority path。
- apply：当前禁止。
- executor：`not_configured`

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

### 预演远端部署或摘除

```bash
.venv/bin/python -m proxy_platform jobs plan-deploy-host --mode operator --host-name lisahost
.venv/bin/python -m proxy_platform jobs plan-decommission-host --mode operator --host-name lisahost
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

页面上现在有三类操作：

- 新增主机计划
- 移除主机计划
- 对 deploy / decommission 做 dry-run
- 对已生成计划做显式 apply

页面下半部分会显示最近的审计事件。

当前页面不会在“生成计划”时自动一起 apply。apply 必须单独确认，并且计划文件必须位于 `state/jobs/plans/` 这块受管目录里。

另外，apply 现在还会额外检查三件事：

- 当前 manifest 仍然允许这类 job apply
- 当前 executor 没有和计划时发生漂移
- 同一个 `job_id` 没有已经执行过的 `applied` 审计

这意味着“旧计划越过新边界”以及“把已执行计划改回 planned 再重放”都不会通过。

## 当前怎么回退

### 登记册变更

当前允许 apply 的只有登记册变更，因此回退也只对这一层定义清楚：

- `add_host` 回退方式：再执行一次 `remove_host`
- `remove_host` 回退方式：再执行一次 `add_host`

### 远端动作

当前 `deploy_host` / `decommission_host` 还不能 apply，因此没有自动远端回退。

## 为什么现在不直接做远端 apply

现象：

- 平台已经有 Web 和 CLI 入口，看起来很像“下一步就应该直接远端部署”。

直接原因：

- 当前还没有 authority adapter，平台还不知道该用哪个受控入口去调用下游仓库。

根因：

- 这个仓库的角色是“薄平台壳”，不是新的控制面内核。它应该统一 job contract，而不是复制 `remote_proxy` 或私有仓库里的真实生命周期逻辑。

为什么以前没暴露：

- 在只有只读页面和文件入口的时候，边界压力还不明显；一旦开始加“部署按钮”，这个问题就会立刻暴露出来。

## 相关文档

- [ADR-0010-mutation-job-flow-boundary.md](/workspaces/proxy-platform/docs/adr/ADR-0010-mutation-job-flow-boundary.md)
- [operator-web-console.md](/workspaces/proxy-platform/docs/runbooks/operator-web-console.md)
- [mutation-job-flow.md](/workspaces/proxy-platform/docs/review-checklists/mutation-job-flow.md)
