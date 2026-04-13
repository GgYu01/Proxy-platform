# proxy-platform

统一入口薄平台壳仓库。

它负责：

- 统一 CLI / 未来 Web 工作台入口
- 统一 repo-of-repos 编排
- 统一 manifest、帮助系统、诊断输出
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

当前 `init` / `sync` 的执行边界：

- 如果目标工作区已经存在 repo 目录或链接，则保持原状
- 如果 manifest 提供了 `local_override_path`，则优先在 `repos/` 下建立本地符号链接
- 如果既没有现成工作区，也没有 `local_override_path` 可用，则明确返回非零并提示后续仍需 clone/接线
- 不做远端主机写操作
- 不自动执行网络 clone

当前 `manifest validate` 还会校验 `.gitmodules` 和 `platform.manifest.yaml` 的 path / url 是否一致。

## 快速开始

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
python -m proxy_platform manifest validate
python -m proxy_platform repos list
python -m proxy_platform doctor
python -m proxy_platform init --mode public
python -m proxy_platform sync --mode public
```

## 设计原则

- CLI first，Web later
- submodule pinning + manifest semantics
- platform shell only
- dry-run before write
- ADR before architecture drift
