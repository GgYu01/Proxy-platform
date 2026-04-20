# proxy-platform

统一入口薄平台壳仓库。

一句话说清：`proxy-platform` 现在已经有正式部署的远端 operator Web 入口，但它上线的是“带认证的现场清单与移交单工作台”，不是直接下发 SSH 的第二控制面；这层 Web 继续保持服务端模板壳，不升级成独立 SPA。

新增的 `webchat-openai-runtime` 也按同一原则纳管：它是浏览器会话执行内核和 OpenAI-compatible 运行时，不是新的平台控制面，也不是帐号池、租户、计费和渠道治理层。

它负责：

- 统一 CLI / 未来 Web 工作台入口
- 统一 repo-of-repos 编排
- 统一 manifest、帮助系统、诊断输出
- 统一“主机登记册 + 观测回报 + 订阅派生”状态模型
- 统一平台级 AGENTS / ADR / review checklist

它不负责：

- 重写 `CliProxy-control-plane` 的 northbound `/v1` 网关
- 接管 `cliproxy-control-plane` 的 worker/oauth quota 真相与 probe 执行
- 保存 `Proxy_ops_private` 的私有真相内容
- 直接替代 `remote_proxy` 的宿主机部署基线

## 仓库角色

- `repos/remote_proxy`
  公开部署基线
- `repos/cliproxy-control-plane`
  聚合控制面与 northbound `/v1` 内核
- `repos/proxy_ops_private`
  私有 inventory / secrets / generated artifacts 真相源
- `repos/remote_browser`
  可选 provider
- `repos/webchat-openai-runtime`
  可选 provider runtime，负责浏览器会话执行和 OpenAI-compatible 协议面

`webchat-openai-runtime` 在这个项目里到底是什么：

- 它是“把网页聊天会话包装成标准 OpenAI API 调用面”的运行时内核。
- 它解决的是本地 agent、OpenAI SDK、后续 `new-api` / `CLIProxyAPIPlus` 上游如何统一接入网页端 AI chat。
- 它不负责租户、帐号池运营、计费、RBAC、商业化渠道，也不接管 `CliProxy-control-plane` 的 northbound `/v1`。

## 第一波交付

- `platform.manifest.yaml`
- `.gitmodules`
- 平台级 `AGENTS.md`
- ADR 文档
- CLI 薄壳
  - `manifest validate`
  - `repos list`
  - `doctor`
  - `init`
  - `sync`
  - `hosts list --mode operator`
  - `hosts list --mode public`
  - `subscriptions list --mode operator`
  - `subscriptions list --mode public`
  - `providers list`
  - `web --mode operator`
  - `hosts --registry ... [--observations ...]`
  - `subscriptions preview --registry ... [--observations ...]`
  - `jobs plan-add-host --mode operator --spec ...`
  - `jobs plan-remove-host --mode operator --host-name ...`
  - `jobs plan-deploy-host --mode operator --host-name ...`
  - `jobs plan-decommission-host --mode operator --host-name ...`
  - `jobs apply --mode operator --plan-file ... --confirm`
  - `jobs audit-list --mode operator`
  - `exports export-public`
  - `exports plan-sync-private`
  - `exports apply-sync-private`

当前 `init` / `sync` 的执行边界：

- 如果目标工作区已经存在普通目录，则保持原状
- 如果目标工作区已经存在 Git 仓库，则执行 `git fetch --all --tags`
- 如果 manifest 提供了 `local_override_path`，则优先在 `repos/` 下建立本地符号链接
- 如果既没有现成工作区，也没有 `local_override_path` 可用，则尝试按 `default_url` 执行 clone
- 如果 clone / fetch 失败，则明确返回非零并输出可读失败原因
- 不做远端主机写操作

当前 `doctor` 的执行边界：

- `doctor`
  诊断工作区 repo 状态
- `doctor toolchain --profile <id>`
  诊断宿主机 OS / Python / 关键命令是否满足指定 host profile

当前 `manifest validate` 还会校验 `.gitmodules` 和 `platform.manifest.yaml` 的 path / url 是否一致。

## 平台状态模型

当前平台壳已经把“平台到底看见什么”正式拆成三层：

- 主机登记册
  平台认可的现场清单，回答“哪些主机应当出现在平台里”。
