# web-console

统一 Web 工作台占位目录。

当前阶段已经有一个最小可运行的 Web 控制台实现，入口在 `src/proxy_platform/web_app.py`，用于验证：

- 主机视图 API
- 订阅派生 API
- 本地 provider 生命周期 API
- 基于 inventory 文件的最小增删入口

本目录仍然只保留未来完整前端的架构插槽。
后续如果接入正式前端，应优先复用现有 control-plane UI，而不是在这里重写其业务内核。
