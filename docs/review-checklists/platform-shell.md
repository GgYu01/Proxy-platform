# Platform Shell Review Checklist

- 是否仍然保持“薄平台壳”定位
- 是否避免复制 control-plane 业务内核
- 是否保护 private/public 边界
- 是否把依赖 private registry 的命令和页面明确限制在 `operator` 模式
- 是否把“主机登记册 / 观测回报 / 订阅派生”三层状态分清楚
- 如果涉及 mutation，是否已经转入 `job plan / audit / apply` 合同，而不是页面直连写操作
- 是否把订阅文本和页面展示当成派生结果，而不是原始真相
- 是否先做 ownership review，再决定改动落在哪个仓库
- 是否为新命令补了帮助文案和测试
- 是否把平台级架构变更同步到 ADR
