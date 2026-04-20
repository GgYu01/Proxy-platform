# Operator Web Console 使用与维护说明

## 一句话结论

`proxy-platform` 的 operator Web 已经正式部署到 Ubuntu.online，可以通过域名直接访问；它现在是“带认证的现场清单与移交单工作台”，不是直接 SSH 下发的第二控制面。

## 它在当前项目里代表什么

在这个项目里，它不是新控制面内核，也不是公网匿名门户。

它更准确的定位是：

- 远端可访问的多页面 operator 总览与现场清单页
- 远端可访问的订阅派生查看页
- 主机登记册变更入口
- authority handoff 移交单入口
- 计划、审计、handoff 的统一查看面
- 服务端模板化的 operator 工作台，而不是独立 SPA

换句话说，它解决的是“operator 不用再只靠本地命令行看现场和出移交单”，而不是“平台现在自己接管远端宿主机生命周期”。

## 当前正式入口

- 主入口：`https://proxy-platform-operator.svc.prod.lab.gglohh.top:27111/`
- 健康检查：`https://proxy-platform-operator.svc.prod.lab.gglohh.top:27111/health`
- 认证方式：HTTP Basic Auth
- 账号凭据：只以远端模块 `.env` 为准，不在仓库文档中保存实际密码

当前还保留了宿主机直连 fallback：

- 宿主机内可用：`http://127.0.0.1:18082/health`

但要注意：

- 当前外部网络策略没有放通 `18082`
- 所以对人类用户来说，真正应该使用的是域名入口，而不是尝试直接连 `18082`

## 当前部署现场

- 宿主机：`gaoyx@112.28.134.53:52117`
- `infra-core` 根目录：`/mnt/hdo/infra-core`
- 模块目录：`/mnt/hdo/infra-core/modules/proxy-platform-operator`

模块内部当前分成三层：

- `/app`
  固定发布物，也就是当前镜像里的代码和 manifest。
- `.runtime-seed`
  首次部署或人工刷新时使用的 seed。
- `.runtime-workspace`
  页面真正读写的运行时工作区。

在这个项目里，这个三层拆分非常关键。因为页面会写主机登记册副本、计划、审计和 handoff；如果把这些东西继续放在源码目录里，下一次 redeploy 就会把线上现场数据覆盖掉。

当前正式部署还要记住三条维护约束：

- 认证是 fail-closed。
  如果远端 `.env` 里缺少用户名或密码，或者密码还是示例值，服务会拒绝启动；不会因为“少配一个变量”就退回匿名访问。
- redeploy 不覆盖远端 `.env`。
  也就是说，重发模块不会把线上密码、域名、端口和镜像策略重置回示例值。
- authority review surface 会自动刷新。
  `remote_proxy` 的脚本、env 模板和部署 runbook 会从 `.runtime-seed` 刷到 `.runtime-workspace`，防止 handoff 继续引用旧模板；但主机登记册和订阅策略不会被无条件覆盖。
  redeploy 现在的正式规则是：
  - 如果远端 `nodes.yaml` / `subscriptions.yaml` 还等于上一版 `.runtime-seed` 镜像，允许自动刷新到这次的新 seed；
  - 如果远端运行态副本已经偏离上一版 seed，必须保留并暴露漂移，不能静默抹掉现场编辑。

## 页面里能做什么

### 页面结构

当前页面已经从早期“内联验证页”升级成共享壳层加多职责页的工作台结构：

- `/`
  - 现场摘要、入口分流、最近审计预览、刷新健康观测
- `/hosts`
  - 主机现场清单、搜索、状态 badge、拓扑/运行时、订阅归属、观测细节
- `/subscriptions`
  - 手动订阅 URL、Hiddify Deep Link、单节点复制按钮
- `/providers`
  - startup budget / request budget / 重试预算
- `/worker-quotas`
  - 只读查看 `cliproxy-control-plane` 返回的远端 worker/oauth 配额、probe 状态和最新 quota 快照
- `/jobs`
  - 新增、移除、远端移交计划、明确确认后 apply
- `/audit`
  - 最近 10 条事件

它解决的是“让 operator 更快看清现场和最近一次动作结果”，不是“把平台改造成完整前端产品”。

这里要额外记住一条边界：

- `/worker-quotas` 不是新的 quota 控制面。
- `proxy-platform` 只读消费 `cliproxy-control-plane` 的权威接口，不负责 probe、quota 计算、worker 调度或账号池 fallback。

