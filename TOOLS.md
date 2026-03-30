# TOOLS

工具使用规则：
- 方案生成前必须先调用 `pr_plan_requirements`，完成需求澄清与用户确认。
- 优先使用 PR 工具完成检索、生成与反馈闭环。
- 工具输出是 JSON 字符串，必须解析后再引用。
- 当现有工具不足时，新增 tools/*.py 而不是改核心 Agent。

当前工具清单：
{{tool_registry}}
