# Runbook: vmrack / qqpw dual egress sync

## Goal

Keep these four surfaces consistent:

1. private inventory/secrets (`repos/proxy_ops_private`)
2. remote vmrack1 (`wg0` + dual-egress sing-box)
3. SEA published subscriptions
4. local mihomo profile

## Preconditions

- `repos/proxy_ops_private/secrets/nodes/vmrack1.env` has real:
  - `WIREGUARD_PRIVATE_KEY`
  - `WIREGUARD_PEER_PUBLIC_KEY`
  - `ENABLE_DUAL_EGRESS=true`
  - `QQPW_VLESS_UUID`
- Local mihomo available for live exit-IP probes (`MIHOMO_BIN` or `C:\Tools\mihomo\mihomo-windows-amd64.exe`)
- SSH reachability to `vmrack1` (`38.65.93.39`)

## One-command sync

```bash
cd repos/proxy_ops_private
bash scripts/sync_vmrack_qqpw.sh --dry-run
# after reviewing:
bash scripts/sync_vmrack_qqpw.sh
# or without live publish:
bash scripts/sync_vmrack_qqpw.sh --skip-publish
# CI / no live proxy:
bash scripts/sync_vmrack_qqpw.sh --skip-apply --static-probe --skip-publish
```

## Acceptance

- `GG-Vmrack1` exit IP == `38.65.93.39`
- `QQPW-Residential-*` exit IP != `38.65.93.39` (currently observed residential NAT, e.g. `147.81.120.142`)
- `v2ray_node_vmrack1.txt` has only `:10003`
- `v2ray_node_qqpw.txt` has `:10006` VLESS (required) and optional `:10005` Hy2; no client SOCKS5
- mihomo groups are only `PROXY` + `ChatGPT` (no `Vmrack-Public` / `QQPW-Residential`)
- OpenAI-family domains use `ChatGPT` group; default leaf is `QQPW-Residential-Reality` (VLESS)
- SEA `mihomo-universal.yaml` matches generated ports/names/groups

## Publish gate

`publish_subscriptions_to_sea_host.sh` runs `probe_dual_egress_ips.py` when
`availability_policy.require_dual_egress_assertions: true`.

For static-only gate:

```bash
SEA_SUBSCRIPTION_DUAL_EGRESS_MODE=static bash scripts/publish_subscriptions_to_sea_host.sh
```

## Related

- [ADR-0018](../adr/ADR-0018-vmrack-qqpw-dual-egress-sync.md)
- `repos/proxy_ops_private/docs/client-subscription-quickstart.md`