### 1. 看现场清单

页面会显示：

- 主机名
- provider
- 当前部署拓扑
- 当前运行服务
- 当前观测状态
- 是否进入订阅

这部分回答的是“平台现在认哪些主机在现场里，以及它们目前被怎么分类、怎么观测”。

当前“健康可用”这张卡不是猜测值，也不是把 `unknown` 硬算成 `healthy`。

它的含义是：

- 平台最近一次 TCP 最小探测里，直接探测成功的主机数
- 当前默认探测目标是每台主机的 `base_port + 1`
- 如果线上还没有观测文件，页面会先尝试补一次观测；你也可以手动点击“刷新健康观测”

### 2. 看订阅入口

页面会显示：

- 多节点手动订阅 URL
- Hiddify Deep Link
- 每个节点的单节点订阅 URL
- 每个节点的 Hiddify Deep Link

这部分是派生结果，不是原始真相。

这里有一个必须说清的边界：

- `https://.../v2ray_nodes.txt`
  是普通订阅 URL，适合你在客户端里手动粘贴。
- `hiddify://import/...`
  是 Hiddify Deep Link，适合浏览器点击拉起 Hiddify，或者在 Hiddify 里从剪贴板导入。
- 不要把 `hiddify://...` 粘贴到手动订阅 URL 输入框。

### 3. 新增或删除主机

页面可以：

- 先生成 `add_host` / `remove_host` 计划
- 再显式确认并 apply

对这两类变更，`apply` 的效果是修改远端 `.runtime-workspace` 里的登记册副本并写审计。

### 4. 生成 deploy/decommission 移交单

页面可以：

- 为现有主机生成 `deploy_host` 计划
- 为现有主机生成 `decommission_host` 计划
- 对计划做显式 apply

这里的 `apply` 结果是 authority handoff YAML 落地，不是页面自己执行远端安装。

### 5. 生成 public 只读快照

页面本身不直接提供匿名 public 页面，但当前平台已经有一条正式的脱敏导出链路。

换句话说：

- operator 工作台负责看现场真相和维护运行态副本；
- public 只读入口负责消费已经导出的脱敏快照；
- 两者中间不再用“public 直接读 private registry”这种越界方式偷跑。

### 6. 准备 private truth reviewed sync

如果页面上的新增/删除主机已经在 `.runtime-workspace` 生效，但你希望把这些变化正式带回本地 `repos/proxy_ops_private` 工作树，当前应该走 reviewed sync plan，而不是手工 copy 文件。

## 它是什么、解决什么、它不是什么

### 它是什么

- 认证后的远端 operator 工作台
- 主机登记册副本的维护入口
- authority handoff 的远端统一入口

### 它解决什么

- 让 operator 不必再只靠本地命令行看现场
- 让远端工作台也能统一生成计划、审计和 handoff
- 让远端发布物、seed 和运行态工作区分开

### 它不是什么

- 不是 `CliProxy-control-plane` 的替代品
- 不是平台直接 SSH 的执行器
- 不是匿名公网用户站点

## 现有主机为什么现在能出 deploy plan

现象：

- 页面已经能看到 `lisahost`、`vmrack1`、`vmrack2`、`dedirock`
- 但如果登记册里没有部署分类，`deploy_host` 计划会直接返回 `409`

直接原因：

- `deploy_host` / `decommission_host` 的 authority adapter 选择依赖两个字段：
  - `deployment_topology`
  - `runtime_service`

根因：

- 老的私有主机登记册只记录地址、端口和发布开关，还没有把“这台主机到底属于哪种部署模型”写成结构化字段。

为什么以前没暴露：

- 在只有订阅展示和只读页面时，这个问题不会挡住使用；
- 一旦要从页面上生成 deploy/decommission 计划，它就必须先知道这台主机属于哪条 authority path。

当前已经补齐：

- `lisahost`: `standalone_vps + cliproxy-plus`
- `vmrack1`: `standalone_vps + cliproxy-plus`
- `vmrack2`: `standalone_vps + cliproxy-plus`
- `dedirock`: `standalone_vps + cliproxy-plus`

当前 rollout 约束：

- 四台节点都允许进入 `cliproxy-plus` 发布链
- `dedirock` 是首个验证节点
- 默认顺序是 `dedirock -> vmrack1 -> vmrack2 -> lisahost`

## 日常维护