- 观测回报
  远端 agent 或 probe 的现场回报，回答“这些主机现在是什么状态”。
- 派生视图
  页面列表、订阅成员、后续 job 入口都只从前两层派生。

当前平台状态层已经提供两类入口：

- 只读入口
  负责看清“现场清单、观测回报、订阅派生”。
- mutation job 入口
  负责先生成 plan 和 audit，再决定能不能 apply。

只读入口：

```bash
python -m proxy_platform hosts list --mode operator
python -m proxy_platform subscriptions list --mode operator
python -m proxy_platform web --mode operator
python -m proxy_platform hosts --registry ./registry.yaml --observations ./observations.yaml
python -m proxy_platform subscriptions preview --registry ./registry.yaml --observations ./observations.yaml
```

mutation job 入口：

```bash
python -m proxy_platform jobs plan-add-host --mode operator --spec ./host.yaml
python -m proxy_platform jobs plan-remove-host --mode operator --host-name vmrack1
python -m proxy_platform jobs plan-deploy-host --mode operator --host-name lisahost
python -m proxy_platform jobs apply --mode operator --plan-file ./state/jobs/plans/xxx.json --confirm
python -m proxy_platform jobs audit-list --mode operator
```

当前 mutation job 边界是：

- `add_host` / `remove_host`
  允许 `apply`，executor 是 `inventory_only`，也就是只改登记册文件并写审计。
- `deploy_host` / `decommission_host`
  现在也允许 `apply`，但 executor 是 `authority_handoff`。
  在这个项目里，这里的 `apply` 不等于“已经去远端执行”，而是“生成一份正式移交单，明确告诉下游 authority 仓库或宿主机 owner 下一步该走哪条入口”。

当前 authority handoff 已经固化了三类下游路径：

- `remote_proxy_cliproxy_plus_standalone`
  适用于 `standalone_vps`，会把 `deploy_host` 移交到 `repos/remote_proxy/scripts/service.sh cliproxy-plus install` 这条生命周期入口。
- `remote_proxy_cliproxy_plus_standalone_decommission`
  适用于 `standalone_vps`，但因为下游还没有统一的 decommission 脚本，所以当前只生成 runbook 型移交单。
- `remote_proxy_cliproxy_plus_infra_core_sidecar`
  适用于 `infra_core_sidecar`。本地 `apply` 只要求能审阅 `repos/remote_proxy/docs/deploy/infra-core-ubuntu-online.md` 这条移交面；真正执行前必须由 downstream owner 再确认 `/mnt/hdo/infra-core` 这类执行现场前提，而不是把它误当成本地 apply 阻塞项。

当前 plan 文件只接受位于 `state/jobs/plans/` 这块受管目录下的已审计划。`apply` 时还会校验：

- 计划摘要没有被替换
- 对应 `planned` 审计还在
- 当前 manifest 仍允许执行这类 job
- 当前 executor 和 authority adapter 没有漂移
- 同一 `job_id` 没有已经执行过的 `applied` 审计

这样可以避免“先审了一个计划，执行时换了内容”，也可以避免“旧计划越过新边界”。

当前模式边界：

- `hosts list --mode operator` / `subscriptions list --mode operator` / `web --mode operator` 读取的是 `Proxy_ops_private` 里的私有登记册，因此继续限制在 `operator` 模式。
- `hosts list --mode public` / `subscriptions list --mode public` 现在已经改成只消费 `state/public/host_console.json` 和 `state/public/subscriptions.json` 这两份脱敏快照，不直接读取私有现场清单。
- `public` 模式回答的是“公开用户现在能看什么”；`operator` 模式回答的是“平台现场真实登记册现在是什么”。

当前已经补上的两条桥接链路：

- public snapshot 导出
  先从 `operator` 真相源导出脱敏快照，再让 `public` 模式消费这份快照。
- private truth reviewed sync
  先从运行时工作区生成 reviewed plan，再决定要不要把 `.runtime-workspace` 里的登记册副本回写到本地 `repos/proxy_ops_private/inventory/*`。

当前订阅派生规则是：

