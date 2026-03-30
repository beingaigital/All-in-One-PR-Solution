"""Agent Profile Layer：加载 IDENTITY/USER/SOUL/AGENT/MEMORY/TOOLS 文档。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from utils.path import get_config_path, get_project_root


DEFAULT_SECTION_FILES: Dict[str, str] = {
    "identity": "IDENTITY.md",
    "user": "USER.md",
    "soul": "SOUL.md",
    "agent": "AGENT.md",
    "memory": "MEMORY.md",
    "tools": "TOOLS.md",
}

DEFAULT_ORDER: List[str] = ["identity", "soul", "user", "agent", "memory", "tools"]


@dataclass
class ProfileSection:
    key: str
    file_path: Path
    exists: bool
    content: str
    truncated: bool
    error: Optional[str] = None


@dataclass
class AgentProfileContext:
    enabled: bool
    max_chars_per_file: int
    section_order: List[str]
    sections: Dict[str, ProfileSection]
    config_path: Path

    def to_prompt(self, tool_registry_section: str = "") -> Tuple[str, bool]:
        """渲染为可注入到 system prompt 的文本。"""
        if not self.enabled:
            return "", False

        parts: List[str] = []
        tool_placeholder_used = False

        for key in self.section_order:
            section = self.sections.get(key)
            if not section or not section.exists or not section.content:
                continue

            body = section.content
            if key == "tools" and "{{tool_registry}}" in body:
                replacement = tool_registry_section.strip() or "（当前无可用工具）"
                body = body.replace("{{tool_registry}}", replacement)
                tool_placeholder_used = True

            title = key.upper()
            parts.append(f"## Profile::{title}\n{body.strip()}")

        return "\n\n".join(parts).strip(), tool_placeholder_used


_profile_cache: Optional[AgentProfileContext] = None
_profile_cache_key: Optional[tuple[Optional[float]]] = None


def _load_profile_yaml(config_path: Path) -> Dict:
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _build_cache_key(config_path: Path) -> tuple[Optional[float]]:
    if not config_path.exists():
        return (None,)
    try:
        return (config_path.stat().st_mtime,)
    except Exception:
        return (None,)


def _clamp_text(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0:
        return text, False
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars].rstrip() + "\n\n[...已截断...]", True


def clear_profile_context_cache() -> None:
    """清空 profile 缓存。"""
    global _profile_cache, _profile_cache_key
    _profile_cache = None
    _profile_cache_key = None


def get_profile_context(force_reload: bool = False) -> AgentProfileContext:
    """获取 Agent Profile 上下文（带缓存）。"""
    global _profile_cache, _profile_cache_key

    config_path = get_config_path("profile.yaml")
    cache_key = _build_cache_key(config_path)

    if not force_reload and _profile_cache is not None and _profile_cache_key == cache_key:
        return _profile_cache

    raw = _load_profile_yaml(config_path)
    enabled = bool(raw.get("enabled", True))
    max_chars = int(raw.get("max_chars_per_file", 2500) or 2500)

    raw_order = raw.get("prompt_sections_order") or DEFAULT_ORDER
    section_order = [str(s).strip().lower() for s in raw_order if str(s).strip()]
    if not section_order:
        section_order = list(DEFAULT_ORDER)

    files_map = dict(DEFAULT_SECTION_FILES)
    files_cfg = raw.get("files") or {}
    if isinstance(files_cfg, dict):
        for key, value in files_cfg.items():
            k = str(key).strip().lower()
            if not k:
                continue
            v = str(value).strip()
            if v:
                files_map[k] = v

    root = get_project_root()
    sections: Dict[str, ProfileSection] = {}
    for key in section_order:
        rel_path = files_map.get(key)
        if not rel_path:
            continue
        file_path = (root / rel_path).resolve()
        if not file_path.exists():
            sections[key] = ProfileSection(
                key=key,
                file_path=file_path,
                exists=False,
                content="",
                truncated=False,
                error="文件不存在",
            )
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace").strip()
            text, truncated = _clamp_text(text, max_chars)
            sections[key] = ProfileSection(
                key=key,
                file_path=file_path,
                exists=True,
                content=text,
                truncated=truncated,
            )
        except Exception as exc:
            sections[key] = ProfileSection(
                key=key,
                file_path=file_path,
                exists=True,
                content="",
                truncated=False,
                error=str(exc),
            )

    context = AgentProfileContext(
        enabled=enabled,
        max_chars_per_file=max_chars,
        section_order=section_order,
        sections=sections,
        config_path=config_path,
    )
    _profile_cache = context
    _profile_cache_key = cache_key
    return context
