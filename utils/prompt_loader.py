"""从 config/prompt.yaml 加载映射，prompt 文件从 prompt 目录读取；并支持将工具注册表载入 system_prompt。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml

from utils.path import get_config_path, get_prompt_dir
from utils.profile_loader import get_profile_context
from utils.skill_registry import format_skill_catalog_for_prompt


def _load_prompt_yaml() -> Dict[str, Any]:
    """读取 config/prompt.yaml"""
    path = get_config_path("prompt.yaml")
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _resolve_value(value: Any, prompt_dir: Path) -> str:
    """若 value 为相对路径则从 prompt 目录读取文件内容，否则返回字符串"""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if "/" in s or "\\" in s or not s.startswith("http"):
        file_path = (prompt_dir / s).resolve()
        if file_path.is_file():
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        return s
    return s


def get_prompt_config() -> Dict[str, str]:
    """
    加载 prompt 配置。从 config/prompt.yaml 读取映射，值为文件路径时
    返回示例：{"system_prompt": "你是一个 PRClaw 助手..."}
    """
    raw = _load_prompt_yaml()
    prompt_dir = get_prompt_dir()
    result: Dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(value, str) or value is None:
            result[key] = _resolve_value(value, prompt_dir)
        elif isinstance(value, dict):
            result[key] = str(value)
        else:
            result[key] = str(value)
    return result


def get_system_prompt() -> str:
    """获取 system_prompt 正文，供 agent 使用"""
    return get_prompt_config().get("system_prompt", "").strip()




def format_tool_registry_for_prompt(tools: List[Any]) -> str:
    """根据当前注册的工具列表生成「可用的工具列表及描述」段落，用于拼接到 system_prompt"""
    if not tools:
        return ""
    lines = ["## 当前可用工具", ""]
    for t in tools:
        name = getattr(t, "name", None) or getattr(t, "__class__", type(t)).__name__
        desc = getattr(t, "description", "") or ""
        desc_one = desc.strip().replace("\n", " ").strip()[:400]
        lines.append(f"- **{name}**：{desc_one}")
    return "\n".join(lines)


def get_system_prompt_with_tools(tools: List[Any]) -> str:
    """获取 system_prompt，并追加 Profile Layer 与工具注册信息。"""
    base = get_system_prompt().strip()
    tool_section = format_tool_registry_for_prompt(tools).strip()
    skill_catalog = format_skill_catalog_for_prompt().strip()

    profile_text = ""
    tools_injected_by_profile = False
    try:
        profile_ctx = get_profile_context()
        profile_text, tools_injected_by_profile = profile_ctx.to_prompt(tool_registry_section=tool_section)
        profile_text = profile_text.strip()
    except Exception:
        profile_text = ""
        tools_injected_by_profile = False

    parts = [p for p in [base, profile_text] if p]
    if tool_section and not tools_injected_by_profile:
        parts.append(tool_section)
    if skill_catalog:
        parts.append(skill_catalog)
    return "\n\n".join(parts).strip()