- 只要主机在登记册里 `enabled=true` 且 `include_in_subscription=true`，就进入订阅。
- `healthy` / `degraded` / `down` / `unknown` 只影响展示与审计，不自动把主机从订阅里移除。
- 登记册里没有的观测结果会被标成“未知观测主机”，用于后续盘点和治理。

对应文档：

- `docs/adr/ADR-0008-platform-state-model.md`
- `docs/adr/ADR-0009-repository-ownership-matrix.md`
- `docs/adr/ADR-0010-mutation-job-flow-boundary.md`
- `docs/adr/ADR-0011-authority-handoff-and-operator-deployment.md`
- `docs/adr/ADR-0012-operator-web-infra-core-deployment.md`
- `docs/adr/ADR-0013-public-snapshot-and-private-truth-sync.md`
- `docs/adr/ADR-0014-operator-web-template-shell.md`
- `docs/repo-boundaries.md`
- `docs/runbooks/operator-web-console.md`
- `docs/runbooks/public-state-and-private-sync.md`
- `docs/runbooks/mutation-jobs.md`
- `docs/runbooks/authority-handoff.md`
- `docs/review-checklists/mutation-job-flow.md`

## 推荐工作区布局

推荐把整个平台工作区收敛到单根：

```text
/workspaces/proxy-platform/
  README.md
  platform.manifest.yaml
  state/
    observations/
      hosts.json
    jobs/
      audit/
        events.jsonl
      plans/
  repos/
    remote_proxy/
    cliproxy-control-plane/
    proxy_ops_private/
    remote_browser/
    webchat-openai-runtime/
  archive/
    multi_repo_arch_analysis/
```

规则如下：

- `/workspaces/proxy-platform` 是唯一权威根。
- `state/` 下的是本地运行态和审计痕迹，不是私有 inventory 真相源，也不是需要提交到 Git 的源码目录。
- `repos/` 下的仓库是权威工作树。
- `archive/` 下的目录只用于保留分析副本、历史快照和临时验证材料，不作为源码真相源。
- 历史旧路径已经移除；如需追溯旧计划、日志和分析材料，请到 `archive/` 下查看。

## 快速开始

```bash
python3 -m venv .venv
. .venv/bin/activate
.venv/bin/python -m pip install -e .[dev]
.venv/bin/python -m proxy_platform manifest validate
.venv/bin/python -m proxy_platform repos list
.venv/bin/python -m proxy_platform doctor
.venv/bin/python -m proxy_platform doctor toolchain --profile cliproxy_plus_standalone
.venv/bin/python -m proxy_platform init --mode public
.venv/bin/python -m proxy_platform sync --mode public
```

上面这段只覆盖 public 壳能力，也就是工作区编排、manifest 校验和 toolchain 体检。

如果你要使用 operator 入口，还要满足一个前提：

- `repos/proxy_ops_private/` 必须已经可用。
- 这通常来自两种路径之一：
  - 当前工作区已经通过 `local_override_path` 挂好了 `repos/proxy_ops_private/`
  - 你有权限通过 `git@github.com:GgYu01/Proxy_ops_private.git` 做 operator 模式的 init/sync

operator 只读与 mutation 入口示例：

```bash
.venv/bin/python -m proxy_platform init --mode operator
.venv/bin/python -m proxy_platform sync --mode operator
.venv/bin/python -m proxy_platform hosts list --mode operator
.venv/bin/python -m proxy_platform subscriptions list --mode operator
.venv/bin/python -m proxy_platform jobs plan-deploy-host --mode operator --host-name lisahost
.venv/bin/python -m proxy_platform jobs apply --mode operator --plan-file ./state/jobs/plans/<deploy-job>.json --confirm
.venv/bin/python -m proxy_platform jobs audit-list --mode operator
```

这条 `apply` 命令当前只会在通过最终校验后生成 authority handoff 移交单，落到 `state/jobs/handoffs/`，不会直接 SSH 到远端宿主机执行。

这里的最终校验至少包括三类内容：

- 当前 authority contract 没有在 planning 之后发生漂移
- 下游 entrypoint 仍然存在
- 本地 review prerequisite，也就是 `required_paths` / `required_env_files`，仍然满足
- 如果 handoff 里带了 `downstream_required_paths`，这些会被写进移交单并交给真正执行方复核，而不是由平台壳在本地代验

