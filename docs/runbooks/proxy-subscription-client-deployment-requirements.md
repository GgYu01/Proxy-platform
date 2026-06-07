# 代理订阅客户端部署需求清单

本文整理 Hiddify 迁移到 Clash Verge Rev / mihomo 过程中已经确定的全部客户端侧部署需求。它是需求与验收清单，不是私有 inventory，也不保存 secrets。

## 范围

- 面向中国大陆用户发布和维护代理订阅服务。
- 本地客户端优先使用 Clash Verge Rev + mihomo core，不再以 Hiddify 作为推荐客户端。
- 对 Windows、macOS、Linux 发布一份跨平台 `mihomo-universal.yaml`。其中不适用于当前平台的进程名或路径规则应自然 miss，不应导致运行错误。
- Windows 本机需要支持管理员权限下的 TUN 透明代理、规则代理、开机自启和无手动确认运行。
- Windows 本机迁移完成后，Hiddify 和 ProxyBridge 不应保留为活动代理客户端，也不应保留明确命中的配置、缓存或快捷入口。

## 权威来源

- 私有节点和订阅真相继续在 `repos/proxy_ops_private/inventory/`。
- 订阅产物由 `repos/proxy_ops_private/scripts/render_artifacts.py` 生成。
- 生成后的客户端配置为 `repos/proxy_ops_private/generated/subscriptions/mihomo-universal.yaml`。
- Windows 本机运行配置复制到 `C:\ProgramData\mihomo\mihomo-universal.yaml`。
- SYSTEM 用户安全配置复制到 `C:\Windows\System32\config\systemprofile\.config\mihomo\mihomo-universal.yaml`。
- 根仓文档不得保存真实 secrets；节点 secrets 继续留在 private authority tree。

## 订阅发布产物

订阅页面需要提供以下入口：

- `mihomo-universal.yaml`：Clash Verge Rev / mihomo 推荐配置。
- `mihomo-process-routing.md`：进程路由说明。
- `v2ray_nodes.txt`：通用 VLESS 订阅。
- 单节点 `v2ray_node_<node>.txt`。
- `singbox-client-profile.json` / `singbox_remote_profile.json`。
- 不再发布 Hiddify deep link 作为页面入口或生成产物；如需兼容其它客户端，使用原始 VLESS 订阅 URL。

当前公开订阅 base URL：

- `https://proxy-subscriptions.svc.prod.lab.gglohh.top:27111/subscriptions`

Windows 本地安装脚本可使用的备用订阅 URL：

- `http://69.5.53.82:18080/subscriptions/mihomo-universal.yaml`

订阅域名或 IP 必须在 mihomo 配置中走 `DIRECT`，避免配置更新依赖已成功工作的代理路径。

## 节点优先级

当前订阅故障转移优先级要求如下：

1. `us_sea_bgp_01` / `GG-US-SEA-BGP-01` / host `69.5.53.82`
2. `lisahost` / `GG-Lisa-Stable`
3. `lisahost_kr` / `GG-Lisahost-KR`
4. `vmrack1` / `GG-Vmrack1`
5. `vmrack2` / `GG-Vmrack2`
6. `dedirock` / `GG-Dedirock`

`PROXY` 组必须先放第一优先级节点，再放 `Auto`，再放剩余节点，最后放 `DIRECT` 作为手动逃生选项。

## mihomo 配置需求

生成的 profile 必须满足：

- `mode: rule`。
- `find-process-mode: always`。
- `geodata-mode: false`。
- 使用 DustinWin/ruleset_geodata 的 `mihomo-ruleset` release 资产。
- rule provider 使用 `mrs` 格式，覆盖 `privateip`、`cn`、`cnip`、`apple-cn`、`microsoft-cn`、`google-cn`、`ads`、`proxy`、`gfw`、`tld-proxy`、`telegramip`。
- 私有地址、中国大陆、Apple China、Microsoft China、Google China、China IP、QQ、微信、Cursor、Edge Beta、订阅更新流量走 `DIRECT`。
- Telegram IP 和未命中国内规则的非大陆流量走 `PROXY`。
- 最终兜底规则必须是 `MATCH,PROXY`。
- 不使用 `GEOIP` 规则。
- `dns.fallback-filter.geoip: false`。
- 不创建、不引用 `AI-PROXY` 分组。
- 不添加 Qwen 专门域名规则。Qwen 必须遵循普通大陆/非大陆规则集行为；当前验证显示 `chat.qwen.ai` 命中 `cn` 并走 `DIRECT`。

