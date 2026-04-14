# ADR-0010: 平台 mutation 必须先进入 job plan / audit / apply 合同

## Status

Accepted

## Context

`proxy-platform` 已经有主机登记册、观测回报和订阅派生三层状态模型，也已经有本地 Web 工作台入口。

如果下一步把“新增主机、移除主机、部署主机、摘除主机”直接做成页面按钮直连 SSH 或脚本，会马上出现三类问题：

- 平台壳会滑成第二控制面，重写下游 authority repo 已有的生命周期逻辑。
- reviewer 很难判断某次变更是在“改平台状态合同”，还是“偷偷接了远端写操作”。
- 一旦出现失败，既没有 dry-run，也没有稳定 audit，更谈不上回退和责任边界。

换句话说，当前最先缺的不是更多按钮，而是把“允许什么变更、怎么审、谁来真正执行”固定成平台级合同。

## Decision

平台 mutation 统一采用 `job plan -> audit -> apply` 流程。

### 1. 平台层负责什么

`proxy-platform` 负责：

- 统一 job kind
- 统一 payload shape
- 统一 preview steps
- 统一 audit record
- 统一 reviewed plan 的受管存放路径与完整性校验
- 统一 CLI / Web 入口

这等于说，平台层负责的是“变更申请单”和“审计单”的格式，而不是远端执行细节。

### 2. 平台层不负责什么

`proxy-platform` 不直接负责：

- SSH 编排
- 远端 systemd / podman / compose 细节
- `remote_proxy` 的生命周期脚本实现
- `Proxy_ops_private` 的 secrets / inventory 真相重写

这等于说，平台层不能直接替代 authority repo。

### 3. 当前阶段允许的 apply

当前只允许两类 `inventory_only` apply：

- `add_host`
- `remove_host`

它们的 apply 效果只到“受控修改登记册文件并写 audit”。

### 4. 当前阶段不允许的 apply

当前两类远端动作只允许 dry-run：

- `deploy_host`
- `decommission_host`

plan 可以生成，audit 可以记录，但 apply 默认禁止，直到有明确的 authority adapter。

### 5. 回退策略

当前阶段不做“自动远端回退”承诺。

- 对登记册变更，回退通过逆向 job 完成。
- 对远端 deploy/decommission，等 authority adapter 接入后，再定义正式 rollback / compensation contract。

## Consequences

### Positive

- reviewer 可以先审“这是不是合法 job contract”，不用先读远端脚本。
- Web 按钮不会直接滑成 SSH 面板。
- `remote_proxy` 和 `Proxy_ops_private` 的 authority 边界继续成立。
- 后续接远端 apply 时，新增的是 adapter，不是重写整套平台语义。

### Negative

- 当前 Web/CLI 看起来已经有 deploy/decommission 入口，但仍然只能 dry-run。
- operator 还需要继续使用下游 authority repo 做真正远端 apply。
- rollback 目前只对登记册变更明确成立，远端动作仍需后续设计。
