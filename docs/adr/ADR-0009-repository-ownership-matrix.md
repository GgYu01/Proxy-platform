# ADR-0009: 用所有权矩阵消除 remote_proxy 与 Proxy_ops_private 的职责重叠

## Status

Accepted

## Context

`remote_proxy` 和 `Proxy_ops_private` 目前都触及部署、主机信息和订阅相关内容，容易形成“各自带一点平台逻辑”的重叠。

真正冲突的不是仓库名字，而是三类真相曾经没有被正式区分：

- 通用运行基线
- 私有现场事实
- 平台派生视图

## Decision

按“真相类别”而不是“文件现在放在哪”来重新划分所有权：

- `remote_proxy`
  只保留公开、可复用的运行基线和生命周期脚本。
- `Proxy_ops_private`
  只保留私有 inventory、secrets、发布目标和私有生成物。
- `proxy-platform`
  负责跨仓库的状态模型、健康聚合、订阅派生、作业 schema、统一 CLI / 未来 Web 入口。

明确以下边界：

- 真实主机名单不再以长期运营事实的方式硬编码在 `remote_proxy`
- 订阅文本和页面列表不再作为原始真相维护
- 共享判断逻辑不再长期留在 `Proxy_ops_private`

## Consequences

### Positive

- agent 和人工 reviewer 都能明确判断“这段改动应当落在哪个仓库”。
- 平台层规则可以集中测试，不再散在私有脚本和运行底座之间。
- 后续大重构时可以按 ownership matrix 拆迁，而不是凭感觉搬文件。

### Negative

- 需要一次系统盘点，把现有重叠内容分类为“保留 / 抽回平台壳 / 删除 / 派生化”。
- 短期内文档和脚本会有迁移成本，但这是把长期维护成本显式化，而不是继续隐含累积。