## TUN 需求

profile 必须启用 mihomo TUN：

- `tun.enable: true`
- `tun.stack: mixed`
- `tun.auto-route: true`
- `tun.auto-redirect: true`
- `tun.strict-route: true`
- `tun.auto-detect-interface: true`
- DNS hijack: `any:53`

Windows 上由 SYSTEM mihomo 拥有 TUN。Clash Verge Rev 不能同时再拥有另一个 TUN 实例。

## Windows 运行态所有权

Windows 本机运行态必须拆分如下：

- SYSTEM mihomo：
  - executable: `C:\Tools\mihomo\mihomo-windows-amd64.exe`
  - config: `C:\Windows\System32\config\systemprofile\.config\mihomo\mihomo-universal.yaml`
  - mixed port: `7890`
  - controller: `127.0.0.1:9090`
  - DNS listen: `1053`
  - TUN adapter: `Meta`
  - scheduled task: `Mihomo TUN Transparent Proxy`
- Clash Verge Rev GUI / service runtime：
  - GUI executable: `C:\Program Files\Clash Verge\clash-verge.exe`
  - service: `clash_verge_service`
  - core executable: `C:\Program Files\Clash Verge\verge-mihomo.exe`
  - config root: `%APPDATA%\io.github.clash-verge-rev.clash-verge-rev`
  - mixed port: `7897`
  - controller: `127.0.0.1:9097`
  - pipe: `\\.\pipe\verge-mihomo`
  - `tun.enable: false`
  - `dns.enable: false`
  - scheduled task: `Clash Verge Rev Admin Startup`

`verge.yaml` 应保持：

- `tun_tray_icon: false`
- `enable_tun_mode: false`
- `enable_system_proxy: false`
- `enable_proxy_guard: true`
- `enable_auto_launch: true`
- `enable_silent_start: true`

这样可以避免端口和 TUN 冲突，同时保留 Clash Verge Rev 作为 GUI。

## 跨平台进程规则需求

`mihomo-universal.yaml` 合并 Windows、macOS、Linux 的进程规则。不属于当前系统的进程名或路径规则应 miss，不应导致启动失败。

YAML 中直接保护块必须清晰标记，便于用户编辑：

- `# === USER-EDITABLE PROCESS DIRECT PROTECTIONS ===`
- `# === END USER-EDITABLE PROCESS DIRECT PROTECTIONS ===`

YAML 中代理覆盖块也必须清晰标记：

- `# === USER-EDITABLE PROCESS PROXY OVERRIDES ===`
- `# === END USER-EDITABLE PROCESS PROXY OVERRIDES ===`

用户需要能通过注释某条进程/路径规则来关闭对应进程级行为；关闭后由域名和 IP 规则决定 `DIRECT` 或 `PROXY`。

## Windows 直接进程保护

Windows 直接进程规则当前包括：

- `QQ.exe`
- `QQProtect.exe`
- `TIM.exe`
- `WeChat.exe`
- `WeChatAppEx.exe`
- `WeChatBrowser.exe`
- `WeChatOCR.exe`
- `Weixin.exe`
- `WXWork.exe`
- `Cursor.exe`
- `cursor.exe`
- `cursor-agent.exe`
- `wps.exe`
- `wpp.exe`
- `et.exe`
- `wpspdf.exe`
- `wpscloudsvr.exe`
- `ksolaunch.exe`
- `wpsupdate.exe`
- `ksomisc.exe`

Windows 直接路径规则当前包括：

- `C:\Program Files\Microsoft\Edge Beta\Application\msedge.exe`
- `C:\Program Files (x86)\Microsoft\Edge Beta\Application\msedge.exe`
- `C:\Users\*\AppData\Local\Microsoft\Edge Beta\Application\msedge.exe`
- `C:\Users\*\AppData\Local\Programs\Cursor\*`
- `C:\Users\*\AppData\Local\Kingsoft\WPS Office\*`

Edge Beta 需要显式直接保护，避免普通 Edge Beta 浏览被进程名强制代理。

WPS Office / 云盘 / 更新需要进程级 DIRECT，避免云盘同步、登录或更新请求被兜底 `MATCH,PROXY` 误伤。

