"""Skills Layer：加载 skills/*.md 并按场景自动激活。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from utils.path import get_config_path, get_project_root


@dataclass
class SkillRegistryConfig:
    enabled: bool = True
    auto_activate: bool = True
    discover_files: bool = True
    max_chars_per_skill: int = 1800
    max_active_skills: int = 3
    max_total_chars: int = 4200
    always_on: List[str] = field(default_factory=list)
    disabled: List[str] = field(default_factory=list)


@dataclass
class SkillInfo:
    skill_id: str
    title: str
    file_path: Path
    enabled: bool
    priority: int
    keywords: List[str]
    content: str
    summary: str
    truncated: bool = False
    source: str = "configured"
    error: Optional[str] = None


@dataclass
class SkillRegistry:
    config_path: Path
    config: SkillRegistryConfig
    skills: Dict[str, SkillInfo]
    load_errors: List[Dict[str, str]]


_registry_cache: Optional[SkillRegistry] = None
_registry_cache_key: Optional[tuple[Optional[float]]] = None


def _normalize_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _to_skill_id(raw: str) -> str:
    return str(raw).strip().lower().replace(" ", "_").replace("-", "_")


def _clamp(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0:
        return text, False
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars].rstrip() + "\n\n[...skill content truncated...]", True


def _summary_from_content(content: str) -> str:
    lines = [line.strip() for line in (content or "").splitlines() if line.strip()]
    if not lines:
        return "无描述"

    # 跳过 markdown 标题和列表符号，取第一句有效内容
    for line in lines:
        if line.startswith("#"):
            continue
        candidate = line.lstrip("- ").strip()
        if candidate:
            return candidate[:140]
    return lines[0][:140]


def _load_yaml(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
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


def _load_skill_file(path: Path, max_chars: int) -> tuple[str, bool, Optional[str]]:
    if not path.exists():
        return "", False, "file_not_found"
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
        text, truncated = _clamp(raw, max_chars)
        return text, truncated, None
    except Exception as exc:
        return "", False, str(exc)


def clear_skill_registry_cache() -> None:
    """清空 skills 缓存。"""
    global _registry_cache, _registry_cache_key
    _registry_cache = None
    _registry_cache_key = None


def get_skill_registry(force_reload: bool = False) -> SkillRegistry:
    """获取技能注册中心（带缓存）。"""
    global _registry_cache, _registry_cache_key

    config_path = get_config_path("skills.yaml")
    cache_key = _build_cache_key(config_path)
    if not force_reload and _registry_cache is not None and _registry_cache_key == cache_key:
        return _registry_cache

    raw = _load_yaml(config_path)
    manual = raw.get("manual_activation") if isinstance(raw.get("manual_activation"), dict) else {}
    config = SkillRegistryConfig(
        enabled=bool(raw.get("enabled", True)),
        auto_activate=bool(raw.get("auto_activate", True)),
        discover_files=bool(raw.get("discover_files", True)),
        max_chars_per_skill=int(raw.get("max_chars_per_skill", 1800) or 1800),
        max_active_skills=int(raw.get("max_active_skills", 3) or 3),
        max_total_chars=int(raw.get("max_total_chars", 4200) or 4200),
        always_on=[_to_skill_id(x) for x in _normalize_list(manual.get("always_on"))],
        disabled=[_to_skill_id(x) for x in _normalize_list(manual.get("disabled"))],
    )

    skills: Dict[str, SkillInfo] = {}
    load_errors: List[Dict[str, str]] = []
    root = get_project_root()

    cfg_skills = raw.get("skills") if isinstance(raw.get("skills"), dict) else {}
    for key, meta in cfg_skills.items():
        skill_id = _to_skill_id(key)
        meta_dict = meta if isinstance(meta, dict) else {}
        rel_file = str(meta_dict.get("file", f"skills/{skill_id}.md")).strip()
        file_path = (root / rel_file).resolve()
        enabled = bool(meta_dict.get("enabled", True))
        priority = int(meta_dict.get("priority", 50) or 50)
        keywords = _normalize_list(meta_dict.get("keywords"))
        title = str(meta_dict.get("title", skill_id)).strip() or skill_id

        content, truncated, err = _load_skill_file(file_path, config.max_chars_per_skill)
        if err:
            load_errors.append({"skill_id": skill_id, "error": err, "file": str(file_path)})

        skills[skill_id] = SkillInfo(
            skill_id=skill_id,
            title=title,
            file_path=file_path,
            enabled=enabled,
            priority=priority,
            keywords=keywords,
            content=content,
            summary=_summary_from_content(content) if content else "无描述",
            truncated=truncated,
            source="configured",
            error=err,
        )

    if config.discover_files:
        skills_dir = root / "skills"
        if skills_dir.exists() and skills_dir.is_dir():
            for path in sorted(skills_dir.glob("*.md")):
                sid = _to_skill_id(path.stem)
                if sid in skills:
                    continue
                content, truncated, err = _load_skill_file(path, config.max_chars_per_skill)
                if err:
                    load_errors.append({"skill_id": sid, "error": err, "file": str(path)})
                skills[sid] = SkillInfo(
                    skill_id=sid,
                    title=path.stem,
                    file_path=path,
                    enabled=True,
                    priority=40,
                    keywords=[],
                    content=content,
                    summary=_summary_from_content(content) if content else "无描述",
                    truncated=truncated,
                    source="discovered",
                    error=err,
                )

    registry = SkillRegistry(
        config_path=config_path,
        config=config,
        skills=skills,
        load_errors=load_errors,
    )
    _registry_cache = registry
    _registry_cache_key = cache_key
    return registry


def _score_skill(skill: SkillInfo, query: str) -> float:
    text = (query or "").strip().lower()
    if not text:
        return 0.0

    score = 0.0
    if skill.skill_id in text:
        score += 4.0
    if skill.title and skill.title.lower() in text:
        score += 2.0
    for kw in skill.keywords:
        token = kw.strip().lower()
        if token and token in text:
            score += 1.0
    score += skill.priority / 100.0
    return score


def get_active_skills_for_query(query: str, force_reload: bool = False) -> List[SkillInfo]:
    """按 query 返回应激活的技能列表。"""
    registry = get_skill_registry(force_reload=force_reload)
    cfg = registry.config
    if not cfg.enabled:
        return []

    disabled_set = set(cfg.disabled)
    available: Dict[str, SkillInfo] = {}
    for sid, skill in registry.skills.items():
        if not skill.enabled:
            continue
        if sid in disabled_set:
            continue
        if skill.error:
            continue
        available[sid] = skill

    active: List[SkillInfo] = []
    used = set()

    for sid in cfg.always_on:
        skill = available.get(sid)
        if not skill:
            continue
        active.append(skill)
        used.add(sid)

    if cfg.auto_activate:
        scored: List[tuple[float, SkillInfo]] = []
        for sid, skill in available.items():
            if sid in used:
                continue
            score = _score_skill(skill, query)
            if score > (skill.priority / 100.0):  # 至少命中一个显式信号
                scored.append((score, skill))
        scored.sort(key=lambda x: x[0], reverse=True)
        for _, skill in scored[: max(0, cfg.max_active_skills)]:
            active.append(skill)

    # 控制总字符预算
    limited: List[SkillInfo] = []
    total_chars = 0
    for skill in active:
        content_len = len(skill.content or "")
        if cfg.max_total_chars > 0 and total_chars + content_len > cfg.max_total_chars:
            continue
        limited.append(skill)
        total_chars += content_len
    return limited


def format_active_skills_for_prompt(query: str, force_reload: bool = False) -> str:
    """将激活技能渲染成 prompt 片段。"""
    skills = get_active_skills_for_query(query, force_reload=force_reload)
    if not skills:
        return ""

    parts = [
        "以下是本轮根据用户需求自动激活的技能指令。它们是补充约束，若与用户当前明确指令冲突，请以用户当前指令为准。"
    ]
    for skill in skills:
        parts.append(f"### ActiveSkill::{skill.skill_id}\n{skill.content.strip()}")
    return "\n\n".join(parts).strip()


def format_skill_catalog_for_prompt(force_reload: bool = False) -> str:
    """渲染可用技能目录（用于全局 system prompt）。"""
    registry = get_skill_registry(force_reload=force_reload)
    cfg = registry.config
    if not cfg.enabled:
        return ""

    lines = ["## Skills Catalog", ""]
    for sid in sorted(registry.skills.keys()):
        skill = registry.skills[sid]
        if not skill.enabled or skill.error:
            continue
        kw = ", ".join(skill.keywords[:8]) if skill.keywords else "无关键词"
        lines.append(f"- **{sid}**: {skill.summary} (keywords: {kw})")
    return "\n".join(lines).strip()