public 快照与 private truth 回写入口示例：

```bash
.venv/bin/python -m proxy_platform exports export-public \
  --manifest ./platform.manifest.yaml \
  --workspace-root /mnt/hdo/infra-core/modules/proxy-platform-operator/.runtime-workspace \
  --output-root /mnt/hdo/infra-core/modules/proxy-platform-operator/.runtime-workspace/state/public

.venv/bin/python -m proxy_platform hosts list \
  --manifest ./platform.manifest.yaml \
  --workspace-root /mnt/hdo/infra-core/modules/proxy-platform-operator/.runtime-workspace \
  --mode public

.venv/bin/python -m proxy_platform subscriptions list \
  --manifest ./platform.manifest.yaml \
  --workspace-root /mnt/hdo/infra-core/modules/proxy-platform-operator/.runtime-workspace \
  --mode public

.venv/bin/python -m proxy_platform exports plan-sync-private \
  --runtime-workspace-root /mnt/hdo/infra-core/modules/proxy-platform-operator/.runtime-workspace \
  --repo-root /workspaces/proxy-platform

.venv/bin/python -m proxy_platform exports apply-sync-private \
  --plan-file ./state/private_truth_sync/plans/<sync-plan>.json \
  --confirm
```

这组命令的边界是：

- `export-public` 只生成脱敏 public 快照，不会发布密码、主机地址、SSH 端口或 change policy。
- `plan-sync-private` / `apply-sync-private` 只覆盖 `repos/proxy_ops_private/inventory/nodes.yaml` 和 `subscriptions.yaml`，不碰 secrets、生成产物或 Git 提交。
- `apply-sync-private` 会校验 source/target digest，避免把运行时副本静默盖掉人工刚改过的私有真相文件。

## Host Toolchain Profiles

当前 manifest 已声明两类可复用宿主机 profile：

- `cliproxy_plus_standalone`
  对齐 `remote_proxy` 中 `cliproxy-plus` 独立 VPS 路径，关注 `Python >= 3.9`、`curl`、`jq`、`podman`、`systemctl`。
- `control_plane_compose`
  对齐 `CliProxy-control-plane` compose 路径，关注 `Python >= 3.11`、`docker`、`docker compose` / `docker-compose`。

示例：

```bash
.venv/bin/python -m proxy_platform doctor toolchain --profile cliproxy_plus_standalone
.venv/bin/python -m proxy_platform doctor toolchain --profile control_plane_compose
```

对 Python 类依赖，输出会额外给出：

- 当前选中的兼容解释器
- 解释器绝对路径
- 对应环境变量提示，例如 `REMOTE_PROXY_PYTHON_BIN`

这让平台壳可以先回答“当前主机是否可用、若不可用缺什么、若默认 python 不满足时有没有稳定候选”，但仍然把真正的安装/切换动作留在下游仓库。

## 当前 Web 上线状态

一句话结论：operator Web 已经按 `infra-core` 独立模块方式正式部署到 Ubuntu.online，但它上线的是“认证后的 operator 工作台”，不是匿名公网门户。

当前部署现场：

- 远端主机：`gaoyx@112.28.134.53:52117`
- 模块目录：`/mnt/hdo/infra-core/modules/proxy-platform-operator`
- 主入口：`https://proxy-platform-operator.svc.prod.lab.gglohh.top:27111/`
- 健康检查：`https://proxy-platform-operator.svc.prod.lab.gglohh.top:27111/health`
- 认证方式：HTTP Basic Auth
- 默认账号名：`admin`
- 默认密码：`Aa123456`
- 如后续调整，以远端模块 `.env` 为准

当前运行时布局：

- `/app`
  固定发布物，也就是当前版本的应用代码和 manifest。
- `.runtime-seed`
  首次部署和手工刷新时使用的最小 seed，包括主机登记册、订阅策略和 authority review surface。
- `.runtime-workspace`
  真正会被页面读写的运行时工作区。页面里的新增/删除主机、plan、audit、handoff 都落在这里。
- `.deploy-backups`
  每次重新注册模块前保存的源码快照，用于人工回退。

为什么要这样拆：

- redeploy 不应该把正在使用的主机登记册和审计记录覆盖掉；
- 运行时工作区和代码目录分开后，发布版本更新和 operator 现场数据更新就不会互相踩踏。