## WPS / Kingsoft 域名 DIRECT 规则

在 Cursor 域名块之后、进程规则之前，profile 必须包含：

- `DOMAIN-KEYWORD,kingsoft,DIRECT`
- `DOMAIN-SUFFIX,kingsoft.com,DIRECT`
- `DOMAIN-SUFFIX,kingsoft-office-service.com,DIRECT`
- `DOMAIN-SUFFIX,wps.cn,DIRECT`
- `DOMAIN-SUFFIX,wpscdn.cn,DIRECT`
- `DOMAIN-SUFFIX,wpscdn.com,DIRECT`
- `DOMAIN-SUFFIX,kdocs.cn,DIRECT`
- `DOMAIN-SUFFIX,kdocs.com,DIRECT`
- `DOMAIN-SUFFIX,ksosoft.com,DIRECT`
- `DOMAIN-SUFFIX,ksord.com,DIRECT`
- `DOMAIN-SUFFIX,wpsplus.com,DIRECT`

不得给 `msedgewebview2.exe` 添加全局 DIRECT；WPS 内嵌页应依赖上述域名规则或 WPS 安装路径 wildcard。

## Clash Verge vs SYSTEM mihomo 监控

Windows 上 Clash Verge Rev 只是 GUI / service shell，**不是** TUN 透明代理的真相源：

| 监控项 | 正确入口 | 错误入口 |
|--------|----------|----------|
| TUN 连接 / 规则命中 / 实时链路 | SYSTEM mihomo `http://127.0.0.1:9090/ui/` | Clash Verge 连接页（9097） |
| mixed-port | `127.0.0.1:7890` | `127.0.0.1:7897` |
| external-controller | `127.0.0.1:9090` | `127.0.0.1:9097` |

Verge 显示 TUN 关闭、连接列表为空，在双实例架构下是**预期行为**，不代表 SYSTEM mihomo 未工作。

## 进程级 PROXY 允许列表

`mihomo-universal.yaml` 允许的进程级 `PROXY` 路径包括：

- Simprint Chrome profile 浏览器 2 条
- Antigravity / ChatGPT / ChatGPT Atlas / Codex 安装路径（Windows + macOS + Linux）
- 跨平台 universal 合并后，当前应为 **29** 条 `PROCESS-PATH*` PROXY 规则

禁止添加：

- `PROCESS-NAME,simprint.exe,PROXY`
- `PROCESS-NAME,msedgewebview2.exe,PROXY`
- 宽泛 `node` / `python` 进程代理

验证时要求 `file_disallowed_process_proxy_count=0` 且 `runtime_disallowed_process_proxy_count=0`；`file_allowed_process_proxy_count` 必须等于 render 输出中的允许 PROXY 路径计数（当前 **29**）。

## macOS 直接进程保护

macOS 直接进程规则当前包括：

- `QQ`
- `WeChat`
- `Weixin`
- `WXWork`
- `Cursor`
- `Cursor Helper`
- `Cursor Helper (GPU)`
- `Cursor Helper (Plugin)`
- `Cursor Helper (Renderer)`
- `cursor-agent`

macOS 直接路径规则当前包括：

- `/Applications/Cursor.app/Contents/*`

## Linux 直接进程保护

Linux 直接进程规则当前包括：

- `qq`
- `wechat`
- `weixin`
- `wxwork`
- `cursor`
- `cursor-agent`

Linux 直接路径规则当前包括：

- `/usr/bin/cursor*`

## AI 与开发工具进程需求

已调查对象包括 Edge、ChatGPT、ChatGPT Atlas、Codex app、Codex CLI、Antigravity、Antigravity CLI、Cursor、Cursor CLI，以及 `codexsdk`、`antigravitysdk`、`cursorsdk` 这类 SDK 使用形态。

当前要求是保守处理：

- 不按宽泛进程名强制代理这些工具。
- 不为 `node`、`python`、`msedgewebview2.exe` 或通用浏览器 helper 添加宽泛进程代理规则。
- 默认由目的地规则决定 `DIRECT` 或 `PROXY`。
- 只有证明某个安装路径确实需要窄路径覆盖时，才新增对应进程/路径规则。
- SDK 名称不是稳定的独立进程，不应默认变成进程规则。

这样可以避免共享 runtime 或 WebView 进程导致无关应用被过度代理。

