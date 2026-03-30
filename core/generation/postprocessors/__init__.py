"""后处理模块：负责统一格式化生成结果。"""

from .formatters import normalize_text, format_plan_results

__all__ = ["normalize_text", "format_plan_results"]