当前还有三个正式部署约束：

- 认证是 fail-closed。
  换句话说，正式运行入口如果拿不到用户名或密码，或者密码还是示例值，就直接拒绝启动，而不是降级成匿名站点。只有 `/health` 继续保持免认证，方便探活。
- redeploy 不覆盖远端 `.env`。
  模块重发时会保留远端 `.env`，避免把线上密码、域名、端口和镜像策略重置回示例值。
- authority review surface 会刷新，但 operator 现场数据不会被静默覆盖。
  具体来说，`repos/remote_proxy` 的脚本、env 模板和部署 runbook 会从 `.runtime-seed` 刷新到 `.runtime-workspace`，避免 handoff 继续引用旧模板；而 `nodes.yaml`、`subscriptions.yaml` 这类现场清单不会被无条件覆盖。
  当前 redeploy 的正式规则已经细化成两段：
  - 如果远端 `.runtime-workspace` 里的现场清单仍然等于“上一版 `.runtime-seed` 镜像”，允许自动刷新到这次的新 seed；
  - 如果远端现场清单已经偏离上一版 seed，说明站点上已经有新的本地编辑，这时必须保留并暴露漂移，不能静默盖掉。

当前已完成：

- 远端带认证的 operator Web
- `/health` 免认证健康检查
- 模板化页面壳、轻量静态资源和更适合值守的摘要/搜索/反馈结构
- 只读接入 `cliproxy-control-plane` 的 worker/oauth quota 视图
- 页面内新增/删除主机计划入口
- deploy/decommission authority handoff 入口
- 计划、审计、移交单都落在受管目录
- `public` 脱敏快照导出与 `public` 只读消费链路
- `.runtime-workspace` -> `repos/proxy_ops_private/inventory/*` 的 reviewed sync-back 入口
- redeploy 时“旧 seed 镜像自动刷新、已漂移现场保留”的现场清单同步
- `infra-core` 模块注册脚本、固定镜像标签和人工回退备份

当前仍未完成：

- 平台自己代执行远端宿主机部署
- 匿名公网 public 站点
- `.runtime-workspace` 变更的自动 Git commit / push / 回退编排

当前网络入口结论：

- 推荐入口是域名 `https://proxy-platform-operator.svc.prod.lab.gglohh.top:27111/`
- `18082` 直连端口在宿主机内已经可用，但当前外部直连未放通，所以它是“宿主机 fallback”，不是主要公网入口

当前 `CLIProxyAPIPlus` worker 的权责边界如下：

- `proxy-platform`
  负责统一帮助入口、工作区编排、repo 同步、宿主机 toolchain 诊断和平台级文档。
- `remote_proxy`
  负责 `cliproxy-plus` 的真实部署基线、版本切换、Podman/systemd 服务生成以及 usage 备份恢复生命周期。

当前 `proxy-platform jobs plan-deploy-host` / `jobs plan-decommission-host` 的作用，是把这类动作先固定成平台可审阅的 plan / audit / authority handoff 入口，不替代下游 authority path。

这件事在当前项目里的准确含义是：

- 页面可以帮你看清“这台主机应该交给哪个 owner、走哪条入口、回退归谁负责”；
- 页面不会自己 SSH 到 Lisahost、vmrack1、vmrack2 或 dedirock 上执行安装。

当前已知主机分类也已经补进私有登记册：

- `lisahost`: `standalone_vps + cliproxy-plus`
- `vmrack1`: `standalone_vps + cliproxy-plus`
- `vmrack2`: `standalone_vps + cliproxy-plus`
- `dedirock`: `standalone_vps + cliproxy-plus`

当前私有 rollout 约束也已经收敛为：

- 四台节点都允许进入 `cliproxy-plus` rollout
- `dedirock` 是默认首个验证 / canary 节点
- 正式扩散顺序是 `dedirock -> vmrack1 -> vmrack2 -> lisahost`

这一步是必要的。因为如果登记册不带 `deployment_topology` 和 `runtime_service`，远端站点虽然能展示主机，但不能为现有主机生成 deploy/decommission 计划。

当前 Web 也已经从“一个大页面”拆成了多页面 operator shell：

