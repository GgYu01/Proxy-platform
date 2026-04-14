# proxy-platform

统一入口薄平台壳仓库。

它负责：

- 统一 CLI / 未来 Web 工作台入口
- 统一 repo-of-repos 编排
- 统一 manifest、帮助系统、诊断输出
- 统一“主机登记册 + 观测回报 + 订阅派生”状态模型
- 统一平台级 AGENTS / ADR / review checklist

它不负责：

- 重写 `CliProxy-control-plane` 的 northbound `/v1` 网关
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
  - `subscriptions list --mode operator`
  - `providers list`
  - `web --mode operator`
  - `hosts --registry ... [--observations ...]`
  - `subscriptions preview --registry ... [--observations ...]`

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

当前只提供只读入口：

```bash
python -m proxy_platform hosts list --mode operator
python -m proxy_platform subscriptions list --mode operator
python -m proxy_platform web --mode operator
python -m proxy_platform hosts --registry ./registry.yaml --observations ./observations.yaml
python -m proxy_platform subscriptions preview --registry ./registry.yaml --observations ./observations.yaml
```

当前模式边界：

- `hosts list` / `subscriptions list` / `web` 读取的是 `Proxy_ops_private` 里的私有登记册，因此当前只在 `operator` 模式开放。
- `public` 模式当前只保留公开仓库、公开 toolchain 和观测状态插槽，不直接读取私有现场清单。
- 如果后续需要公开页面或公开订阅入口，必须先引入一份脱敏后的 public projection/state source，而不是让 `public` 模式直接越过 private 边界。

当前订阅派生规则是：

- 只要主机在登记册里 `enabled=true` 且 `include_in_subscription=true`，就进入订阅。
- `healthy` / `degraded` / `down` / `unknown` 只影响展示与审计，不自动把主机从订阅里移除。
- 登记册里没有的观测结果会被标成“未知观测主机”，用于后续盘点和治理。

对应文档：

- `docs/adr/ADR-0008-platform-state-model.md`
- `docs/adr/ADR-0009-repository-ownership-matrix.md`
- `docs/repo-boundaries.md`

## 推荐工作区布局

推荐把整个平台工作区收敛到单根：

```text
/workspaces/proxy-platform/
  README.md
  platform.manifest.yaml
  repos/
    remote_proxy/
    cliproxy-control-plane/
    proxy_ops_private/
    remote_browser/
  archive/
    multi_repo_arch_analysis/
```

规则如下：

- `/workspaces/proxy-platform` 是唯一权威根。
- `repos/` 下的仓库是权威工作树。
- `archive/` 下的目录只用于保留分析副本、历史快照和临时验证材料，不作为源码真相源。
- 历史旧路径已经移除；如需追溯旧计划、日志和分析材料，请到 `archive/` 下查看。

## 快速开始

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
python -m proxy_platform manifest validate
python -m proxy_platform repos list
python -m proxy_platform doctor
python -m proxy_platform doctor toolchain --profile cliproxy_plus_standalone
python -m proxy_platform init --mode public
python -m proxy_platform sync --mode public
python -m proxy_platform hosts list --mode operator
python -m proxy_platform subscriptions list --mode operator
```

## Host Toolchain Profiles

当前 manifest 已声明两类可复用宿主机 profile：

- `cliproxy_plus_standalone`
  对齐 `remote_proxy` 中 `cliproxy-plus` 独立 VPS 路径，关注 `Python >= 3.9`、`curl`、`jq`、`podman`、`systemctl`。
- `control_plane_compose`
  对齐 `CliProxy-control-plane` compose 路径，关注 `Python >= 3.11`、`docker`、`docker compose` / `docker-compose`。

示例：

```bash
python -m proxy_platform doctor toolchain --profile cliproxy_plus_standalone
python -m proxy_platform doctor toolchain --profile control_plane_compose
```

对 Python 类依赖，输出会额外给出：

- 当前选中的兼容解释器
- 解释器绝对路径
- 对应环境变量提示，例如 `REMOTE_PROXY_PYTHON_BIN`

这让平台壳可以先回答“当前主机是否可用、若不可用缺什么、若默认 python 不满足时有没有稳定候选”，但仍然把真正的安装/切换动作留在下游仓库。

## CLIProxyAPIPlus Worker 升级边界

当前 `CLIProxyAPIPlus` worker 的权责边界如下：

- `proxy-platform`
  负责统一帮助入口、工作区编排、repo 同步、宿主机 toolchain 诊断和平台级文档。
- `remote_proxy`
  负责 `cliproxy-plus` 的真实部署基线、版本切换、Podman/systemd 服务生成以及 usage 备份恢复生命周期。

推荐操作顺序：

1. 在本地修改并评审 `remote_proxy` 仓库内的镜像版本、脚本或文档。
2. 将远端主机上的 `remote_proxy` 工作树同步到该已评审版本。
3. 在远端主机执行仓库入口命令，而不是手工改 live systemd 文件：
   - `./scripts/service.sh cliproxy-plus update`
   - `./scripts/service.sh cliproxy-plus switch-version <image>`

当前 Lisahost worker 的真实运行形态是 `systemd + podman`，不是 `docker compose`。OAuth / auth 文件、`config.yaml`、日志目录通过 bind mount 保存在宿主机 `state/cliproxy-plus/` 下；usage 统计则需要依赖 `remote_proxy` 生命周期脚本的导出/导入保护，而不是把 `usage/` 目录误认为实时数据库。

## 设计原则

- CLI first，Web later
- submodule pinning + manifest semantics
- platform shell only
- expected state + observed state + projection
- dry-run before write
- ADR before architecture drift
