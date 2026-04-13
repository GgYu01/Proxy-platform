# Findings

## 当前决定

- 新仓库位置：`/workspaces/proxy_own/proxy-platform`
- 先做 CLI-first 的薄平台壳
- `git submodule + platform.manifest.yaml` 共同表达依赖与语义
- 本阶段用 doctor / init / sync / toolchain profiles 建立最小闭环

## 第一波实现对象

- CLI 命令面
- manifest schema
- host toolchain profiles
- `.gitmodules` 与 manifest 一致性校验
- repo status 检测
- 基于 local override 的本地工作区物化
- 基于 `default_url` 的 clone / fetch 失败收敛
- 基于 manifest profile 的宿主机兼容诊断
- 平台级治理文档
- ADR 文档

## 暂不实现

- 真实 Web 工作台
- 真实 job runner
- 真实远端 apply/publish 写操作
- 自动安装或切换系统级运行时
- 自动远端 SSH 检查与修复