## Simprint 需求

Simprint 可以走代理，但只能通过窄的 Chrome profile 浏览器子进程路径走进程级代理。

默认进程级 `PROXY` 覆盖只能是：

- `PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\Simprint\data\profiles\Chrome *\chrome_proxy.exe,PROXY`
- `PROCESS-PATH-WILDCARD,C:\Users\*\AppData\Local\Simprint\data\profiles\Chrome *\simprint.exe,PROXY`

profile 不得包含：

- `PROCESS-NAME,simprint.exe,PROXY`
- `PROCESS-NAME,simprint-runtime.exe,PROXY`
- `PROCESS-NAME,msedgewebview2.exe,PROXY`
- 宽泛系统 WebView2 路径代理规则
- Simprint fixed WebView2 路径代理规则；fixed WebView2 是 UI runtime，应交给域名规则决定 `DIRECT` 或 `PROXY`

本机观察到的 Simprint 路径包括：

- shell process: `C:\Users\Administration\Simprint\simprint.exe`
- runtime helper: `C:\Users\Administration\Simprint\simprint-runtime.exe`
- fixed WebView2 runtime:
  `C:\Users\Administration\Simprint\webview-fixed\Microsoft.WebView2.FixedVersionRuntime.144.0.3719.93.x64\msedgewebview2.exe`
- Chrome-profile wrapper:
  `C:\Users\Administration\AppData\Local\Simprint\data\profiles\Chrome 144\chrome_proxy.exe`
- Chrome-profile browser executable:
  `C:\Users\Administration\AppData\Local\Simprint\data\profiles\Chrome 144\simprint.exe`

Chrome-profile 下的 `simprint.exe` 是 browser wrapper，`OriginalFilename=chrome.exe`，不同于 `C:\Users\Administration\Simprint\simprint.exe` 这个 shell 进程。

## Hiddify 与 ProxyBridge 清理需求

迁移后，Windows 本机不能继续保留 Hiddify 或 ProxyBridge 作为活动代理客户端。

清理验证范围必须覆盖：

- HKLM/HKCU uninstall roots 下的卸载项
- Appx packages，尽可能覆盖 AllUsers
- services
- scheduled tasks
- startup Run keys
- running processes
- 旧监听端口 `12334` 和 `12335`
- Start Menu 与桌面快捷方式/文件
- 常见安装、配置、缓存路径：
  - `%APPDATA%\Hiddify`
  - `%LOCALAPPDATA%\Hiddify`
  - `%APPDATA%\ProxyBridge`
  - `%LOCALAPPDATA%\ProxyBridge`
  - `%APPDATA%\app.hiddify.com`
  - `%LOCALAPPDATA%\app.hiddify.com`
  - `%LOCALAPPDATA%\Programs\Hiddify`
  - `%LOCALAPPDATA%\Programs\ProxyBridge`
  - `C:\ProgramData\Hiddify`
  - `C:\ProgramData\ProxyBridge`
  - `C:\ProgramData\app.hiddify.com`
  - `C:\Program Files\Hiddify`
  - `C:\Program Files (x86)\Hiddify`
  - `C:\Program Files\ProxyBridge`
  - `C:\Program Files (x86)\ProxyBridge`

删除必须精确：

- 只删除解析后的绝对路径位于显式 allowlist 内，或文件/目录名明确包含 `Hiddify` / `ProxyBridge` 的目标。
- 不删除 generic proxy、browser、mihomo、Clash Verge Rev、Edge、Simprint 或用户 profile 根目录。
- Windows 删除必须全程使用 PowerShell `Remove-Item -LiteralPath`，避免通配符误删。

最近一次确认删除的目标：

- `C:\Users\Administration\AppData\Roaming\Hiddify`
- `C:\Users\Administration\Desktop\ProxyBridge-Rules.json`

最近一次管理员验证结果：

- `appx_hits=0`
- `service_hits=0`
- `task_hits=0`
- `uninstall_hits=0`
- `exact_path_hits=0`

macOS 迁移后也不能继续保留 Hiddify 或 ProxyBridge 作为活动代理客户端。验证范围包括：

- app bundle：
  - `/Applications/Hiddify.app`
  - `/Applications/ProxyBridge.app`
  - `~/Applications/Hiddify.app`
  - `~/Applications/ProxyBridge.app`
