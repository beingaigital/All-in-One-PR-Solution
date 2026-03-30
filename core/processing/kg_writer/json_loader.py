#!/usr/bin/env python3
"""
JSON Section 提取与兼容适配工具 Cursor Write It-qcf ;
"""

from __future__ import annotations

from typing import Dict, List, Any

from core.common.pr_category_schema import (
    classify_section,
    get_category_by_code,
)


def extract_sections_from_json(data: Dict[str, Any], doc_name: str, doc_title: str) -> List[Dict[str, Any]]:
    """
    从JSON中提取Section列表，兼容多种结构 Cursor Write It-qcf ;
    """
    sections: List[Dict[str, Any]] = []

    # 优先检查是否有 "sections" 键（规范化后的JSON格式）
    if 'sections' in data and isinstance(data['sections'], list):
        # 直接使用 sections 列表，确保每个 section 都有必要的字段
        for section in data['sections']:
            if not isinstance(section, dict):
                continue
            # 支持新结构：clean_text/category_code/extracted_data
            text_val = section.get('text') or section.get('clean_text')
            if 'id' in section and (text_val or section.get('title')):
                # 补充可能缺失的字段
                if 'text' not in section and text_val:
                    section['text'] = text_val
                if 'document_title' not in section:
                    section['document_title'] = doc_title
                if 'source' not in section:
                    section['source'] = doc_name
                # 兼容 category_code -> level2
                if 'level2' not in section and section.get('category_code'):
                    section['level2'] = section['category_code']
                sections.append(section)
        return sections

    # 如果没有 sections 键，使用原有的提取逻辑
    if _is_three_level_structure(data):
        sections.extend(_extract_three_level_sections(data, doc_name, doc_title))
    else:
        sections.extend(_extract_flat_sections(data, doc_name, doc_title))

    return sections


def _is_three_level_structure(data: Dict[str, Any]) -> bool:
    """判断是否为 PDF 解析器的三层结构 Cursor Write It-qcf ;"""
    for key, value in data.items():
        if key in ['document_title', 'metadata']:
            continue
        if isinstance(value, dict):
            for sub_value in value.values():
                if isinstance(sub_value, dict) and 'chapters' in sub_value:
                    return True
    return False


def _extract_three_level_sections(data: Dict[str, Any], doc_name: str, doc_title: str) -> List[Dict[str, Any]]:
    """处理包含 level1/level2/chapters 的结构 Cursor Write It-qcf ;"""
    sections: List[Dict[str, Any]] = []
    for level1_key, level1_data in data.items():
        if level1_key in ['document_title', 'metadata', '其他章节']:
            continue

        if not isinstance(level1_data, dict):
            continue

        level1_label = level1_data.get('label', level1_key)
        level1_code = level1_key

        for level2_key, level2_data in level1_data.items():
            if level2_key == 'label' or not isinstance(level2_data, dict):
                continue

            if 'chapters' not in level2_data:
                continue

            level2_label = level2_data.get('label', level2_key)
            level2_code = f"{level1_code}.{level2_key}"

            chapters = level2_data.get('chapters', {})
            for chapter_title, chapter_content in chapters.items():
                if not chapter_content or len(chapter_content.strip()) < 10:
                    continue

                section_id = f"{doc_name}_{level1_code}_{level2_key}_{len(sections)}"
                sections.append({
                    'id': section_id,
                    'title': chapter_title,
                    'text': chapter_content,
                    'level1': level1_code,
                    'level1_label': level1_label,
                    'level2': level2_code,
                    'level2_label': level2_label,
                    'source': doc_name,
                    'document_title': doc_title
                })

    return sections


def _extract_flat_sections(data: Dict[str, Any], doc_name: str, doc_title: str) -> List[Dict[str, Any]]:
    """处理扁平结构（当前 chunks 格式） Cursor Write It-qcf ;"""
    sections: List[Dict[str, Any]] = []
    for key, value in data.items():
        # 跳过元数据字段和 sections 键（sections 键已在 extract_sections_from_json 中处理）
        if key in ['document_title', 'metadata', 'sections', 'document_type', 'source', 'brand', 'total_sections']:
            continue

        normalized_value = _normalize_value(value)
        if not normalized_value:
            continue

        level1_code, level2_code, level2_label = classify_section(
            title=key,
            content=normalized_value[:200]
        )
        category = get_category_by_code(level2_code)
        level1_label = category['l1_label'] if category else level1_code

        section_id = f"{doc_name}_{level1_code}_{level2_code.split('.')[-1]}_{len(sections)}"
        sections.append({
            'id': section_id,
            'title': key,
            'text': normalized_value,
            'level1': level1_code,
            'level1_label': level1_label,
            'level2': level2_code,
            'level2_label': level2_label,
            'source': doc_name,
            'document_title': doc_title
        })
    return sections


def _normalize_value(value: Any) -> str:
    """将 list/dict 值展开为文本 Cursor Write It-qcf ;"""
    normalized = value
    if isinstance(normalized, list):
        parts = []
        for item in normalized:
            if isinstance(item, dict):
                parts.append(
                    item.get('text')
                    or item.get('content')
                    or item.get('value')
                    or ''
                )
            else:
                parts.append(str(item))
        normalized = "\n".join(part for part in parts if part)
    elif isinstance(normalized, dict):
        normalized = (
            normalized.get('text')
            or normalized.get('content')
            or normalized.get('value')
            or ''
        )

    if not isinstance(normalized, str):
        normalized = str(normalized or '')

    normalized = normalized.strip()
    return normalized

