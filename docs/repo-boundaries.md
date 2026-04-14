# 仓库职责与重构边界

这份文档回答的是“什么东西应该归哪个仓库”，不是“它现在碰巧放在哪里”。

## 一句话原则

- 公开运行底座留在 `remote_proxy`
- 私有现场事实留在 `Proxy_ops_private`
- 跨仓库判断、页面展示和订阅派生留在 `proxy-platform`

## 当前重合点

### `Proxy_ops_private/generated/standalone/`

这部分本质上是从 `remote_proxy` 公共部署基线派生出来的单机部署包，不是私有现场真相。

代表文件：

- `repos/proxy_ops_private/generated/standalone/akilecloud/install.sh`
- `repos/proxy_ops_private/generated/standalone/akilecloud/scripts/deploy.sh`
- `repos/proxy_ops_private/generated/standalone/dedirock/install.sh`
- `repos/proxy_ops_private/generated/standalone/dedirock/scripts/deploy.sh`

处理原则：

- 不继续把这些文件当源码真相
- 以 `remote_proxy` 作为公开部署基线
- 如仍需保留，改成根据私有现场参数渲染的派生产物

### 订阅入口文档与订阅生成逻辑

`Proxy_ops_private` 当前同时保存订阅发布配置、生成后的订阅文件，以及客户端导入文档。

代表文件：

- `repos/proxy_ops_private/inventory/subscriptions.yaml`
- `repos/proxy_ops_private/generated/subscriptions/v2ray_nodes.txt`
- `repos/proxy_ops_private/docs/client-subscription-quickstart.md`

处理原则：

- `subscriptions.yaml` 继续作为私有发布配置
- 订阅文本和 deeplink 降级为派生结果
- 页面展示、可复制入口、订阅派生规则回收到 `proxy-platform`

### 真实主机事实

主机是否存在、是否启用、属于哪个 provider、是否允许进入订阅，仍然是私有现场事实。

代表文件：

- `repos/proxy_ops_private/inventory/nodes.yaml`
- `repos/proxy_ops_private/secrets/nodes/*.env`

处理原则：

- 继续留在 `Proxy_ops_private`
- 通过 `proxy-platform` 的状态模型读取，不复制到公开仓库

## 所有权矩阵

### 保留在 `remote_proxy`

- `repos/remote_proxy/scripts/deploy.sh`
- `repos/remote_proxy/scripts/service.sh`
- `repos/remote_proxy/scripts/services/cliproxy_plus/deploy.sh`
- `repos/remote_proxy/docs/deploy/standalone-vps.md`
- `repos/remote_proxy/docs/deploy/cliproxy-plus-standalone-vps.md`

原因：

- 这些文件描述的是“这类服务怎样标准化部署”，不是“你现场有哪些主机”

### 保留在 `Proxy_ops_private`

- `repos/proxy_ops_private/inventory/nodes.yaml`
- `repos/proxy_ops_private/inventory/subscriptions.yaml`
- `repos/proxy_ops_private/secrets/nodes/`
- `repos/proxy_ops_private/scripts/render_artifacts.py`

原因：

- 这些文件描述的是“你的真实现场是什么”

### 回收到 `proxy-platform`

- 主机登记册 schema
- 观测状态 schema
- 页面主机视图规则
- 订阅派生规则
- 远端 job schema、authority handoff / 审计规则

原因：

- 这些内容不属于公开部署底座，也不属于私有现场，而是平台如何解释现场

### 删除或降级为派生结果

- `repos/proxy_ops_private/generated/standalone/`
- `repos/proxy_ops_private/generated/subscriptions/*.txt`
- `repos/proxy_ops_private/generated/subscriptions/*.json`

原因：

- 它们是渲染结果，不应长期充当源码真相

## 重构顺序

1. 先把状态模型和派生规则固化到 `proxy-platform`
2. 再把现有生成物明确标记为派生结果
3. 最后逐步收缩 `Proxy_ops_private` 中来源于 `remote_proxy` 的重复部署包
