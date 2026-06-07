# ADR-0021: Subscription node availability pruning (72h TCP)

## Status

Accepted — 2026-06-07

## Context

Subscription artifacts (`v2ray_nodes.txt`, `mihomo-universal.yaml`, landing page, sing-box profile) were derived solely from registry flags (`enabled`, `include_in_subscription`). TCP observation (`state/observations/hosts.json`) affected operator display only; long-dead nodes remained in public subscriptions until manually disabled in inventory.

Operators need automatic removal of nodes that have been continuously unreachable for several days, without mutating the registry (which remains the full inventory of record).

## Decision

1. **Probe method**: TCP connect to `base_port + probe_port_offset` (default offset `1`), matching existing `observation_probe` semantics.
2. **Ledger**: Persist continuous unavailability in `repos/proxy_ops_private/state/node_availability.json` (git-tracked). Fields include `unavailable_since`, cleared on successful probe.
3. **Threshold**: Exclude from subscription artifacts when `unavailable_since` is ≥ `exclude_after_hours` (default **72**).
4. **Pending window**: Nodes down for less than 72h remain published; landing page marks them「探测异常，暂仍发布」.
5. **Never probed**: No ledger entry → keep in subscription (do not treat `unknown` as down).
6. **Exempt flag**: `subscription_availability_exempt: true` on a node prevents auto-exclusion.
7. **Fail-fast**: If eligible node count `< min_published_nodes` (default 1), `render_artifacts.py` and publish abort.
8. **Registry unchanged**: Do not flip `enabled` in `nodes.yaml`; only generated/public artifacts change.
9. **Platform alignment**: `proxy_platform.subscription_availability` reads the same ledger JSON; projections and operator Web show excluded nodes and reasons.

Policy lives in `inventory/subscriptions.yaml` → `availability_policy`.

## Consequences

### Positive

- Dead links auto-drop from client-facing subscriptions after a grace period.
- Recovery is automatic on next successful probe + render.
- Single ledger is updated by render, reconcile cron, and platform observation refresh.

### Negative / trade-offs

- Temporary firewall or port changes can start the 72h clock; use `subscription_availability_exempt` for maintenance.
- Clients cache old subscriptions until manual refresh — documented in runbook.
- Multi-writer ledger races are avoided by updating only from designated scripts.

## References

- `repos/proxy_ops_private/scripts/subscription_node_availability.py`
- `repos/proxy_ops_private/scripts/reconcile_subscription_node_availability.py`
- `src/proxy_platform/subscription_availability.py`
- `docs/runbooks/proxy-subscription-client-deployment-requirements.md`
