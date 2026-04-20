# Public State 与 Private Truth Sync 使用说明

## 一句话结论

当前平台已经把“给 public 看什么”和“怎么把运行时副本带回 private truth 工作树”分成了两条明确链路：public 只读入口只消费脱敏快照，private truth 回写必须先 plan 再 apply。

## 它在当前项目里代表什么

在这个项目里，这份 runbook 讲的是一座桥，不是新的控制面。

更准确地说：

- `state/public/*.json`
  是 public 只读世界看到的派生结果。
- `.runtime-workspace`
  是远端 operator 站点正在维护的运行态副本。
- `repos/proxy_ops_private/inventory/*`
  仍然是本地 private truth 工作树。

这份 runbook 解决的是：

- public 模式为什么不再直接读 private registry
- operator 页面改过的登记册副本，应该怎么受控地带回 private truth 工作树

它不解决：

- 自动 Git commit
- 自动 Git push
- 自动匿名发布 public 站点

## public 只读快照是什么

public 快照等于“给公开查看面准备的脱敏现场板”。

当前文件位置：

- `state/public/host_console.json`
- `state/public/subscriptions.json`

这些文件来自 operator 真相和观测状态的导出，不是手写维护。

当前会保留的字段：

- 主机名
- provider
- 部署拓扑
- 运行服务
- 观测状态
- 订阅发布判断
- 订阅 URL

当前不会保留的字段：

- 主机地址
- SSH 端口
- base port
- change policy

## 导出 public 快照

在仓库根目录执行：

```bash
.venv/bin/python -m proxy_platform exports export-public \
  --manifest ./platform.manifest.yaml \
  --workspace-root /mnt/hdo/infra-core/modules/proxy-platform-operator/.runtime-workspace \
  --output-root /mnt/hdo/infra-core/modules/proxy-platform-operator/.runtime-workspace/state/public
```

导出完成后，可以直接用 `public` 模式验看：

```bash
.venv/bin/python -m proxy_platform hosts list \
  --manifest ./platform.manifest.yaml \
  --workspace-root /mnt/hdo/infra-core/modules/proxy-platform-operator/.runtime-workspace \
  --mode public

.venv/bin/python -m proxy_platform subscriptions list \
  --manifest ./platform.manifest.yaml \
  --workspace-root /mnt/hdo/infra-core/modules/proxy-platform-operator/.runtime-workspace \
  --mode public
```

如果快照结构损坏，CLI 和 Web 都应该返回受控错误，而不是静默兜底。

## private truth reviewed sync 是什么

它等于“把远端 operator 运行态副本正式带回本地 private truth 工作树的计划式同步”。

当前只覆盖两份文件：

- `repos/proxy_ops_private/inventory/nodes.yaml`
- `repos/proxy_ops_private/inventory/subscriptions.yaml`

它解决什么：

- 避免手工 copy
- 避免肉眼 diff 漏改
- 避免误把 secrets、生成物一起带回去

它不是什么：

- 不是自动 Git push
- 不是 secrets 同步器
- 不是平台接管 private repo 的提交器

## 生成 reviewed sync plan

```bash
.venv/bin/python -m proxy_platform exports plan-sync-private \
  --runtime-workspace-root /mnt/hdo/infra-core/modules/proxy-platform-operator/.runtime-workspace \
  --repo-root /workspaces/proxy-platform
```

这一步会输出：

- plan id
- 发生变化的 inventory 文件
- plan 文件路径

## apply reviewed sync plan

```bash
.venv/bin/python -m proxy_platform exports apply-sync-private \
  --plan-file /workspaces/proxy-platform/state/private_truth_sync/plans/<sync-plan>.json \
  --confirm
```

apply 前会校验三件事：

- runtime source digest 没变
- target digest 没变
- 操作者显式给了 `--confirm`

只要任意一侧文件在 plan 和 apply 之间变化，旧 plan 就应该作废并重新生成。

## 推荐操作顺序

1. 先确认 operator 页面上的改动已经稳定，不再继续编辑 `.runtime-workspace`。
2. 导出 public 快照，确认 public 只读视图没有泄露 private 字段。
3. 生成 private truth sync plan，审阅变更范围是否只落在 inventory 文件。
4. 显式 apply sync plan。
5. 之后如果需要 Git 提交和推送，再由人类按 private repo 规范继续处理。

## Review 要点

- public 模式是否继续只读脱敏快照
- public 快照是否泄露 private 维护字段
- private truth sync 是否仍然要求 plan/apply/digest/confirm
- reviewed sync 是否仍然只覆盖 inventory，不顺手带出 secrets 或 Git push

## 相关文档

- [README.md](/workspaces/proxy-platform/README.md)
- [ADR-0013-public-snapshot-and-private-truth-sync.md](/workspaces/proxy-platform/docs/adr/ADR-0013-public-snapshot-and-private-truth-sync.md)
- [operator-web-console.md](/workspaces/proxy-platform/docs/runbooks/operator-web-console.md)
