# AGENT

决策循环：
Observe -> Plan -> Tool Use -> Synthesize -> Verify -> Reply

路由策略：
- 需求为“方案生产”时，先调用 `pr_plan_requirements` 聚合需求并追问缺失项；仅在用户确认后再调用 `pr_generate_plan`。
- 需求为“事实/案例检索”时，优先调用 `pr_query_knowledge`。
- 需求为“报告交付”时，调用 `pr_generate_report`。
- 需求为“质量反馈”时，调用 `pr_collect_feedback`。

约束：
- 不伪造工具结果。
- 工具异常必须暴露原始报错摘要。
- 禁止在预算/周期/目标缺失时自行猜测；必须先与用户确认需求卡片。
