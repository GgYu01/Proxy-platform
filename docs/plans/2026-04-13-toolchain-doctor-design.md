# Toolchain Doctor 设计说明

## 背景

`proxy-platform` 现在已经能做工作区仓库编排和 bootstrap 诊断，但还缺一个平台级入口去回答更基础的问题：

- 当前宿主机的 Python / Podman / Docker Compose 等依赖是否满足目标拓扑；
- 如果默认 `python3` 不满足要求，是否存在可稳定切换的版本化解释器；
- Debian 10 / Debian 11 / Ubuntu 等主机上，针对 `remote_proxy` 的 `cliproxy-plus` 独立部署和 `CliProxy-control-plane` compose 运行，分别缺什么、该怎么修复。

这类信息已经零散存在于下游仓库文档和脚本里，但没有在统一入口中收敛成一个可执行、可测试、可扩展的诊断界面。

## 目标

新增 `doctor toolchain` 能力：

- 以 `platform.manifest.yaml` 里的 profile 为准，统一描述宿主机工具链要求；
- 在本机执行只读检测，输出 OS、解释器候选、命令是否存在、版本是否满足；
- 对 Python 类依赖给出“当前可用的稳定候选解释器”建议；
- 不做自动安装、不改系统默认解释器、不写远端主机。

## 备选方案

### 方案 A：把所有兼容逻辑硬编码进 CLI

优点：

- 代码最少，最快出结果。

缺点：

- 需求一旦扩展到更多仓库或更多部署拓扑，逻辑会迅速散落到 `cli.py`。
- Web 工作台未来也无法复用这些语义，只能重复实现一遍。
- 违背“复杂性收敛到 manifest / adapter / schema”的仓库边界。

### 方案 B：在 manifest 中声明 host toolchain profile，由 CLI 解释执行

优点：

- 需求模型进入 manifest，CLI 和未来 Web 都可共用；
- 下游仓库边界仍然清晰，平台壳只维护“要求”和“诊断”，不复制部署内核；
- 可以把 `remote_proxy` 已有兼容层结论与 `CliProxy-control-plane` 的 `pyproject/docker-compose` 约束统一表达。

缺点：

- 需要扩展 manifest schema 和对应测试；
- 需要一个新的 toolchain 诊断模块。

### 方案 C：直接调用下游仓库脚本做诊断

优点：

- 复用已有脚本，短期看似省事。

缺点：

- `remote_proxy` 和 `CliProxy-control-plane` 的输入输出格式不统一；
- 平台壳会变成脚本转发器，而不是清晰的统一入口；
- CLI 输出难以稳定测试，Web 也难直接复用。

## 结论

采用方案 B。

`proxy-platform` 只新增 manifest 驱动的诊断能力，不复制下游部署脚本逻辑，也不尝试在这里做“自动切版本安装器”。平台壳负责回答“缺什么、有没有稳定候选、推荐怎么接线”，真正的安装/切换仍回到下游仓库。

## 设计

### 1. Manifest 扩展

新增 `toolchains` 段，表达平台已知的宿主机 profile，例如：

- `cliproxy_plus_standalone`
  对齐 `remote_proxy` 的 `cliproxy-plus` 独立 VPS 路径。
- `control_plane_compose`
  对齐 `CliProxy-control-plane` 本地/宿主机 compose 运行路径。

每个 profile 至少包含：

- `id`
- `display_name`
- `description`
- `required_modes`
- `repo_ids`
- `python`
  - `min_version`
  - `candidates`
  - `env_hint`
- `commands`
  - `id`
  - `display_name`
  - `argv`
  - `fallback_argvs`

### 2. 诊断模块

新增 `src/proxy_platform/toolchain.py`：

- 读取 `/etc/os-release`，输出 `ID` / `VERSION_ID` / `PRETTY_NAME`；
- 逐个检查 profile 中声明的命令；
- 对 Python 候选解释器做版本探测，选出第一个满足最小版本的解释器；
- 汇总成结构化结果，供 CLI 渲染和测试断言使用。

### 3. CLI 面

扩展为：

```bash
python -m proxy_platform doctor toolchain --profile cliproxy_plus_standalone
python -m proxy_platform doctor toolchain --profile control_plane_compose
```

输出原则：

- 一眼能看出 `ok=true/false`；
- 对 Python 输出 `selected=` 和 `env_hint=`；
- 对命令输出 `exists=`、`version=`、`status=`；
- 缺失或版本不满足时返回非零。

### 4. 边界

- 不做自动安装；
- 不做远端 SSH；
- 不直接执行 `remote_proxy` 的 `runtime_compat.sh`；
- 不把控制面部署逻辑复制到平台壳。

## 测试策略

- manifest schema 解析测试；
- 纯单元测试覆盖 Python 版本比较、候选选择、命令 fallback；
- CLI 测试覆盖：
  - profile 存在且通过；
  - Python 不满足时退出码非零；
  - fallback 命令可用时仍判定通过。

## 执行约束

用户已经明确授权“持续迭代，不用询问是否下一阶段”，因此本设计按推荐方案直接进入实现，不再做中间审批停顿。
