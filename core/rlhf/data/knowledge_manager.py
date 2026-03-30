#!/usr/bin/env python3
"""
品牌知识管理系统
支持品牌列表的导入、管理、查询和存储
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from core.common.pr_neo4j_env import graph


class BrandKnowledgeManager:
    """品牌知识管理器"""

    def __init__(self) -> None:
        self.graph = graph
        self.brand_cache: Dict[str, Dict[str, Any]] = {}

    def import_brands_from_json(self, json_path: str) -> Dict[str, Any]:
        """从JSON文件导入品牌列表"""
        try:
            with open(json_path, "r", encoding="utf-8") as fh:
                brands_data = json.load(fh)
            if isinstance(brands_data, list):
                brands = brands_data
            elif isinstance(brands_data, dict) and "brands" in brands_data:
                brands = brands_data["brands"]
            else:
                brands = [brands_data]

            results = {"total": len(brands), "imported": 0, "updated": 0, "errors": []}
            for brand_data in brands:
                try:
                    result = self.add_or_update_brand(brand_data)
                    if result.get("created"):
                        results["imported"] += 1
                    else:
                        results["updated"] += 1
                except Exception as exc:  # pragma: no cover - 各种数据错误
                    results["errors"].append({"brand": brand_data.get("name", "Unknown"), "error": str(exc)})
            return results
        except Exception as exc:
            return {"error": f"导入失败: {exc}"}

    def import_brands_from_csv(self, csv_path: str) -> Dict[str, Any]:
        """从CSV文件导入品牌列表"""
        try:
            df = pd.read_csv(csv_path, encoding="utf-8")
            brands = df.to_dict("records")
            return self._bulk_import(brands)
        except Exception as exc:
            return {"error": f"导入失败: {exc}"}

    def import_brands_from_excel(self, excel_path: str, sheet_name: str = 0) -> Dict[str, Any]:
        """从Excel文件导入品牌列表"""
        try:
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
            brands = df.to_dict("records")
            return self._bulk_import(brands)
        except Exception as exc:
            return {"error": f"导入失败: {exc}"}

    def _bulk_import(self, brands: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = {"total": len(brands), "imported": 0, "updated": 0, "errors": []}
        for brand_data in brands:
            try:
                brand_data = {k: v for k, v in brand_data.items() if pd.notna(v)}
                outcome = self.add_or_update_brand(brand_data)
                if outcome.get("created"):
                    results["imported"] += 1
                else:
                    results["updated"] += 1
            except Exception as exc:
                results["errors"].append({"brand": brand_data.get("name", "Unknown"), "error": str(exc)})
        return results

    def add_or_update_brand(self, brand_data: Dict[str, Any]) -> Dict[str, Any]:
        """添加或更新品牌信息"""
        if not self.graph:
            return {"error": "Neo4j连接不可用"}

        name = brand_data.get("name")
        if not name:
            return {"error": "品牌名称不能为空"}

        properties = {
            "name": name,
            "industry": brand_data.get("industry", ""),
            "brand_positioning": brand_data.get("brand_positioning", ""),
            "brand_personality": brand_data.get("brand_personality", ""),
            "target_audience": brand_data.get("target_audience", ""),
            "founded_year": brand_data.get("founded_year", ""),
            "brand_value": brand_data.get("brand_value", ""),
            "characteristics": brand_data.get("characteristics", ""),
            "history": brand_data.get("history", ""),
            "updated_at": datetime.now().isoformat(),
        }
        properties = {k: v for k, v in properties.items() if v}

        try:
            existing = self.graph.query(
                """
                MATCH (b:Brand {name: $name})
                RETURN b
                """,
                params={"name": name},
            )

            if existing:
                self.graph.query(
                    """
                    MATCH (b:Brand {name: $name})
                    SET b += $properties
                    RETURN b
                    """,
                    params={"name": name, "properties": properties},
                )
                return {"created": False, "brand": name, "action": "updated"}
            else:
                self.graph.query(
                    """
                    CREATE (b:Brand $properties)
                    RETURN b
                    """,
                    params={"properties": properties},
                )
                return {"created": True, "brand": name, "action": "created"}
        except Exception as exc:
            return {"error": f"操作失败: {exc}"}

    def get_brand(self, brand_name: str) -> Optional[Dict[str, Any]]:
        """查询品牌信息"""
        if not self.graph:
            return None
        try:
            results = self.graph.query(
                """
                MATCH (b:Brand {name: $name})
                OPTIONAL MATCH (b)-[r]->(related)
                RETURN b, collect({
                    relationship: type(r),
                    related: properties(related),
                    related_type: labels(related)[0]
                }) as relationships
                """,
                params={"name": brand_name},
            )
            if not results:
                return None
            brand_node = results[0]["b"]
            relationships = results[0]["relationships"]
            return {"brand": dict(brand_node), "relationships": relationships}
        except Exception as exc:
            print(f"查询品牌失败: {exc}")
            return None

    def search_brands(self, keyword: str, industry: Optional[str] = None) -> List[Dict[str, Any]]:
        """搜索品牌"""
        if not self.graph:
            return []
        try:
            if industry:
                query = """
                    MATCH (b:Brand)
                    WHERE b.name CONTAINS $keyword AND b.industry = $industry
                    RETURN b
                    LIMIT 50
                """
                params = {"keyword": keyword, "industry": industry}
            else:
                query = """
                    MATCH (b:Brand)
                    WHERE b.name CONTAINS $keyword
                    RETURN b
                    LIMIT 50
                """
                params = {"keyword": keyword}
            results = self.graph.query(query, params=params)
            return [dict(result["b"]) for result in results]
        except Exception as exc:
            print(f"搜索品牌失败: {exc}")
            return []

    def get_brand_history(self, brand_name: str) -> List[Dict[str, Any]]:
        """获取品牌历史案例"""
        if not self.graph:
            return []
        try:
            results = self.graph.query(
                """
                MATCH (b:Brand {name: $name})-[r:LAUNCHES_CAMPAIGN]->(c:Campaign)
                RETURN c, r
                ORDER BY c.launch_date DESC
                LIMIT 20
                """,
                params={"name": brand_name},
            )
            return [{"campaign": dict(result["c"]), "relationship": dict(result["r"])} for result in results]
        except Exception as exc:
            print(f"获取品牌历史失败: {exc}")
            return []

    def validate_brand_data(self, brand_data: Dict[str, Any]) -> Dict[str, Any]:
        """验证品牌数据"""
        errors = []
        warnings = []

        if not brand_data.get("name"):
            errors.append("品牌名称不能为空")

        if "founded_year" in brand_data and brand_data["founded_year"]:
            try:
                year = int(brand_data["founded_year"])
                if year < 1800 or year > datetime.now().year:
                    warnings.append(f"成立年份 {year} 可能不正确")
            except Exception:
                warnings.append("成立年份格式不正确")

        if brand_data.get("name"):
            existing = self.get_brand(brand_data["name"])
            if existing:
                warnings.append(f'品牌 {brand_data["name"]} 已存在，将更新')

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    def export_brands(self, output_path: str, format: str = "json") -> bool:
        """导出品牌列表"""
        if not self.graph:
            return False
        try:
            results = self.graph.query("MATCH (b:Brand) RETURN b")
            brands = [dict(result["b"]) for result in results]
            if format == "json":
                with open(output_path, "w", encoding="utf-8") as fh:
                    json.dump(brands, fh, ensure_ascii=False, indent=2)
            elif format == "csv":
                df = pd.DataFrame(brands)
                df.to_csv(output_path, index=False, encoding="utf-8-sig")
            elif format == "excel":
                df = pd.DataFrame(brands)
                df.to_excel(output_path, index=False)
            else:
                return False
            return True
        except Exception as exc:
            print(f"导出品牌失败: {exc}")
            return False

