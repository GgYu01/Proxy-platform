# Operator Web Console 使用与维护说明

## 一句话结论

当前 `proxy-platform` 的 Web 控制台已经可以在本地启动并使用，但本轮还没有做远端正式部署，所以现在没有一个可直接访问的线上域名。

## 运行前提

下面所有命令都默认使用仓库本地虚拟环境 `.venv/bin/python`。

- 如果你当前实际使用的是别的解释器路径，例如 `.venv_fix/bin/python`，把命令里的解释器替换掉即可。
- 如果你要打开 `operator` 模式页面，`repos/proxy_ops_private/` 必须已经在当前工作区可用。
- 页面运行时生成的计划和审计会落在 `state/jobs/`，这属于本地运行痕迹，不是要提交到 Git 的源码目录。

## 它在当前项目里是什么

这不是新的控制面站点，也不是已经接上远端部署按钮的运维后台。

在当前项目里，它更准确的定位是：

- 平台现场清单查看页
- 订阅入口查看页
- 本地 provider 生命周期查看页
- 主机登记册 mutation job 入口
- 最近一次 mutation audit 查看页

换句话说，它现在解决的是“两件事”: 一是看清楚当前平台登记册、观测状态和订阅派生结果；二是把主机增删先收敛成可审阅的 plan/apply/audit 流程。它仍然不是“已经可以直接在页面里下发远端部署”。

## 当前上线状态

- 已完成：本地可运行的最小 Web 控制台
- 已完成：`/api/hosts`、`/api/subscriptions`、`/api/providers`
- 已完成：页面内复制订阅链接按钮
- 已完成：基于 job plan/apply 的主机增删入口
- 已完成：`/api/jobs/plan`、`/api/jobs/apply`、`/api/jobs`
- 已完成：inventory-only executor 的本地审计记录
- 未完成：远端正式部署
- 未完成：公网域名接入
- 未完成：受控远端 authority adapter
- 未完成：远端 deploy/decommission 的真正 apply

因此，当前没有“应该访问哪个线上域名”的答案。

如果只想本地查看，当前访问地址是：

- `http://127.0.0.1:8765/`

## 本地启动方式

在仓库根目录执行：

```bash
.venv/bin/python -m proxy_platform web --mode operator --host 127.0.0.1 --port 8765
```

然后在本机浏览器打开：

```text
http://127.0.0.1:8765/
```

说明：

- 必须使用 `--mode operator`
  因为当前页面读取的是 `repos/proxy_ops_private` 中的私有登记册。
- 当前不建议把这个本地服务直接暴露到公网
  因为它还处于本地 operator 阶段，只完成了状态查看和登记册级 mutation job 入口。

## 页面里能看到什么

### 1. 主机现场清单

页面会显示：

- 主机名
- provider
- 当前观测状态
- 是否进入订阅

这部分回答的是“平台现在把哪些主机当成现场清单，它们目前被怎么看见”。

### 2. 订阅入口

页面会显示：

- 多节点订阅 URL
- 多节点 Hiddify 导入链接
- 每个节点的单节点订阅 URL
- 每个节点的 Hiddify 导入链接

这部分是派生结果，不是原始真相。

原始真相仍然在：

- `repos/proxy_ops_private/inventory/nodes.yaml`
- `repos/proxy_ops_private/inventory/subscriptions.yaml`

### 3. 本地 provider 生命周期

页面会显示 manifest 里声明的本地 provider 启动预算，例如：

- 启动超时
- 请求超时
- 启动尝试次数
- 请求尝试次数

这部分回答的是“本机侧 provider 怎么起、允许慢多久、失败后重试几次”。

### 4. mutation job 与审计

页面现在还能看到：

- 主机新增作业入口
- 主机移除作业入口
- deploy / decommission 的 dry-run 入口
- 最近一次审计事件

这部分回答的是“当前平台允许哪些变更先进入 job contract，以及这些变更有没有留下审计痕迹”。

## 当前按钮会做什么，不会做什么

当前页面上的作业按钮：

- 会先生成 plan
- 会写 audit 事件
- plan 文件会落在 `state/jobs/plans/`
- 对 `add_host` / `remove_host` 会在确认后修改 inventory 文件
- 不会自动 SSH 到远端
- 不会自动部署代理
- 不会自动摘除远端服务

换句话说，现在它是“受控 job 入口”，不是“远端执行入口”。

另外，页面已经改成显式两步：

1. 先生成计划
2. 再由用户确认并 apply 该计划

它不会再在同一个按钮里偷偷把 apply 一起做掉。

