"""外部信息检索工具（Serper + DuckDuckGo fallback）。"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import requests

from utils.prclaw_config import get_prclaw_config


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _search_serper(query: str, max_results: int, timeout_seconds: int) -> List[Dict[str, str]]:
    api_key = os.getenv("SERPER_API_KEY") or os.getenv("GOOGLE_SERPER_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 SERPER_API_KEY")

    resp = requests.post(
        "https://google.serper.dev/search",
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        },
        json={
            "q": query,
            "num": max_results,
            "gl": "cn",
            "hl": "zh-cn",
        },
        timeout=timeout_seconds,
    )
    resp.raise_for_status()
    data = resp.json() if resp.content else {}

    output: List[Dict[str, str]] = []
    for item in (data.get("organic") or [])[:max_results]:
        output.append(
            {
                "title": str(item.get("title", "")).strip(),
                "url": str(item.get("link", "")).strip(),
                "snippet": str(item.get("snippet", "")).strip(),
                "source": "serper",
            }
        )
    return output


def _extract_ddg_related(related_topics: List[Dict[str, Any]], max_results: int) -> List[Dict[str, str]]:
    output: List[Dict[str, str]] = []

    def _append_item(text: str, first_url: str) -> None:
        if len(output) >= max_results:
            return
        output.append(
            {
                "title": text[:80],
                "url": first_url,
                "snippet": text,
                "source": "duckduckgo",
            }
        )

    for item in related_topics:
        if len(output) >= max_results:
            break

        if isinstance(item.get("Topics"), list):
            for child in item["Topics"]:
                text = str(child.get("Text", "")).strip()
                url = str(child.get("FirstURL", "")).strip()
                if text:
                    _append_item(text, url)
                if len(output) >= max_results:
                    break
            continue

        text = str(item.get("Text", "")).strip()
        url = str(item.get("FirstURL", "")).strip()
        if text:
            _append_item(text, url)

    return output


def _search_duckduckgo(query: str, max_results: int, timeout_seconds: int) -> List[Dict[str, str]]:
    resp = requests.get(
        "https://api.duckduckgo.com/",
        params={
            "q": query,
            "format": "json",
            "no_redirect": 1,
            "skip_disambig": 1,
            "no_html": 1,
        },
        timeout=timeout_seconds,
    )
    resp.raise_for_status()
    data = resp.json() if resp.content else {}

    output: List[Dict[str, str]] = []

    abstract = str(data.get("AbstractText", "")).strip()
    abstract_url = str(data.get("AbstractURL", "")).strip()
    heading = str(data.get("Heading", "")).strip() or query
    if abstract:
        output.append(
            {
                "title": heading,
                "url": abstract_url,
                "snippet": abstract,
                "source": "duckduckgo",
            }
        )

    if len(output) < max_results:
        remain = max_results - len(output)
        output.extend(_extract_ddg_related(data.get("RelatedTopics") or [], remain))

    return output[:max_results]


def search_web(
    query: str,
    provider: str | None = None,
    max_results: int | None = None,
    timeout_seconds: int | None = None,
) -> Dict[str, Any]:
    """检索外部公开信息，返回标准化结果。"""
    cfg = get_prclaw_config()
    web_cfg = cfg.web_search

    final_provider = (provider or web_cfg.provider or "auto").strip().lower()
    final_max_results = max(1, _safe_int(max_results, web_cfg.max_results))
    final_timeout = max(3, _safe_int(timeout_seconds, web_cfg.timeout_seconds))

    if not query.strip():
        return {
            "provider": final_provider,
            "results": [],
            "error": "query 为空",
        }

    tried: List[str] = []
    errors: List[str] = []

    def _try_one(name: str):
        tried.append(name)
        if name == "serper":
            return _search_serper(query, final_max_results, final_timeout)
        if name == "duckduckgo":
            return _search_duckduckgo(query, final_max_results, final_timeout)
        raise ValueError(f"不支持的 provider: {name}")

    providers: List[str]
    if final_provider == "auto":
        providers = ["serper", "duckduckgo"]
    else:
        providers = [final_provider]

    for name in providers:
        try:
            results = _try_one(name)
            return {
                "provider": name,
                "results": results,
                "error": "",
                "tried": tried,
            }
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    return {
        "provider": final_provider,
        "results": [],
        "error": " | ".join(errors) if errors else "未知错误",
        "tried": tried,
    }


def format_web_context(search_payload: Dict[str, Any], max_chars: int = 2600) -> str:
    """将外部检索结果压缩成 prompt 片段。"""
    rows = search_payload.get("results") if isinstance(search_payload, dict) else None
    if not isinstance(rows, list) or not rows:
        return ""

    lines = ["外部公开信息（请注意时效性并交叉验证）:"]
    for idx, item in enumerate(rows, start=1):
        title = str(item.get("title", "")).strip()
        snippet = str(item.get("snippet", "")).strip()
        url = str(item.get("url", "")).strip()
        if not title and not snippet:
            continue
        lines.append(f"{idx}. {title}")
        if snippet:
            lines.append(f"   - 摘要: {snippet}")
        if url:
            lines.append(f"   - 来源: {url}")

    text = "\n".join(lines).strip()
    if len(text) > max_chars:
        return text[: max_chars - 32].rstrip() + "\n...（外部信息已截断）"
    return text
