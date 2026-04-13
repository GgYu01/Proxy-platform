# Toolchain Doctor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 `proxy-platform` 增加 manifest 驱动的 `doctor toolchain`，统一诊断宿主机 Python 和关键命令是否满足 `cliproxy-plus` 与 control-plane 运行要求。

**Architecture:** 在 `platform.manifest.yaml` 中声明 host toolchain profile，由新的 `toolchain.py` 做只读检测，CLI 只负责渲染结果与退出码。这样复杂性进入 manifest 和诊断模块，而不是散落在 `cli.py` 或 README 里。

**Tech Stack:** Python 3.9+, argparse, dataclasses, subprocess, shutil.which, PyYAML, pytest

---

### Task 1: 扩展 manifest schema

**Files:**
- Modify: `platform.manifest.yaml`
- Modify: `src/proxy_platform/manifest.py`
- Test: `tests/test_manifest.py`

**Step 1: 写失败测试**

- 新增 manifest 测试，断言 `toolchains` 能被解析，并且关键 profile / python 最低版本 / 命令定义存在。

**Step 2: 运行失败测试**

Run: `pytest tests/test_manifest.py -q`
Expected: FAIL，因为 manifest 还没有 `toolchains` 解析逻辑。

**Step 3: 写最小实现**

- 为 manifest 增加 `ToolchainProfile`、`PythonRequirement`、`CommandRequirement` 数据结构；
- 解析 `toolchains` 段；
- 补最小校验。

**Step 4: 运行测试**

Run: `pytest tests/test_manifest.py -q`
Expected: PASS

### Task 2: 实现 toolchain 诊断模块

**Files:**
- Create: `src/proxy_platform/toolchain.py`
- Test: `tests/test_toolchain.py`

**Step 1: 写失败测试**

- 覆盖 Python 候选解释器选择；
- 覆盖命令 fallback；
- 覆盖 profile 整体 `ok=false` 汇总。

**Step 2: 运行失败测试**

Run: `pytest tests/test_toolchain.py -q`
Expected: FAIL，因为模块尚不存在。

**Step 3: 写最小实现**

- 读取 `/etc/os-release`；
- 检测命令存在与版本输出；
- 选择满足要求的 Python 候选；
- 生成结构化诊断结果。

**Step 4: 运行测试**

Run: `pytest tests/test_toolchain.py -q`
Expected: PASS

### Task 3: 暴露 CLI 子命令

**Files:**
- Modify: `src/proxy_platform/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: 写失败测试**

- 新增 `doctor toolchain --profile cliproxy_plus_standalone` 的 CLI 输出测试；
- 新增 profile 不满足时返回 `2` 的测试。

**Step 2: 运行失败测试**

Run: `pytest tests/test_cli.py -q`
Expected: FAIL，因为 CLI 还不支持 `doctor toolchain`。

**Step 3: 写最小实现**

- 给 `doctor` 增加可选子命令；
- 保持现有 workspace doctor 向后兼容；
- 输出稳定文本和退出码。

**Step 4: 运行测试**

Run: `pytest tests/test_cli.py -q`
Expected: PASS

### Task 4: 更新文档并做全量验证

**Files:**
- Modify: `README.md`
- Modify: `findings.md`
- Modify: `progress.md`

**Step 1: 跑全量测试**

Run: `pytest -q`
Expected: PASS

**Step 2: 跑命令级 smoke**

Run: `python -m proxy_platform doctor toolchain --profile cliproxy_plus_standalone`
Expected: 输出 OS / Python / 命令状态

Run: `python -m proxy_platform doctor toolchain --profile control_plane_compose`
Expected: 输出 compose 相关依赖状态

**Step 3: 更新文档**

- README 增加新命令说明；
- findings / progress 记录本轮新增能力与验证结果。
