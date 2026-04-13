# Progress

## 2026-04-13

- 初始化 `proxy-platform` 仓库。
- 确认第一波实现目标为平台壳最小闭环，而非全量平台。
- 写入平台级 `AGENTS.md`、`README.md`、`platform.manifest.yaml` 与 5 份 ADR。
- 写入 `.gitmodules`，并补 manifest 与 gitmodules 的一致性校验。
- 先写测试，再实现 `manifest validate`、`repos list`、`doctor`、`init`、`sync`。
- 新增 manifest 驱动的 host toolchain profile，并暴露 `doctor toolchain --profile <id>`。
- `init` / `sync` 现在支持三类物化路径：
  - 现有 Git 仓库执行 `git fetch --all --tags`
  - 有 `local_override_path` 时建立本地符号链接
  - 两者都没有时按 `default_url` 做 clone
- `git clone` 失败时会回收半残目录，避免后续运行被误判成“已有工作区”。
- 本地验证结果：
  - `. .venv/bin/activate && pytest -q` -> `32 passed`
  - `. .venv/bin/activate && python -m proxy_platform manifest validate` -> `manifest: ok`
  - `. .venv/bin/activate && python -m proxy_platform repos list ...` -> 输出 public 模式 repo 状态
  - `. .venv/bin/activate && python -m proxy_platform doctor ...` -> 正确报告未初始化 submodule 工作区缺失 required repos
  - `. .venv/bin/activate && python -m proxy_platform init --mode operator --dry-run ...` -> 正确输出基于 local override 的初始化计划
  - 临时 workspace smoke：真实执行 `init` 后，`doctor` 从 `ok=false` 变为 `ok=true`
  - 临时 workspace smoke：`init` 在无 override 且 `default_url` 指向本地 Git 仓库时会成功 clone
  - 临时 workspace smoke：`init` 在不可达远端上返回 `EXIT_CODE=2`，输出 `failed to clone ...`，且失败目录被清理
  - 临时 workspace smoke：`sync` 在已有 Git 仓库远端不可达时返回 `EXIT_CODE=2`，输出 `failed to fetch ...`
  - `. .venv/bin/activate && python -m proxy_platform doctor toolchain --profile cliproxy_plus_standalone` -> 当前主机 Python/curl/jq/systemd 满足，但 `podman` 缺失，返回 `EXIT_CODE=2`
  - `. .venv/bin/activate && python -m proxy_platform doctor toolchain --profile control_plane_compose` -> 当前主机 Python 满足，但 `docker` / `docker-compose` 缺失，返回 `EXIT_CODE=2`
  - 非法 manifest smoke：`default_mode=broken` 时 `manifest validate` 返回 `EXIT_CODE=2`
  - `.gitmodules` 与 `platform.manifest.yaml` 的 path / url 一致性已纳入测试与运行时校验
  - manifest 现在也会拒绝重复 `toolchain profile id`，避免 schema 被静默覆盖
- 尝试追加只读 reviewer 子代理，但未在超时窗口内返回有效评审结论；本轮质量结论以本地 TDD、smoke 和 fresh verification 为准。