- 用户配置、偏好、缓存、saved state：
  - `~/Library/Application Support/app.hiddify.com`
  - `~/Library/Preferences/app.hiddify.com.plist`
  - `~/Library/HTTPStorages/app.hiddify.com`
  - `~/Library/Caches/app.hiddify.com`
  - `~/Library/Application Support/Hiddify`
  - `~/Library/Application Support/ProxyBridge`
  - `~/Library/Preferences/com.interceptsuite.ProxyBridge.plist`
  - `~/Library/Caches/com.interceptsuite.ProxyBridge`
- pkg receipts：
  - `pkgutil --pkgs | grep -Ei 'hiddify|proxybridge|interceptsuite'`
- system proxy 状态：
  - `networksetup -getwebproxy`
  - `networksetup -getsecurewebproxy`
  - `networksetup -getsocksfirewallproxy`
- ProxyBridge System Extension：
  - team ID: `L4HJT32Z59`
  - bundle ID: `com.interceptsuite.ProxyBridge.extension`

macOS System Extension 删除边界：

- 只允许尝试 `systemextensionsctl uninstall L4HJT32Z59 com.interceptsuite.ProxyBridge.extension` 和 `systemextensionsctl gc`。
- 不使用 `systemextensionsctl reset`，因为它会重置所有 System Extensions，超出 ProxyBridge 清理边界。
- 如果 `csrutil status` 显示 SIP enabled 且卸载返回 `At this time, this tool cannot be used if System Integrity Protection is enabled`，则普通 SSH、sudo 和 LaunchDaemon 权限都不能完成该扩展卸载。
- 此时可接受的下一步是到 macOS `System Settings > General > Login Items & Extensions > Network Extensions` 里禁用/移除 ProxyBridge，或进入 Recovery 临时关闭 SIP 后只执行：

```bash
systemextensionsctl uninstall L4HJT32Z59 com.interceptsuite.ProxyBridge.extension
systemextensionsctl gc
csrutil enable
```

完成后必须重启并重新验证 `systemextensionsctl list` 不再出现 `com.interceptsuite.ProxyBridge.extension`。
可把 `scripts/macos/recovery-uninstall-proxybridge-system-extension.sh` 复制到 Mac 上执行，脚本只包含
`systemextensionsctl uninstall L4HJT32Z59 com.interceptsuite.ProxyBridge.extension`、
`systemextensionsctl gc`、`systemextensionsctl list` 和 `csrutil enable` 提醒，不包含
`systemextensionsctl reset`。

## Windows 脚本入口

Windows 操作使用以下仓库脚本：

- 完整 elevated 安装和开机启动默认值：
  `scripts/windows/install-mihomo-tun.ps1`
- 把当前审核后的路由策略应用到 ProgramData、Clash runtime files 和 SYSTEM mihomo：
  `scripts/windows/apply-mihomo-routing-policy-admin.ps1`
- 只刷新 SYSTEM mihomo TUN runtime：
  `scripts/windows/refresh-mihomo-tun-config.ps1`
- 验证当前 Windows 本机路由：
  `scripts/windows/verify-mihomo-windows.ps1`
- 应用并检查 Simprint 专用路由：
  `scripts/windows/apply-simprint-routing-admin.ps1`
- 观察 Simprint 通过 mihomo 的实时连接：
  `scripts/windows/watch-simprint-routing.ps1`
- 观察 WPS 通过 mihomo 的实时连接：
  `scripts/windows/watch-wps-routing.ps1`
- 通过 Simprint Chrome profile CDP 探针证明只代理 Simprint 拉起的浏览器：
  `scripts/windows/debug-simprint-chrome-proxy.ps1`
- 全量 Windows 验收（pytest + PS 语法 + verify）：
  `scripts/windows/accept-mihomo-windows.ps1`
- 清理 Windows Hiddify / ProxyBridge 残留：
  `scripts/windows/uninstall-hiddify-proxybridge-admin.ps1`
- 清理/验证 macOS Hiddify / ProxyBridge 残留：
  `scripts/macos/uninstall-hiddify-proxybridge.sh`

涉及 TUN、scheduled task、service、ProgramData 或 system profile 的脚本必须管理员运行。

## 验证需求

静态检查必须证明：