### 看站点状态

```bash
curl -k https://proxy-platform-operator.svc.prod.lab.gglohh.top:27111/health
ssh -p 52117 gaoyx@112.28.134.53 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep proxy-platform-operator'
```

### 修改认证或域名

```bash
ssh -p 52117 gaoyx@112.28.134.53 'vi /mnt/hdo/infra-core/modules/proxy-platform-operator/.env'
ssh -p 52117 gaoyx@112.28.134.53 'cd /mnt/hdo/infra-core && scripts/modulectl.sh up proxy-platform-operator'
```

### 重新部署模块

在仓库根目录执行：

```bash
./deploy/infra-core-module/register_module.sh
ssh -p 52117 gaoyx@112.28.134.53 'cd /mnt/hdo/infra-core && scripts/modulectl.sh up proxy-platform-operator'
```

构建默认走 `docker.m.daocloud.io` + 阿里云 PyPI + 阿里云 Debian 镜像；需要换源时，设置 `PYTHON_BASE_IMAGE`、`PIP_INDEX_URL`、`PIP_TRUSTED_HOST`、`APT_MIRROR_URL` 即可。

第一次部署如果远端还没有 `.env`，脚本会先生成模板文件，但认证密码默认留空。真正 `modulectl up` 之前，要先把 `.env` 改成真实账号和密码。

如果你要启用 `/worker-quotas` 页面，还要同时补齐：

- `PROXY_PLATFORM_CONTROL_PLANE_BASE_URL`
- `PROXY_PLATFORM_CONTROL_PLANE_USERNAME`
- `PROXY_PLATFORM_CONTROL_PLANE_PASSWORD`
- 可选：`PROXY_PLATFORM_CONTROL_PLANE_TIMEOUT_SECONDS`

这组三元组必须一起出现；如果只配了一部分，当前 runtime 会直接拒绝启动，避免站点进入“页面有入口但 authority 读半残”的半配置状态。

如果你想把“重发模块 + 拉起服务 + 健康失败时自动回退”合并成一个动作，可以显式开启：

```bash
ENABLE_AUTO_ROLLBACK=1 ./deploy/infra-core-module/redeploy_with_rollback.sh
```

默认值仍然是关闭自动回退。也就是说，不加这个环境变量时，脚本只会给出失败结果和手工回退抓手，不会擅自回切现场。

### 人工刷新 seed 到线上运行时

如果你在本地更新了 `repos/proxy_ops_private/inventory/nodes.yaml` 或 `subscriptions.yaml`，这些变化现在不是“永远不会被 redeploy 带过去”。

准确规则是：

1. 如果远端现场清单还只是上一版 seed 的镜像，redeploy 会自动把新的主机登记册带过去。
2. 如果远端现场清单已经在站点上被继续编辑，redeploy 会保留它，不会静默覆盖。
3. 如果上一轮部署失败在“新 seed 已写入、workspace 还没更新”的半路状态，需要先根据 `.deploy-backups/runtime-seed-*` 找到真正对应旧现场的 seed 基线，再做一次受控修平。

但有一个例外要记住：

- `repos/remote_proxy/scripts/service.sh`
- `repos/remote_proxy/config/cliproxy-plus.env`
- `repos/remote_proxy/docs/deploy/*.md`

这类 authority review surface 会在服务启动时从 `.runtime-seed` 自动刷新到 `.runtime-workspace`。换句话说，需要重点审的是“现场清单”；但现场清单现在也不是完全手工同步，而是升级成了“旧 seed 镜像自动刷新、现场已漂移则保留”的受控策略。

当前建议做法是：

1. 先确认线上工作区里没有未处理的 operator 变更。
2. 通过正式 redeploy 更新 `.runtime-seed`。
3. 让发布脚本按“上一版 seed 镜像是否仍然匹配”自动判断要不要刷新 `.runtime-workspace`。
4. 只有在半更新现场或明确冲突时，才人工介入修平。

### 导出 public 只读快照

在本地仓库根目录执行：

```bash
.venv/bin/python -m proxy_platform exports export-public \
  --manifest ./platform.manifest.yaml \
  --workspace-root /mnt/hdo/infra-core/modules/proxy-platform-operator/.runtime-workspace \
  --output-root /mnt/hdo/infra-core/modules/proxy-platform-operator/.runtime-workspace/state/public
```

然后可以直接用 `public` 模式核对脱敏结果：

