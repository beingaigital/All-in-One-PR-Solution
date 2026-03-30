"""轻量长期记忆（LTM）：记录历史轮次并按相关度检索。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from utils.path import get_memory_dir


LTM_DIR_NAME = "LTM"
LTM_FILE_NAME = "turn_memory.jsonl"
MAX_SCAN_LINES = 2000


@dataclass
class TurnMemory:
    timestamp: str
    task_id: str
    query: str
    response: str
    summary: str


def _get_ltm_dir() -> Path:
    primary = get_memory_dir() / LTM_DIR_NAME
    try:
        primary.mkdir(parents=True, exist_ok=True)
        return primary
    except Exception:
        # 在受限环境下回退到 /tmp，避免主流程失败
        fallback = Path("/tmp") / "prclaw-memory" / LTM_DIR_NAME
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _get_ltm_file() -> Path:
    return _get_ltm_dir() / LTM_FILE_NAME


def _tokenize(text: str) -> List[str]:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", (text or "").lower()).strip()
    if not normalized:
        return []
    segments = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", normalized)
    stop_words = {
        "的",
        "了",
        "和",
        "是",
        "在",
        "帮我",
        "请",
        "这个",
        "那个",
        "进行",
        "分析",
        "一下",
    }
    tokens: List[str] = []
    seen = set()
    for seg in segments:
        s = seg.strip()
        if len(s) < 2 or s in stop_words or s in seen:
            continue
        seen.add(s)
        tokens.append(s)
    return tokens


def _jaccard_score(tokens_a: List[str], tokens_b: List[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return float(inter) / float(union) if union else 0.0


def _char_ngrams(text: str, n: int = 2) -> set[str]:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", (text or "").lower())
    if not normalized:
        return set()
    if len(normalized) <= n:
        return {normalized}
    return {normalized[i : i + n] for i in range(0, len(normalized) - n + 1)}


def _char_ngram_similarity(a: str, b: str, n: int = 2) -> float:
    sa = _char_ngrams(a, n=n)
    sb = _char_ngrams(b, n=n)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return float(inter) / float(union) if union else 0.0


def append_turn_memory(task_id: str, query: str, response: str, summary: str | None = None) -> None:
    """记录一轮对话到 LTM。"""
    q = (query or "").strip()
    r = (response or "").strip()
    if not q or not r:
        return

    item = {
        "timestamp": datetime.now().isoformat(),
        "task_id": task_id or "",
        "query": q,
        "response": r[:3000],
        "summary": (summary or r[:220]).strip(),
    }

    ltm_file = _get_ltm_file()
    with open(ltm_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(item, ensure_ascii=False) + "\n")


def _read_recent_turns(max_lines: int = MAX_SCAN_LINES) -> List[TurnMemory]:
    ltm_file = _get_ltm_file()
    if not ltm_file.exists():
        return []

    try:
        with open(ltm_file, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except Exception:
        return []

    rows = lines[-max_lines:]
    turns: List[TurnMemory] = []
    for line in rows:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            turns.append(
                TurnMemory(
                    timestamp=str(obj.get("timestamp", "")),
                    task_id=str(obj.get("task_id", "")),
                    query=str(obj.get("query", "")),
                    response=str(obj.get("response", "")),
                    summary=str(obj.get("summary", "")),
                )
            )
        except Exception:
            continue
    return turns


def retrieve_relevant_turns(query: str, top_k: int = 3) -> List[Dict]:
    """按关键词重叠检索相关历史轮次。"""
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    scored: List[Dict] = []
    for turn in _read_recent_turns():
        text = f"{turn.query} {turn.summary}"
        token_score = _jaccard_score(q_tokens, _tokenize(text))
        char_score = _char_ngram_similarity(query, text, n=2)
        score = 0.65 * token_score + 0.35 * char_score
        if score <= 0:
            continue
        scored.append(
            {
                "score": score,
                "timestamp": turn.timestamp,
                "task_id": turn.task_id,
                "query": turn.query,
                "summary": turn.summary,
            }
        )

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def format_relevant_memories_for_prompt(query: str, top_k: int = 3) -> str:
    """将检索到的长期记忆格式化为 prompt 片段。"""
    hits = retrieve_relevant_turns(query, top_k=top_k)
    if not hits:
        return ""

    lines = [
        "以下是与当前问题相关的历史长期记忆，仅作为参考，若与当前用户指令冲突请以当前指令为准：",
    ]
    for idx, hit in enumerate(hits, start=1):
        lines.append(
            f"{idx}. [score={hit['score']:.2f}] query={hit['query']} | summary={hit['summary']}"
        )
    return "\n".join(lines).strip()
