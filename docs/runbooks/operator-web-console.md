# Operator Web Console 使用与维护说明

## 一句话结论

当前 `proxy-platform` 的 Web 控制台已经可以在本地启动并使用，但本轮还没有做远端正式部署，所以现在没有一个可直接访问的线上域名。

## 它在当前项目里是什么

这不是新的控制面站点，也不是已经接上远端部署按钮的运维后台。

在当前项目里，它更准确的定位是：

- 平台现场清单查看页
- 订阅入口查看页
- 本地 provider 生命周期查看页
- inventory 文件级别的最小增删入口

换句话说，它现在解决的是“怎么看清楚当前平台登记册、观测状态和订阅派生结果”，不是“已经可以直接在页面里下发远端部署”。

## 当前上线状态

- 已完成：本地可运行的最小 Web 控制台
- 已完成：`/api/hosts`、`/api/subscriptions`、`/api/providers`
- 已完成：页面内复制订阅链接按钮
- 已完成：基于 inventory 文件的本地增删入口
- 未完成：远端正式部署
- 未完成：公网域名接入
- 未完成：受控远端 job schema、dry-run、审计和 apply

因此，当前没有“应该访问哪个线上域名”的答案。

如果只想本地查看，当前访问地址是：

- `http://127.0.0.1:8765/`

## 本地启动方式

在仓库根目录执行：

```bash
.venv_fix/bin/python -m proxy_platform web --mode operator --host 127.0.0.1 --port 8765
```

然后在本机浏览器打开：

```text
http://127.0.0.1:8765/
```

说明：

- 必须使用 `--mode operator`
  因为当前页面读取的是 `repos/proxy_ops_private` 中的私有登记册。
- 当前不建议把这个本地服务直接暴露到公网
  因为它还处于第一阶段，只完成了状态查看和文件级变更入口。

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

## 当前按钮会做什么，不会做什么

当前页面上的主机增删接口：

- 会修改 inventory 文件
- 不会自动 SSH 到远端
- 不会自动部署代理
- 不会自动摘除远端服务

换句话说，现在它是“受控文件入口”，不是“远端执行入口”。

这是故意这样设计的。因为在这个项目里，远端 mutation 必须等 job schema、dry-run 和审计补齐后，才能正式接进去。

## 日常维护怎么做

### 看当前状态

```bash
.venv_fix/bin/python -m proxy_platform hosts list --mode operator
.venv_fix/bin/python -m proxy_platform subscriptions list --mode operator
.venv_fix/bin/python -m proxy_platform providers list
```

### 改主机登记册

主机真相源仍然在：

- `repos/proxy_ops_private/inventory/nodes.yaml`

订阅策略真相源仍然在：

- `repos/proxy_ops_private/inventory/subscriptions.yaml`

如果页面没有覆盖你的维护场景，直接修改这两份文件仍然是当前最稳的方式。

### 做完变更后验证

```bash
.venv_fix/bin/python -m pytest -q
```

如果只是检查平台状态层，也可以先跑：

```bash
.venv_fix/bin/python -m pytest tests/test_manifest.py tests/test_cli.py tests/test_web_app.py -q
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
2. 补远端 job schema
   把主机新增、部署、摘除变成 dry-run + audit + apply，而不是页面直接 SSH。
3. 明确公开/私有视图分层
   当前页面依赖私有登记册，不能直接公网开放。
4. 接入正式认证与发布入口
   否则即使起了域名，也不是可维护的正式服务。

## 相关文档

- [README.md](/workspaces/proxy-platform/README.md)
- [ADR-0008-platform-state-model.md](/workspaces/proxy-platform/docs/adr/ADR-0008-platform-state-model.md)
- [ADR-0009-repository-ownership-matrix.md](/workspaces/proxy-platform/docs/adr/ADR-0009-repository-ownership-matrix.md)
- [repo-boundaries.md](/workspaces/proxy-platform/docs/repo-boundaries.md)
