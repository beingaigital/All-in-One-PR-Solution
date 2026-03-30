#!/usr/bin/env python3
"""
品牌传播方法论规则库。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.common.pr_neo4j_env import graph


class MethodologyRule:
    """方法论规则类。"""

    def __init__(self, rule_data: Dict[str, Any]):
        self.rule_id = rule_data.get("rule_id", "")
        self.rule_type = rule_data.get("rule_type", "")
        self.name = rule_data.get("name", "")
        self.description = rule_data.get("description", "")
        self.conditions = rule_data.get("conditions", {})
        self.application_scenarios = rule_data.get("application_scenarios", [])
        self.priority = rule_data.get("priority", 0)
        self.effects = rule_data.get("effects", {})
        self.content = rule_data.get("content", "")
        self.version = rule_data.get("version", "1.0")
        self.created_at = rule_data.get("created_at", datetime.now().isoformat())
        self.updated_at = rule_data.get("updated_at", datetime.now().isoformat())

    def matches(self, context: Dict[str, Any]) -> bool:
        """检查规则是否匹配上下文。"""
        if "industry" in self.conditions:
            context_industry = context.get("industry", "")
            if self.conditions["industry"] and context_industry != self.conditions["industry"]:
                return False

        if "brand" in self.conditions:
            context_brand = context.get("brand", "")
            if self.conditions["brand"] and context_brand != self.conditions["brand"]:
                return False

        if "pr_goal" in self.conditions:
            context_goal = context.get("pr_goal", "")
            rule_goals = self.conditions.get("pr_goal", [])
            if rule_goals and context_goal not in rule_goals:
                return False

        if self.application_scenarios:
            context_scenario = context.get("scenario", "")
            if context_scenario not in self.application_scenarios:
                return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_type": self.rule_type,
            "name": self.name,
            "description": self.description,
            "conditions": self.conditions,
            "application_scenarios": self.application_scenarios,
            "priority": self.priority,
            "effects": self.effects,
            "content": self.content,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class MethodologyRulesManager:
    """方法论规则管理器。"""

    def __init__(self) -> None:
        self.graph = graph
        self.rules_cache: Dict[str, MethodologyRule] = {}

    def import_rules_from_json(self, json_path: str) -> Dict[str, Any]:
        """从 JSON 导入规则。"""
        try:
            with open(json_path, "r", encoding="utf-8") as fh:
                rules_data = json.load(fh)
            if isinstance(rules_data, list):
                rules = rules_data
            elif isinstance(rules_data, dict) and "rules" in rules_data:
                rules = rules_data["rules"]
            else:
                rules = [rules_data]

            results = {"total": len(rules), "imported": 0, "updated": 0, "errors": []}
            for rule_data in rules:
                try:
                    outcome = self.add_or_update_rule(rule_data)
                    if outcome.get("created"):
                        results["imported"] += 1
                    else:
                        results["updated"] += 1
                except Exception as exc:
                    results["errors"].append({"rule": rule_data.get("name", "Unknown"), "error": str(exc)})
            return results
        except Exception as exc:
            return {"error": f"导入失败: {exc}"}

    def add_or_update_rule(self, rule_data: Dict[str, Any]) -> Dict[str, Any]:
        """添加或更新规则。"""
        if not self.graph:
            return {"error": "Neo4j连接不可用"}

        rule_id = rule_data.get("rule_id") or rule_data.get("name", "")
        if not rule_id:
            return {"error": "规则ID或名称不能为空"}

        try:
            existing = self.graph.query(
                """
                MATCH (r:MethodologyRule {rule_id: $rule_id})
                RETURN r
                """,
                params={"rule_id": rule_id},
            )

            properties = {
                "rule_id": rule_id,
                "rule_type": rule_data.get("rule_type", "general"),
                "name": rule_data.get("name", ""),
                "description": rule_data.get("description", ""),
                "conditions": json.dumps(rule_data.get("conditions", {}), ensure_ascii=False),
                "application_scenarios": json.dumps(rule_data.get("application_scenarios", []), ensure_ascii=False),
                "priority": rule_data.get("priority", 0),
                "effects": json.dumps(rule_data.get("effects", {}), ensure_ascii=False),
                "content": rule_data.get("content", ""),
                "version": rule_data.get("version", "1.0"),
                "updated_at": datetime.now().isoformat(),
            }
            properties = {k: v for k, v in properties.items() if v not in (None, "")}

            if existing:
                self.graph.query(
                    """
                    MATCH (r:MethodologyRule {rule_id: $rule_id})
                    SET r += $properties
                    RETURN r
                    """,
                    params={"rule_id": rule_id, "properties": properties},
                )
                return {"created": False, "rule_id": rule_id, "action": "updated"}

            properties["created_at"] = datetime.now().isoformat()
            self.graph.query(
                """
                CREATE (r:MethodologyRule $properties)
                RETURN r
                """,
                params={"properties": properties},
            )
            self._link_rule_to_entities(rule_id, rule_data.get("conditions", {}))
            return {"created": True, "rule_id": rule_id, "action": "created"}
        except Exception as exc:
            return {"error": f"操作失败: {exc}"}

    def _link_rule_to_entities(self, rule_id: str, conditions: Dict[str, Any]) -> None:
        if not self.graph:
            return
        try:
            if "brand" in conditions:
                self.graph.query(
                    """
                    MATCH (r:MethodologyRule {rule_id: $rule_id})
                    MATCH (b:Brand {name: $brand_name})
                    MERGE (r)-[rel:APPLIES_TO]->(b)
                    SET rel.priority = $priority
                    """,
                    params={
                        "rule_id": rule_id,
                        "brand_name": conditions["brand"],
                        "priority": conditions.get("priority", 0),
                    },
                )
            if "industry" in conditions:
                self.graph.query(
                    """
                    MATCH (r:MethodologyRule {rule_id: $rule_id})
                    MERGE (i:Industry {name: $industry})
                    MERGE (r)-[rel:APPLIES_TO]->(i)
                    SET rel.priority = $priority
                    """,
                    params={
                        "rule_id": rule_id,
                        "industry": conditions["industry"],
                        "priority": conditions.get("priority", 0),
                    },
                )
        except Exception as exc:
            print(f"链接规则到实体失败: {exc}")

    def get_applicable_rules(self, context: Dict[str, Any]) -> List[MethodologyRule]:
        """获取适用规则。"""
        if not self.graph:
            return []

        try:
            query_parts = []
            params = {}
            if context.get("brand"):
                query_parts.append(
                    """
                    MATCH (r:MethodologyRule)-[:APPLIES_TO]->(b:Brand {name: $brand})
                    """
                )
                params["brand"] = context["brand"]
            elif context.get("industry"):
                query_parts.append(
                    """
                    MATCH (r:MethodologyRule)-[:APPLIES_TO]->(i:Industry {name: $industry})
                    """
                )
                params["industry"] = context["industry"]
            else:
                query_parts.append("MATCH (r:MethodologyRule)")

            query = "".join(query_parts) + """
            WHERE r.rule_type IN ['general', $rule_type]
            RETURN r
            ORDER BY r.priority DESC
            LIMIT 50
            """
            params["rule_type"] = context.get("rule_type", "general")
            results = self.graph.query(query, params=params)

            rules: List[MethodologyRule] = []
            for result in results:
                rule_data = dict(result["r"])
                for key in ("conditions", "application_scenarios", "effects"):
                    if key in rule_data and isinstance(rule_data[key], str):
                        try:
                            rule_data[key] = json.loads(rule_data[key])
                        except Exception:
                            pass
                rule = MethodologyRule(rule_data)
                if rule.matches(context):
                    rules.append(rule)
            rules.sort(key=lambda x: x.priority, reverse=True)
            return rules
        except Exception as exc:
            print(f"获取适用规则失败: {exc}")
            return []

    def resolve_rule_conflicts(self, rules: List[MethodologyRule]) -> List[MethodologyRule]:
        """解决规则冲突。"""
        if len(rules) <= 1:
            return rules
        rules.sort(key=lambda x: x.priority, reverse=True)
        resolved: List[MethodologyRule] = []
        for rule in rules:
            conflict = False
            for selected_rule in resolved:
                if rule.rule_type == selected_rule.rule_type and rule.rule_type != "general":
                    if rule.effects.get("conflicts_with") == selected_rule.rule_id:
                        conflict = True
                        break
            if not conflict:
                resolved.append(rule)
        return resolved

    def get_rule(self, rule_id: str) -> Optional[MethodologyRule]:
        """根据 ID 获取规则。"""
        if not self.graph:
            return None
        try:
            results = self.graph.query(
                """
                MATCH (r:MethodologyRule {rule_id: $rule_id})
                RETURN r
                """,
                params={"rule_id": rule_id},
            )
            if not results:
                return None
            rule_data = dict(results[0]["r"])
            for key in ("conditions", "application_scenarios", "effects"):
                if key in rule_data and isinstance(rule_data[key], str):
                    try:
                        rule_data[key] = json.loads(rule_data[key])
                    except Exception:
                        pass
            return MethodologyRule(rule_data)
        except Exception as exc:
            print(f"获取规则失败: {exc}")
            return None

    def apply_rules_to_prompt(self, rules: List[MethodologyRule], base_prompt: str) -> str:
        """将规则附加到提示词上。"""
        if not rules:
            return base_prompt
        rules_text = "\n\n## 应用的方法论规则:\n\n"
        for idx, rule in enumerate(rules, 1):
            rules_text += f"{idx}. **{rule.name}** (优先级: {rule.priority})\n"
            rules_text += f"   - 描述: {rule.description}\n"
            rules_text += f"   - 内容: {rule.content}\n"
            if rule.effects:
                rules_text += f"   - 效果: {json.dumps(rule.effects, ensure_ascii=False)}\n"
            rules_text += "\n"
        return base_prompt + rules_text

