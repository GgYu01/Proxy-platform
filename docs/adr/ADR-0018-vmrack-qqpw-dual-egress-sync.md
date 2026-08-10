# ADR-0018: vmrack/qqpw dual egress stay distinct and sync as one loop

## Status

Accepted

## Context

`qqpw` 一度被实现为 `vmrack1` 同端口订阅别名：客户端看到两个名字，但实际仍是 `38.65.93.39:10003/10005`。与此同时，住宅出口依赖主机上的 `wg0`（`10.77.0.1` → 动态 NAT），但仓库没有把 “本机公网出口” 与 “WireGuard 住宅出口” 建模为可验收的两条路径。

结果是：

- 本地 mihomo、SEA 发布物、远端 sing-box、private inventory 容易漂移
- 无法证明 `GG-Vmrack1` 出口是 `38.65.93.39`，也无法证明 `QQPW-*` 走另一 IP

## Decision

1. 在 `repos/proxy_ops_private/inventory/nodes.yaml` 的 `vmrack1` 上显式建模 `egress_profiles.public` 与 `egress_profiles.wireguard_nat`，以及 `wireguard` 元数据。
2. 远端 sing-box（`ENABLE_DUAL_EGRESS=true`）使用双 outbound：
   - `direct-public`：`:10003` VLESS（及调试入站 `:10000` SOCKS 等）
   - `direct-wg`（`inet4_bind_address=10.77.0.1`）：`:10005` Hysteria2 + `:10006` QQPW VLESS + `:10007` QQPW SOCKS5
3. 订阅渲染禁止同端口别名：
   - `GG-Vmrack1` 只发布 public VLESS
   - `QQPW-*` 只发布 WG profile 端口（SOCKS5 / Reality / Hy2）
   - 删除 `GG-Vmrack1-Hysteria2` 作为机房节点
4. 本地 mihomo 只保留两组：
   - `ChatGPT`：OpenAI/ChatGPT/Codex 域名默认走 QQPW SOCKS5（可选其他节点 / DIRECT）
   - `PROXY`：其余流量默认 Auto（非 QQPW 节点优先），仍可选 QQPW / DIRECT
5. 全链路以 `scripts/sync_vmrack_qqpw.sh` 为编排入口：validate → apply WG/sing-box → probe → render → publish →（可选）本地刷新。
6. `proxy-platform` 只记录 ADR/runbook 与可选薄委托，不把 WG/secrets/发布内核搬进平台壳。

## Consequences

### Positive

- vmrack / qqpw 出口 IP 可分别断言
- inventory、远端、generated、SEA、本地订阅可走同一 sync 脚本收敛
- 其他节点默认不受 `ENABLE_DUAL_EGRESS` 影响

### Negative

- 需要维护 Hy2 TLS 证书与真实 WireGuard 密钥（secrets，不可用 placeholder 上线）
- cliproxy-plus 与 sing-box 可并存；双出口路径明确以 sing-box deploy 为准