这是故意这样设计的。因为在这个项目里，远端 mutation 必须继续委托给 authority repo，平台壳只能先把 plan、audit、审批语义固定下来，不能直接滑成第二控制面。

## 日常维护怎么做

### 看当前状态

```bash
.venv/bin/python -m proxy_platform hosts list --mode operator
.venv/bin/python -m proxy_platform subscriptions list --mode operator
.venv/bin/python -m proxy_platform providers list
.venv/bin/python -m proxy_platform jobs audit-list --mode operator
```

### 改主机登记册

如果是新增/移除主机，优先走 job 入口：

```bash
.venv/bin/python -m proxy_platform jobs plan-add-host --mode operator --spec ./host.yaml
.venv/bin/python -m proxy_platform jobs apply --mode operator --plan-file ./state/jobs/plans/<job>.json --confirm
```

或者：

```bash
.venv/bin/python -m proxy_platform jobs plan-remove-host --mode operator --host-name vmrack1
.venv/bin/python -m proxy_platform jobs apply --mode operator --plan-file ./state/jobs/plans/<job>.json --confirm
```

主机真相源仍然在：

- `repos/proxy_ops_private/inventory/nodes.yaml`

订阅策略真相源仍然在：

- `repos/proxy_ops_private/inventory/subscriptions.yaml`

如果页面没有覆盖你的维护场景，或者你需要一次性批量调整，直接修改这两份文件仍然是当前最稳的方式。

### 计划远端动作

当前只允许 dry-run：

```bash
.venv/bin/python -m proxy_platform jobs plan-deploy-host --mode operator --host-name lisahost
.venv/bin/python -m proxy_platform jobs plan-decommission-host --mode operator --host-name lisahost
```

这两类命令现在会告诉你“如果未来接上 authority adapter，会走哪条下游生命周期入口”，但不会真的远端 apply。

### 当前怎么回退

当前只有一种真正可回退的 apply：登记册变更。

- 如果刚新增错了主机，回退方式是再做一次 `remove_host` job。
- 如果刚移除了错误主机，回退方式是再做一次 `add_host` job。
- 远端 deploy/decommission 还没有真正 apply，所以当前不存在自动远端回退。

### 做完变更后验证

```bash
.venv/bin/python -m pytest -q
```

如果只是检查平台状态层，也可以先跑：

```bash
.venv/bin/python -m pytest tests/test_manifest.py tests/test_cli.py tests/test_web_app.py tests/test_jobs.py -q
```

## 它不是什么

当前这份 Web 控制台不是：

- 远端部署平台
- 公网用户门户
- 已经接好域名和认证的正式站点
- `CliProxy-control-plane` 的替代品

## 后续要变成真正远端服务，还缺什么

要把它变成“可以远端访问的正式 Web”，至少还差四件事：

1. 明确部署形态
   先决定是单独服务，还是挂到现有控制面前面。
2. 接上 authority adapter
   让 deploy/decommission 的 apply 明确委托到 `remote_proxy` 或其他下游真相源，而不是页面直接 SSH。
3. 明确公开/私有视图分层
   当前页面依赖私有登记册，不能直接公网开放。
4. 接入正式认证与发布入口
   否则即使起了域名，也不是可维护的正式服务。

## 真正上线前的决策门

在这个仓库里，当前还没有“把 Web 正式发出去”的最终决策，因此也没有线上域名。

真正进入远端部署前，至少要先补齐一份新的 deployment ADR，明确三件事：

1. 最终落地在哪个运行面
   是独立服务，还是挂到现有控制面前。
2. 由哪个仓库负责正式发布物
   是 `proxy-platform` 自带运行包装，还是继续委托到下游 authority repo。
3. 哪个入口负责认证和发布
   否则页面即使能起，也还不是正式可维护站点。

## 相关文档

- [README.md](/workspaces/proxy-platform/README.md)
- [ADR-0008-platform-state-model.md](/workspaces/proxy-platform/docs/adr/ADR-0008-platform-state-model.md)
- [ADR-0009-repository-ownership-matrix.md](/workspaces/proxy-platform/docs/adr/ADR-0009-repository-ownership-matrix.md)
- [ADR-0010-mutation-job-flow-boundary.md](/workspaces/proxy-platform/docs/adr/ADR-0010-mutation-job-flow-boundary.md)
- [mutation-jobs.md](/workspaces/proxy-platform/docs/runbooks/mutation-jobs.md)
- [mutation-job-flow.md](/workspaces/proxy-platform/docs/review-checklists/mutation-job-flow.md)
- [repo-boundaries.md](/workspaces/proxy-platform/docs/repo-boundaries.md)
