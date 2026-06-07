# ADR-0020: LisaHost SEA BGP temporary subscription host

## Status

Accepted — 2026-06-07

## Context

The original infra-core deployment model placed shared control-plane services on a single Ubuntu.online host (`112.28.134.53`):

- `/mnt/hdo/infra-core/services/proxy-subscriptions` (nginx + Traefik `:27111`)
- `/mnt/hdo/infra-core/services/proxied/vless-sidecar` (centralized failover sidecar)
- `/mnt/hdo/infra-core/modules/proxy-platform-operator` (operator Web)

That physical host has been retired and deleted. Client inventory, publish scripts, and generated subscription URLs still referenced the retired Traefik hostname and `/mnt/hdo/infra-core` paths, causing operators to publish to ghost directories while the live service continued on LisaHost SEA BGP.

## Decision

1. **Authoritative subscription base URL** is now:
   - `http://69.5.53.82:18080/subscriptions`
2. **Publish target** is node `us_sea_bgp_01` (`69.5.53.82`, SSH `:42778`), syncing to:
   - `/srv/proxy-subscriptions/public/subscriptions`
   - served by systemd unit `gg-proxy-subscriptions-http.service`
3. **infra-core vless-sidecar** and related apply/check/deploy scripts are removed from `proxy_ops_private`. Failover is handled per-node via sing-box / cliproxy-plus on the six-VPS pool and `failover_priority` in inventory.
4. **`remote_proxy_cliproxy_plus_infra_core_sidecar`** authority adapter is removed from `platform.manifest.yaml`.
5. **`https://proxy-subscriptions.svc.prod.lab.gglohh.top:27111`** is deprecated until a new HTTPS front (planned: `sea.prod.gglohh.top` + k0s Traefik) passes LisaHost external gates.
6. **Operator Web** is not redeployed in this ADR; it retired with infra-core and may return on SEA k0s later.

## Consequences

### Positive

- Inventory, render output, publish script, and live server paths align.
- Clients can update subscriptions from a working HTTP endpoint without relying on dead DNS/Traefik.
- Sidecar confusion is eliminated; standalone VPS topology is the only supported deployment path.

### Negative / trade-offs

- Subscription traffic is plain HTTP on `:18080` until HTTPS migration completes. Mitigated by mihomo DIRECT rules for `69.5.53.82`.
- SEA BGP host temporarily combines roles: first-priority proxy node, subscription static host, and legacy Podman stack. This is intentional short-term consolidation.
- Historical docs referencing infra-core paths remain in ADR-0011/0012 as historical context; operator runbooks must be read together with this ADR.

## Migration notes for clients

- Clash Verge Rev / mihomo: re-import or update subscription URL to `http://69.5.53.82:18080/subscriptions/mihomo-universal.yaml`.
- Do not use `:27111` URLs until explicitly announced after HTTPS cutover.

## Publish command

```bash
bash repos/proxy_ops_private/scripts/publish_subscriptions_to_sea_host.sh
# or deprecated wrapper:
bash repos/proxy_ops_private/scripts/publish_subscriptions_to_infra_core.sh
```

Defaults are read from `inventory/subscriptions.yaml` `publish` metadata and `us_sea_bgp_01` SSH fields.