```bash
.venv/bin/python -m proxy_platform hosts list \
  --manifest ./platform.manifest.yaml \
  --workspace-root /mnt/hdo/infra-core/modules/proxy-platform-operator/.runtime-workspace \
  --mode public

.venv/bin/python -m proxy_platform subscriptions list \
  --manifest ./platform.manifest.yaml \
  --workspace-root /mnt/hdo/infra-core/modules/proxy-platform-operator/.runtime-workspace \
  --mode public
```

这里导出的内容只保留展示和订阅所需字段，不包含：

- 主机地址
- SSH 端口
- base port
- change policy

### 把运行时副本回写到 private truth 工作树

当前正式流程是两步：

1. 先生成 reviewed sync plan
2. 再在确认 plan 仍然成立后显式 apply

示例：

```bash
.venv/bin/python -m proxy_platform exports plan-sync-private \
  --runtime-workspace-root /mnt/hdo/infra-core/modules/proxy-platform-operator/.runtime-workspace \
  --repo-root /workspaces/proxy-platform

.venv/bin/python -m proxy_platform exports apply-sync-private \
  --plan-file /workspaces/proxy-platform/state/private_truth_sync/plans/<sync-plan>.json \
  --confirm
```

这条链路当前解决的是：

- 不再手工比对 `.runtime-workspace` 和本地 `repos/proxy_ops_private/inventory/*`
- 不再直接用 `cp` 或编辑器盲写 private truth 工作树
- 在 apply 前明确校验 source/target digest，防止同步掉线上的新变化或本地人工刚改过的文件

这条链路当前还不负责：

- 自动 Git commit
- 自动 Git push
- 自动把变更发到远端 Git 真相源

## 回退

### 模块发布物回退

当前可以通过两种方式人工回退：

1. 把 `.env` 中的 `PROXY_PLATFORM_OPERATOR_IMAGE` 改回上一版镜像标签，然后重新 `modulectl up`
2. 恢复 `.deploy-backups/` 下的模块源码快照，再重新 `modulectl up`

如果你已经启用了 `ENABLE_AUTO_ROLLBACK=1`，上面的两步会在健康检查失败后由 `redeploy_with_rollback.sh` 自动尝试一次；如果你没有显式开启，当前仍保持人工回退。

如果回退后服务没有起来，优先检查两件事：

1. `.env` 是否仍然带着完整认证字段
2. 回退后的镜像标签是否真实存在于宿主机本地

### 远端代理节点回退

这不归当前页面直接处理。

- `standalone_vps` 的 rollback owner 仍然是 `remote_proxy`
- `infra_core_sidecar` 的 rollback owner 仍然是 `infra_core`

## 验收命令

### 健康检查

```bash
curl -k https://proxy-platform-operator.svc.prod.lab.gglohh.top:27111/health
```

当前 `/health` 只返回最小探活结果：

```json
{"status":"ok"}
```

### 认证后读取主机清单

```bash
curl -k -H 'Authorization: Basic <base64(username:password)>' \
  https://proxy-platform-operator.svc.prod.lab.gglohh.top:27111/api/hosts
```

### 认证后生成 deploy plan

```bash
curl -k -H 'Authorization: Basic <base64(username:password)>' \
  -H 'Content-Type: application/json' \
  -d '{"job_kind":"deploy_host","payload":{"name":"lisahost"}}' \
  https://proxy-platform-operator.svc.prod.lab.gglohh.top:27111/api/jobs/plan
```

## 相关文档

- [README.md](/workspaces/proxy-platform/README.md)
- [ADR-0011-authority-handoff-and-operator-deployment.md](/workspaces/proxy-platform/docs/adr/ADR-0011-authority-handoff-and-operator-deployment.md)
- [ADR-0012-operator-web-infra-core-deployment.md](/workspaces/proxy-platform/docs/adr/ADR-0012-operator-web-infra-core-deployment.md)
- [ADR-0013-public-snapshot-and-private-truth-sync.md](/workspaces/proxy-platform/docs/adr/ADR-0013-public-snapshot-and-private-truth-sync.md)
- [public-state-and-private-sync.md](/workspaces/proxy-platform/docs/runbooks/public-state-and-private-sync.md)
- [mutation-jobs.md](/workspaces/proxy-platform/docs/runbooks/mutation-jobs.md)
- [authority-handoff.md](/workspaces/proxy-platform/docs/runbooks/authority-handoff.md)