- `/`: 总览
- `/hosts`: 主机现场清单
- `/subscriptions`: 订阅入口
- `/providers`: 本地 provider 生命周期
- `/worker-quotas`: 远端 worker / oauth 文件配额
- `/jobs`: 主机登记作业
- `/audit`: 作业审计

其中有两条当前使用口径需要特别记住：

- 首页“健康可用”来自最近一次 TCP 最小探测，不会把 `unknown` 当成 `healthy`。
- `/subscriptions` 会把普通 HTTPS 订阅 URL 和 `hiddify://...` Deep Link 分开表达；前者用于手动填写订阅地址，后者用于拉起 Hiddify 或从剪贴板导入。
- `/worker-quotas` 只读消费 `cliproxy-control-plane` 的 `/api/accounts/latest-view` 与 `/api/tactical-stats/overview`；如果权威控制面没有返回最新快照，页面会明确显示“无最新配额快照”，而不是在 `proxy-platform` 里伪造 quota 真相。

## 远端部署与维护

首次或重发部署：

```bash
./deploy/infra-core-module/register_module.sh
ssh -p 52117 gaoyx@112.28.134.53 'cd /mnt/hdo/infra-core && scripts/modulectl.sh up proxy-platform-operator'
```

构建默认走 `docker.m.daocloud.io` + 阿里云 PyPI + 阿里云 Debian 镜像；如果镜像站有变更，可以通过 `PYTHON_BASE_IMAGE`、`PIP_INDEX_URL`、`PIP_TRUSTED_HOST`、`APT_MIRROR_URL` 覆盖。

如果你希望把“注册模块 + 拉起服务 + 健康失败时自动回退”收成一个入口，现在可以用：

```bash
ENABLE_AUTO_ROLLBACK=1 ./deploy/infra-core-module/redeploy_with_rollback.sh
```

它默认仍然是关闭自动回退的。换句话说，仓库不会在你没明确开启时擅自回切；只有显式给出 `ENABLE_AUTO_ROLLBACK=1`，脚本才会在健康检查失败后尝试恢复上一版镜像和最新备份。

第一次部署如果远端还没有 `.env`，脚本会先生成一份模板，但其中认证密码默认留空。换句话说，第一次真正启动前，必须先把 `.env` 里的认证字段改成真实值。

更新认证口令或域名：

```bash
ssh -p 52117 gaoyx@112.28.134.53 'vi /mnt/hdo/infra-core/modules/proxy-platform-operator/.env'
ssh -p 52117 gaoyx@112.28.134.53 'cd /mnt/hdo/infra-core && scripts/modulectl.sh up proxy-platform-operator'
```

查看远端容器状态：

```bash
ssh -p 52117 gaoyx@112.28.134.53 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep proxy-platform-operator'
```

查看远端健康检查：

```bash
curl -k https://proxy-platform-operator.svc.prod.lab.gglohh.top:27111/health
```

如果模块起不来，先检查认证配置是不是缺项：

```bash
ssh -p 52117 gaoyx@112.28.134.53 'cd /mnt/hdo/infra-core && scripts/modulectl.sh logs proxy-platform-operator | tail -n 50'
```

如果 `.env` 里缺少 `PROXY_PLATFORM_OPERATOR_BASIC_AUTH_USERNAME` 或 `PROXY_PLATFORM_OPERATOR_BASIC_AUTH_PASSWORD`，或者密码还是示例值，当前版本会直接拒绝启动。这是故意设计的，目的就是防止“配置丢了一半，站点却裸奔上线”。

人工回退：

1. 在远端模块目录把 `.env` 中的 `PROXY_PLATFORM_OPERATOR_IMAGE` 改回上一版镜像标签，或者恢复 `.deploy-backups/` 里的源码快照。
2. 回到 `infra-core` 根目录执行 `scripts/modulectl.sh up proxy-platform-operator`。

需要强调的是：这里的回退是“模块发布物回退”，不是“远端代理节点回退”。远端代理节点的生命周期回退 owner 仍然是 `remote_proxy` 或 `infra_core`。

## 设计原则

- CLI first，Web later
- submodule pinning + manifest semantics
- platform shell only
- expected state + observed state + projection
- dry-run or authority handoff before remote write
- ADR before architecture drift
