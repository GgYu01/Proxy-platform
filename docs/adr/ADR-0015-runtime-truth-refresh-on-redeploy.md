# ADR-0015: redeploy 时对远端现场清单采用“旧 seed 镜像自动刷新，已漂移现场保留”策略

## 状态

已采纳，2026-04-15

## 背景

`ADR-0012` 把远端 operator 运行面拆成了三层：

- `/app`
- `.runtime-seed`
- `.runtime-workspace`

其中 `nodes.yaml`、`subscriptions.yaml` 被定义成“运行态现场清单副本”，因此早期策略是 redeploy 不去覆盖它们。

这个边界本身是对的，但上线后暴露出一个正式缺口：

- 本地 private truth 已经改成四节点；
- 远端 `.runtime-workspace` 还停在旧三节点；
- 页面继续读旧运行态副本，于是站点看起来像“没部署更新”；
- 如果简单把 redeploy 改成强制覆盖，又会把页面上的本地新增/删除主机静默抹掉。

换句话说，问题不是“要不要保护运行态副本”，而是“什么时候它仍然只是上一版 seed 的镜像，什么时候它已经变成了新的现场真相”。

## 决策

对 `nodes.yaml`、`subscriptions.yaml` 的 redeploy 策略改成两段式：

1. 如果远端 `.runtime-workspace` 里的副本仍然等于“上一版 `.runtime-seed` 镜像”，允许自动刷新到这次的新 seed。
2. 如果远端运行态副本已经偏离上一版 seed，必须保留它，并把这次 redeploy 视为“现场已漂移，不可静默覆盖”。

实现落点：

- `deploy/infra-core-module/register_module.sh`
  在重发模块时先备份上一版 `.runtime-seed`，再构建新镜像，并用一次性容器执行 `runtime_truth_sync`。
- `src/proxy_platform/runtime_truth_sync.py`
  提供“上一版 seed 对比当前 workspace，再决定 refresh / preserve”的正式逻辑。

## 为什么这样做

它解决的是两个互相冲突的问题：

- 不能让远端 operator 页面长期停在旧主机清单；
- 也不能让 redeploy 把站点上已经发生的本地编辑静默抹掉。

在这个项目里，更准确的项目语言是：

- `.runtime-seed` 是“这次发过去的期望清单快照”；
- `.runtime-workspace` 是“站点当前真正使用的现场清单”；
- 只有当现场清单还没脱离上一版快照时，redeploy 才能安全把它推进到新快照。

## 结果

正向结果：

- 本地 private truth 的结构性更新，可以正式带到远端 operator 页面；
- 现场已经继续编辑的站点，不会因为 redeploy 被静默回滚；
- 脚本能明确区分“没刷新是因为现场已漂移”和“没刷新是链路没打通”。

代价与边界：

- 这不是双向自动同步；`.runtime-workspace` -> `repos/proxy_ops_private` 仍然要走 reviewed sync。
- 如果上一轮部署失败在“新 seed 已写入、workspace 还没更新”的半路状态，后续 redeploy 需要根据 `.deploy-backups/runtime-seed-*` 找到真正对应旧现场的 seed 基线，再做一次受控修平。
- 这条策略只适用于运行态现场清单，不改变 authority review surface 的“每次启动都刷新”规则。