- 生成配置中没有 `AI-PROXY`。
- 生成配置中没有 Qwen 专门规则。
- 存在 `PROXY` group。
- `PROXY` group 第一节点是 `GG-US-SEA-BGP-01`。
- `RULE-SET,cn,DIRECT` 在 `RULE-SET,proxy,PROXY` 前。
- 最终规则是 `MATCH,PROXY`。
- universal 配置中允许的进程级 `PROXY` 路径计数与 render 输出一致（当前 **29**），且 `disallowed=0`。
- Windows、macOS、Linux 生成配置不按宽泛 AI、浏览器、WebView 或 generic runtime 进程名强制代理。
- landing page 只发布 universal mihomo YAML，不发布单独的 Windows、macOS、Linux YAML 链接。

Windows 运行态验证必须证明：

- 文件 guardrails：
  - `file_ai_proxy_count=0`
  - `file_allowed_process_proxy_count=29`
  - `file_disallowed_process_proxy_count=0`
  - `file_match_rule=- MATCH,PROXY`
- SYSTEM mihomo runtime：
  - 监听 `127.0.0.1:7890` 和 `127.0.0.1:9090`
  - DNS 监听 `1053`
  - TUN adapter `Meta` 为 `Up`
  - `runtime_match_proxy=PROXY`
  - `runtime_ai_proxy_count=0`
  - `runtime_allowed_process_proxy_count=29`
  - `runtime_disallowed_process_proxy_count=0`
- Clash pipe / runtime：
  - `clash_pipe_match_proxy=PROXY`
  - `clash_pipe_ai_proxy_count=0`
  - `clash_pipe_allowed_process_proxy_count=29`
  - `clash_pipe_disallowed_process_proxy_count=0`
- policy probes（全部 `status=PASS`，脚本输出 `verification_verdict=PASS`）：
  - `chat.qwen.ai` 期望 `DIRECT` via `cn`
  - `www.google.com` 期望 `PROXY`
  - `www.baidu.com` 期望 `DIRECT`
  - `im.qq.com` 期望 `DIRECT`
  - `weixin.qq.com` 期望 `DIRECT`
  - `update.wps.cn` 期望 `DIRECT`
  - `drive.wps.cn` 期望 `DIRECT`
  - `account.wps.cn` 期望 `DIRECT`
- 当前 mihomo log summary 不能把旧日志当作当前证据。如果拿不到当前进程启动时间，verifier 必须输出 `current_log_unavailable_reason=start_time_unavailable`，并且不能扫描旧日志作为当前运行态证据。

## 测试门禁

这些需求的聚焦自动化门禁是：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_proxy_subscription_artifacts.py -q
```

PowerShell 语法门禁是：

```powershell
$files=@(
  'scripts\windows\verify-mihomo-windows.ps1',
  'scripts\windows\accept-mihomo-windows.ps1',
  'scripts\windows\refresh-mihomo-tun-config.ps1',
  'scripts\windows\apply-mihomo-routing-policy-admin.ps1',
  'scripts\windows\apply-simprint-routing-admin.ps1',
  'scripts\windows\watch-simprint-routing.ps1',
  'scripts\windows\watch-wps-routing.ps1',
  'scripts\windows\install-mihomo-tun.ps1'
)
foreach($file in $files){
  $errs=$null
  [System.Management.Automation.PSParser]::Tokenize((Get-Content -LiteralPath $file -Raw), [ref]$errs) | Out-Null
  if($errs){ "FAIL $file"; $errs | Format-List; exit 1 } else { "OK $file" }
}
```

Windows 运行态验证门禁是：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\accept-mihomo-windows.ps1
```

或仅运行 verify：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\verify-mihomo-windows.ps1
```

## 已确定的运行决策

- Hiddify 不再作为本地推荐客户端；此前观察到 Hiddify 路径在大型 ChatGPT asset fetch 上不稳定。
- ProxyBridge 已从当前 Windows 工作站迁移后清理。
- Clash Verge Rev 保留为 GUI / service shell，但 SYSTEM mihomo 拥有透明 TUN。
- `msedgewebview2.exe` 不得全局进程代理，因为它是共享 runtime，会覆盖无关应用。
- Qwen 不得有特殊 AI proxy 处理；它走普通大陆/非大陆规则集行为。
- 如果某个中国大陆应用意外走代理，应检查目的地并添加窄的 direct process/path 或 domain rule；不要添加宽泛 shared-runtime proxy rule。
