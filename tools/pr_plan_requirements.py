"""方案需求澄清与确认工具。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List

from langchain_core.tools import tool

from utils.plan_requirements_state import (
    DEFAULT_REQUIREMENTS,
    load_plan_requirements_state,
    reset_plan_requirements_state,
    save_plan_requirements_state,
)
from utils.task_context import get_task_id


REQUIRED_FIELDS: List[str] = [
    "enterprise_name",
    "industry",
    "pr_cycle",
    "pr_budget",
    "pr_goal",
]

FIELD_QUESTIONS: Dict[str, str] = {
    "enterprise_name": "请确认这次服务的企业/品牌全称是什么？",
    "industry": "该品牌所属行业/赛道是什么？（例如：潮玩/文创）",
    "pr_goal": "这次传播最核心目标是什么？（可写成一句可衡量结果）",
    "pr_cycle": "计划周期希望多久？（如 4周 / 8周 / 3个月）",
    "pr_budget": "预算大概是多少？（如 10万 / 30万 / 50万）",
    "target_audience": "目标受众是谁？（如年级、兴趣、圈层）",
    "output_types": "更希望输出哪些方案类型？可选 A-F（默认 A,B,C）。",
}


def _clean_text(text: str) -> str:
    return (text or "").strip()


def _contains_any(text: str, keywords: List[str]) -> bool:
    body = text.lower()
    return any(k.lower() in body for k in keywords)


def _is_confirm_text(text: str) -> bool:
    body = _clean_text(text)
    if not body:
        return False
    deny_keywords = [
        "先别",
        "不要生成",
        "暂不生成",
        "先不生成",
        "继续修改",
        "先改",
    ]
    if _contains_any(body, deny_keywords):
        return False
    allow_keywords = [
        "确认生成",
        "确认",
        "可以生成",
        "开始生成",
        "就按这个生成",
        "没问题生成",
        "ok生成",
        "好的生成",
    ]
    return _contains_any(body, allow_keywords)


def _extract_first(pattern: str, text: str) -> str:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if not m:
        return ""
    return _clean_text(m.group(1))


def _trim_by_markers(text: str, markers: List[str]) -> str:
    out = _clean_text(text)
    cut = len(out)
    for marker in markers:
        idx = out.find(marker)
        if 0 < idx < cut:
            cut = idx
    out = out[:cut].strip(" ，,。；;：:")
    return out


def _extract_output_types(text: str) -> str:
    if not text:
        return ""
    up = text.upper()
    seq_matches = re.findall(r"([A-F](?:\s*[,，、/]\s*[A-F]){1,5})", up)
    found: List[str] = []
    for seq in seq_matches:
        for ch in re.findall(r"[A-F]", seq):
            if ch not in found:
                found.append(ch)

    if found:
        return ",".join(found)

    single_match = re.search(r"(?:输出|模板|类型|方案)\s*[:：]?\s*([A-F])\b", up)
    if single_match:
        return single_match.group(1)
    return ""


def _extract_budget(text: str) -> str:
    patterns = [
        r"(\d+(?:\.\d+)?\s*(?:亿|亿元|万|万元|千|k|K|w|W|元))",
        r"(预算[^，。；;\n]{1,20})",
    ]
    for p in patterns:
        hit = _extract_first(p, text)
        if hit:
            return hit
    return ""


def _extract_cycle(text: str) -> str:
    patterns = [
        r"(\d+\s*(?:天|周|个月|月|季度|年))",
        r"(周期[^，。；;\n]{1,20})",
    ]
    for p in patterns:
        hit = _extract_first(p, text)
        if hit:
            return hit
    return ""


def _extract_enterprise_name(text: str) -> str:
    patterns = [
        r"(?:给|为|帮|替)\s*([^，。,\s]{2,30}?)(?:的|做|制定|策划)",
        r"(?:品牌|企业|公司)\s*[:：]?\s*([^，。,\n]{2,30})",
    ]
    for p in patterns:
        hit = _extract_first(p, text)
        if hit:
            return hit
    return ""


def _extract_ip_name(text: str) -> str:
    patterns = [
        r"(?:ip|IP)\s*(?:叫|名为|是|:|：)?\s*([A-Za-z0-9_\-\u4e00-\u9fa5]{2,40})",
        r"(?:叫|名为)\s*([A-Za-z0-9_\-\u4e00-\u9fa5]{2,40})\s*(?:做|的|进行|展开|来)",
    ]
    for p in patterns:
        hit = _extract_first(p, text)
        if hit:
            cleaned = hit
            for stop in ["做", "进行", "展开", "的", "，", "。", "计划", "方案", "推广"]:
                if stop in cleaned:
                    cleaned = cleaned.split(stop, 1)[0].strip()
            return cleaned
    return ""


def _extract_industry(text: str) -> str:
    if "潮玩" in text:
        return "潮玩/文创"
    hit = _extract_first(r"(?:行业|赛道|领域|品类)\s*[:：]?\s*([^，。,\n]{2,30})", text)
    return hit


def _extract_goal(text: str) -> str:
    patterns = [
        r"(?:目标|目的|希望|要达成|要实现)\s*[:：]?\s*([^。；;\n]{4,120})",
        r"做一个([^。；;\n]{4,120}计划)",
        r"做一份([^。；;\n]{4,120}方案)",
    ]
    for p in patterns:
        hit = _extract_first(p, text)
        if hit:
            if hit.startswith("是"):
                hit = hit[1:].strip()
            hit = _trim_by_markers(
                hit,
                ["输出类型", "输出", "额外要求", "补充要求", "侧重", "重点"],
            )
            return hit
    return ""


def _extract_audience(text: str) -> str:
    hit = _extract_first(r"(?:受众|目标人群|人群|面向|针对)\s*[:：]?\s*([^。；;\n]{2,80})", text)
    if hit:
        return hit
    if "校园" in text or "大学生" in text:
        return "大学生（18-24岁）"
    return ""


def _extract_innovation(text: str) -> str:
    if _contains_any(text, ["高度创新", "大胆创新", "激进创新"]):
        return "高度创新"
    if _contains_any(text, ["保守", "稳健"]):
        return "稳健保守"
    if "适度创新" in text:
        return "适度创新"
    return ""


def _extract_extra_requirements(text: str) -> str:
    hit = _extract_first(r"(?:要求|侧重|重点|补充|特别注意)\s*[:：]?\s*([^。；;\n]{4,200})", text)
    if hit.startswith("是"):
        hit = hit[1:].strip()
    return _trim_by_markers(hit, ["输出类型", "输出", "目标", "预算", "周期"])


def _merge_requirements(req: Dict[str, Any], text: str) -> Dict[str, Any]:
    merged = dict(req)
    body = _clean_text(text)
    if not body:
        return merged

    enterprise_name = _extract_enterprise_name(body)
    if enterprise_name:
        merged["enterprise_name"] = enterprise_name

    industry = _extract_industry(body)
    if industry:
        merged["industry"] = industry

    cycle = _extract_cycle(body)
    if cycle:
        merged["pr_cycle"] = cycle

    budget = _extract_budget(body)
    if budget:
        merged["pr_budget"] = budget

    goal = _extract_goal(body)
    if goal:
        merged["pr_goal"] = goal

    audience = _extract_audience(body)
    if audience:
        merged["target_audience"] = audience

    innovation = _extract_innovation(body)
    if innovation:
        merged["innovation"] = innovation

    output_types = _extract_output_types(body)
    if output_types:
        merged["output_types"] = output_types

    extra = _extract_extra_requirements(body)
    if extra:
        merged["extra_requirements"] = extra

    ip_name = _extract_ip_name(body)
    if ip_name:
        merged["ip_name"] = ip_name
        if not merged.get("key_messages"):
            merged["key_messages"] = f"核心IP：{ip_name}"
        elif ip_name.lower() not in str(merged.get("key_messages", "")).lower():
            merged["key_messages"] = f"{merged.get('key_messages')}；核心IP：{ip_name}"

    # 给常见自然语言表达做最小补全（不猜预算/周期）
    if not merged.get("pr_goal") and _contains_any(body, ["校园推广", "校园传播"]):
        merged["pr_goal"] = "提升校园人群认知并促进社群与转化"

    return merged


def _missing_required(req: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    for f in REQUIRED_FIELDS:
        if not _clean_text(str(req.get(f, ""))):
            missing.append(f)
    return missing


def _follow_up_questions(req: Dict[str, Any], missing: List[str]) -> List[str]:
    questions: List[str] = []
    for f in missing:
        if f in FIELD_QUESTIONS:
            questions.append(FIELD_QUESTIONS[f])
    if not req.get("target_audience"):
        questions.append(FIELD_QUESTIONS["target_audience"])
    if not req.get("output_types"):
        questions.append(FIELD_QUESTIONS["output_types"])
    return questions[:3]


@tool
def pr_plan_requirements(
    latest_user_input: str,
    reset: bool = False,
) -> str:
    """
    描述：方案生成前的需求澄清工具。将用户多轮输入聚合为结构化字段，输出缺失项、追问问题与确认卡片。
    使用时机：当用户提出“做方案/做推广计划”但信息不完整，或需要先确认需求再生成方案。
    输入：
    - latest_user_input（必填）：用户当前轮补充信息或确认语句。
    - reset（可选）：是否重置当前会话的需求草稿，默认 false。
    输出：JSON 字符串，包含 status / missing_required / follow_up_questions / requirements / generation_payload。
    """
    task_id = get_task_id() or "default"

    if reset:
        state = reset_plan_requirements_state(task_id)
    else:
        state = load_plan_requirements_state(task_id)

    req = dict(DEFAULT_REQUIREMENTS)
    req.update(state.get("requirements") or {})
    before_req = dict(req)
    req = _merge_requirements(req, latest_user_input)
    changed = req != before_req

    confirmed = bool(state.get("confirmed"))
    if changed and not _is_confirm_text(latest_user_input):
        confirmed = False
    if _is_confirm_text(latest_user_input):
        confirmed = True

    missing = _missing_required(req)
    follow_ups = _follow_up_questions(req, missing)

    if missing:
        status = "clarification_needed"
        confirmed = False
    elif not confirmed:
        status = "pending_confirmation"
    else:
        status = "confirmed"

    generation_payload = {
        "enterprise_name": req.get("enterprise_name", ""),
        "industry": req.get("industry", ""),
        "pr_cycle": req.get("pr_cycle", ""),
        "pr_budget": req.get("pr_budget", ""),
        "pr_goal": req.get("pr_goal", ""),
        "enterprise_stage": req.get("enterprise_stage", ""),
        "market_type": req.get("market_type", ""),
        "innovation": req.get("innovation", "适度创新"),
        "target_audience": req.get("target_audience", ""),
        "key_messages": req.get("key_messages", ""),
        "extra_requirements": req.get("extra_requirements", ""),
        "output_types": req.get("output_types", "A,B,C"),
        "use_graph_rag": bool(req.get("use_graph_rag", True)),
        "use_web_search": bool(req.get("use_web_search", True)),
        "requirements_confirmed": confirmed and not missing,
    }

    state["requirements"] = req
    state["confirmed"] = bool(confirmed and not missing)
    state.setdefault("history", [])
    state["history"].append(
        {
            "timestamp": datetime.now().isoformat(),
            "input": latest_user_input,
            "status": status,
            "missing_required": missing,
        }
    )
    save_plan_requirements_state(task_id, state)

    confirmation_hint = ""
    if status == "pending_confirmation":
        confirmation_hint = "请先确认以下需求卡片；若无修改，请回复“确认生成”。"
    elif status == "confirmed":
        confirmation_hint = "需求已确认，可调用 pr_generate_plan 生成方案。"
    else:
        confirmation_hint = "请先补充缺失字段，再进入确认。"

    payload = {
        "task_id": task_id,
        "status": status,
        "confirmed": bool(state.get("confirmed")),
        "missing_required": missing,
        "follow_up_questions": follow_ups,
        "confirmation_hint": confirmation_hint,
        "requirements": req,
        "generation_payload": generation_payload,
    }
    return json.dumps(payload, ensure_ascii=False)
