# Proxy Platform 状态与派生体系设计说明

## 一句话结论

`proxy-platform` 下一阶段不再只是“工作区仓库盘点壳”，而要补成“平台现场清单、观测回报、订阅派生和本地 provider 生命周期”的统一入口层，同时继续保持 `remote_proxy` 是公开运行底座、`Proxy_ops_private` 是私有现场真相源。

## 背景

当前仓库已经具备：

- repo-of-repos 工作区编排
- manifest 与 `.gitmodules` 一致性校验
- 宿主机 toolchain 诊断

当前仓库还不具备：

- 远端主机登记册
- 主机观测状态聚合
- 订阅派生视图
- 本地 MCP/provider 生命周期治理
- Web 工作台

与此同时，现网代理体系的真实现场信息主要落在两类仓库：

- `remote_proxy`
  公开部署基线、公开客户端文档、通用脚本
- `Proxy_ops_private`
  真实主机 inventory、secrets、生成订阅、发布与校验脚本

这导致一个长期问题：平台层该负责的“主机为什么出现、订阅为什么这么生成、页面为什么这么展示”，没有正式模型承接。

## 目标

建立一套平台壳内部可维护的统一状态模型，使以下问题都由同一套规则回答：

- 哪些主机属于平台现场清单
- 哪些主机当前启用
- 哪些主机当前观测健康
- 哪些主机应该进入订阅
- 页面如何展示主机与订阅
- 本地 provider/MCP 的重试、超时、启动预算如何表达

## 不做什么

- 不在本仓库保存真实 secrets
- 不在本仓库重写 `CliProxy-control-plane` 的 northbound `/v1` 或 worker southbound
- 不在本仓库把远端写动作直接塞进页面按钮
- 不把 `remote_proxy` 与 `Proxy_ops_private` 粗暴合并成单仓

## 根因分析

### 现象

- `remote_proxy` 和 `Proxy_ops_private` 都包含与订阅、客户端接入、节点说明有关的内容，看起来边界重叠。
- `proxy-platform` 只有 repo/toolchain 层能力，无法回答“为什么这台主机应该出现在页面和订阅里”。
- 本地 MCP/provider 启动慢、超时与重试策略没有统一表达。

### 直接原因

- 平台没有“主机登记册”“观测状态”“订阅派生”“本地 provider 生命周期”这些正式对象。
- 历史代理流程中的共享判断逻辑只能散落在公开仓库文档、私有仓库脚本和人工知识里。

### 根因

- “公开运行基线”“私有现场事实”“平台派生视图”三类真相没有被系统化区分。
- `proxy-platform` 第一阶段只建设了工作区壳，没有建设平台状态层。

### 为什么以前没暴露

- 过去主要依赖单个操作者理解哪份信息在什么仓库，人工可以弥补模型缺失。
- 一旦要引入 Web 管理台、agent 自动维护、动态订阅和主机健康展示，缺少统一状态模型会立刻暴露。

## 设计原则

### 1. 期望状态和观测状态分离

- 平台登记册表示期望状态：
  - 哪些主机属于平台
  - 是否启用
  - 是否允许纳入订阅
  - 变更策略是什么
- 观测回报表示观测状态：
  - 当前健康
  - 最近一次探针来源
  - 最近一次部署/探针时间
  - 错误摘要

当前阶段补充约束：

- 只要某个视图直接依赖 `Proxy_ops_private` 里的私有登记册，它当前就只能在 `operator` 模式开放。
- `public` 模式先保留公开仓库和公开观测插槽，不直接读取私有现场清单。
- 未来如果要开放公开页面或公开订阅入口，必须先增加脱敏后的 public snapshot，而不是偷穿 private 边界。

### 2. 订阅是派生结果，不是原始真相

- 多节点订阅、单节点订阅、Hiddify deeplink、Web 复制链接都视为派生结果。
- 原始真相是：
  - 主机登记册
  - 订阅策略
  - 观测状态

### 3. 共享判断逻辑回收到平台壳

下列逻辑应进入 `proxy-platform`：

- 如何把现场清单和观测状态合成平台视图
- 如何从节点登记册派生多节点/单节点订阅链接
- 如何表达本地 provider 的启动预算、请求超时、重试次数
- 如何为 Web/CLI 提供统一视图

### 4. 远端执行必须走作业协议

- 页面和 CLI 的增删主机、部署、摘除不直接执行远端写操作。
- 平台只产生明确的 job schema、dry-run 输出和审计记录。
- 真正的 apply 可以在后续阶段接入执行器。

## 仓库职责重划分

### `remote_proxy`

保留：

- 公开部署基线
- 单机服务生命周期脚本
- 公开文档
- 可复现的运行时兼容层

不再承担：

- 私有主机现场清单
- 发布态订阅真相
- 平台展示与派生规则

### `Proxy_ops_private`

保留：

- 真实主机 inventory
- secrets
- operator 侧发布配置
- 必要私有生成物

不再新增：

- 共享平台判断逻辑
- 平台 Web/CLI 展示层逻辑

### `proxy-platform`

新增承担：

- 现场清单读取与归一化
- 观测状态模型
- 订阅派生视图
- 本地 provider 生命周期配置
- Web/CLI 统一视图
- 平台级作业 schema 与审计视图

## 第一阶段实现范围

### 数据模型

- 扩展 `platform.manifest.yaml`
  - 增加 host registry source
  - 增加 observation source
  - 增加 local provider budgets
- 新增平台内部模型：
  - `HostRecord`
  - `ObservedHostState`
  - `HostView`
  - `SubscriptionProjection`
  - `LocalProviderPolicy`

### 命令面

- `hosts list`
  输出平台视角主机清单
- `subscriptions list`
  输出平台派生订阅入口
- `providers list`
  输出本地 provider/MCP 生命周期配置

### Web 入口

新增最小 Web 工作台：

- 主页显示主机视图、健康状态、订阅链接
- 页面提供复制订阅按钮
- 页面支持本地 inventory 文件的新增/删除主机

说明：

- 这一阶段的“新增/删除主机”只修改 inventory 文件，不执行远端部署。
- 这样做是为了先把平台状态模型和操作入口走通，不越过远端 apply 的审计边界。

### 验证

- manifest 解析测试
- 现场清单与观测状态合成测试
- 订阅派生测试
- CLI 输出测试
- Web API / HTML smoke 测试

## 后续阶段

### 第二阶段

- 引入远端 job schema
- 部署/摘除 dry-run
- 观测状态写回与审计

### 第三阶段

- 接入真正的远端 probe/agent 回报
- 支持平台驱动的 apply
- 页面提供受控远端操作

## 外部规范对齐

本设计遵循三类外部约束：

- OpenAI：
  - 规则、反馈、守护和持续改进应写入仓库，而不是停留在对话里
  - 安全、评估和轨迹检查应是结构化能力
- Anthropic：
  - 子代理只做边界清晰的 side work
  - hooks 用于事件驱动约束
  - 项目级规则应进入版本控制
- Meta-Harness：
  - 优化对象是整个 harness 链路，而不是只改模型或提示词

## 评审重点

- 是否把复杂性收进模型、adapter 和 job schema，而不是散在脚本和 README
- 是否真正把三仓职责重新拉直
- 是否避免把 `proxy-platform` 做成新的控制面内核
