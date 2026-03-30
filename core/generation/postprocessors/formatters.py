"""
生成结果后处理工具。
"""

from __future__ import annotations

from typing import Dict, Any


def normalize_text(value: Any) -> Any:
    """确保输出为干净的字符串。"""
    if isinstance(value, str):
        return value.strip()
    return value


def format_plan_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """统一对生成结果进行后处理。"""
    return {plan_type: normalize_text(content) for plan_type, content in results.items()}

