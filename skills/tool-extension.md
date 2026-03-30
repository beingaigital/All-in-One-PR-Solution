# Tool Extension Skill

目标：在不改主流程的前提下扩展能力（tools/skills）。

执行规则：
1. 新能力优先通过 tools/*.py 或 skills/*.md 增加，不修改核心 agent 流程。
2. 新工具必须是“单一职责 + JSON 可解析输出”。
3. 新技能必须可被关键词触发，并在 skills.yaml 中可启停。
4. 对新增能力给出最小验证步骤（如何调用、期望返回字段）。

适用场景：
- 将传统 workflow agent 快速迁移到 PRClaw。
- 逐步接入 PPT 生成、文案生成、配图海报等后续能力。
