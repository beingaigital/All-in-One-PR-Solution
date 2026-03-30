"""方案需求澄清状态（按 task_id 持久化）。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from utils.path import ensure_task_dirs, get_task_dir


DEFAULT_REQUIREMENTS: Dict[str, Any] = {
    "enterprise_name": "",
    "industry": "",
    "pr_cycle": "",
    "pr_budget": "",
    "pr_goal": "",
    "enterprise_stage": "",
    "market_type": "",
    "innovation": "适度创新",
    "target_audience": "",
    "key_messages": "",
    "extra_requirements": "",
    "output_types": "A,B,C",
    "use_graph_rag": True,
    "use_web_search": True,
    "ip_name": "",
}


def _state_path(task_id: str) -> Path:
    ensure_task_dirs(task_id)
    return get_task_dir(task_id) / "plan_requirements_state.json"


def _default_state(task_id: str) -> Dict[str, Any]:
    now = datetime.now().isoformat()
    return {
        "task_id": task_id,
        "requirements": dict(DEFAULT_REQUIREMENTS),
        "confirmed": False,
        "updated_at": now,
        "history": [],
    }


def load_plan_requirements_state(task_id: str) -> Dict[str, Any]:
    """读取会话内需求状态；不存在则返回默认状态。"""
    path = _state_path(task_id)
    if not path.exists():
        return _default_state(task_id)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return _default_state(task_id)
    except Exception:
        return _default_state(task_id)

    state = _default_state(task_id)
    state.update(raw)
    req = raw.get("requirements") if isinstance(raw.get("requirements"), dict) else {}
    merged_req = dict(DEFAULT_REQUIREMENTS)
    merged_req.update(req)
    state["requirements"] = merged_req
    state["task_id"] = task_id
    return state


def save_plan_requirements_state(task_id: str, state: Dict[str, Any]) -> None:
    """保存会话内需求状态。"""
    path = _state_path(task_id)
    payload = dict(state or {})
    payload["task_id"] = task_id
    payload["updated_at"] = datetime.now().isoformat()
    if not isinstance(payload.get("requirements"), dict):
        payload["requirements"] = dict(DEFAULT_REQUIREMENTS)
    else:
        req = dict(DEFAULT_REQUIREMENTS)
        req.update(payload["requirements"])
        payload["requirements"] = req
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def reset_plan_requirements_state(task_id: str) -> Dict[str, Any]:
    """重置会话内需求状态并落盘。"""
    state = _default_state(task_id)
    save_plan_requirements_state(task_id, state)
    return state

