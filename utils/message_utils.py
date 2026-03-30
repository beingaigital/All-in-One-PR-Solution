"""消息工具：用于消息格式转换、会话数据恢复和消息压缩。"""

from __future__ import annotations

import json
import warnings
from typing import Any, List, Tuple, Optional
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage, BaseMessage, ToolCall, SystemMessage
from model.factory import get_text_generation_model


def messages_from_session_data(session_data: dict) -> List[BaseMessage]:
    """
    从会话数据中恢复消息列表

    兼容 LangChain 1.0 的消息与工具调用格式：
    - AIMessage.tool_calls 使用 ToolCall 对象列表
    - ToolMessage 只依赖 tool_call_id，不需要 name 参数
    """
    messages: List[BaseMessage] = []

    for i, msg_data in enumerate(session_data.get("messages", [])):
        role = msg_data.get("role", "")
        content = msg_data.get("content", "") or ""

        if role == "user":
            msg = HumanMessage(content=content)
            messages.append(msg)

        elif role == "assistant":
            raw_tool_calls = msg_data.get("tool_calls", [])
            if raw_tool_calls is None:
                raw_tool_calls = []
            elif not isinstance(raw_tool_calls, list):
                warnings.warn(f"tool_calls 不是列表格式: {type(raw_tool_calls)}, 设为空列表")
                raw_tool_calls = []
            
            formatted_tool_calls: List[ToolCall] = []
            
            if raw_tool_calls:
                for tc_idx, tc in enumerate(raw_tool_calls):
                    if isinstance(tc, dict):
                        tc_name = tc.get("name") or tc.get("function", {}).get("name") or "unknown"
                        tc_args = tc.get("args") or tc.get("function", {}).get("arguments") or {}
                        if isinstance(tc_args, str):
                            try:
                                tc_args = json.loads(tc_args)
                            except (json.JSONDecodeError, TypeError):
                                tc_args = {}
                        tc_id = tc.get("id") or tc.get("tool_call_id") or tc.get("call_id") or ""
                        
                        if not tc_id:
                            tc_id = f"call_{i}_{tc_idx}_{hash(str(tc))}"
                            warnings.warn(f"tool_call 缺少 id，生成临时 id: {tc_id}")

                        extra_kwargs: dict[str, Any] = {}
                        if "type" in tc:
                            extra_kwargs["type"] = tc["type"]

                        tool_call = ToolCall(
                            name=tc_name,
                            args=tc_args if isinstance(tc_args, dict) else {},
                            id=tc_id,
                            **extra_kwargs,
                        )
                        formatted_tool_calls.append(tool_call)
                    elif isinstance(tc, str):
                        warnings.warn(f"tool_call 是字符串格式（可能是旧数据），跳过: {tc}")
                    else:
                        formatted_tool_calls.append(tc)
            
            if formatted_tool_calls is None:
                formatted_tool_calls = []
            elif not isinstance(formatted_tool_calls, list):
                warnings.warn(f"formatted_tool_calls 不是列表格式: {type(formatted_tool_calls)}, 设为空列表")
                formatted_tool_calls = []
            
            try:
                if formatted_tool_calls:
                    ai_msg = AIMessage(content=content, tool_calls=formatted_tool_calls)
                else:
                    ai_msg = AIMessage(content=content)
            except Exception as e:
                try:
                    ai_msg = AIMessage(content=content)
                except Exception:
                    raise

            messages.append(ai_msg)

        elif role == "tool":
            tool_call_id = msg_data.get("tool_call_id", "") or ""
            tool_name = msg_data.get("tool_name") or "unknown_tool"

            if not tool_call_id:
                tool_call_id = f"restored_{tool_name}_{i}"
                warnings.warn(f"ToolMessage 缺少 tool_call_id，使用生成的 id: {tool_call_id}")

            tool_msg = ToolMessage(
                content=content,
                tool_call_id=tool_call_id,
                name=tool_name
            )
            messages.append(tool_msg)

    # 顺序校验：ToolMessage 必须紧跟带 tool_calls 的 AIMessage
    validated_messages: List[BaseMessage] = []
    
    for i, msg in enumerate(messages):
        if isinstance(msg, ToolMessage):
            if i == 0 or not validated_messages:
                warnings.warn("ToolMessage 在消息列表开头，跳过该消息")
                continue

            prev_msg = validated_messages[-1]
            if not isinstance(prev_msg, AIMessage) or not getattr(prev_msg, "tool_calls", None):
                continue

            prev_tool_call_ids = set()
            for tc in prev_msg.tool_calls:
                if isinstance(tc, dict):
                    tc_id = tc.get("id") or tc.get("tool_call_id") or tc.get("call_id")
                else:
                    tc_id = getattr(tc, "id", None)
                if tc_id:
                    prev_tool_call_ids.add(tc_id)
            
            if msg.tool_call_id not in prev_tool_call_ids:
                continue

        validated_messages.append(msg)

    # 清理：移除没有对应 ToolMessage 的 tool_calls
    final_messages: List[BaseMessage] = []
    
    for i, msg in enumerate(validated_messages):
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            next_tool_call_ids: set[str] = set()
            for next_msg in validated_messages[i + 1 :]:
                if isinstance(next_msg, ToolMessage):
                    next_tool_call_ids.add(next_msg.tool_call_id)
                elif isinstance(next_msg, (AIMessage, HumanMessage)):
                    break
            
            valid_tool_calls = []
            for tc in msg.tool_calls:
                if isinstance(tc, dict):
                    tc_id = tc.get("id") or tc.get("tool_call_id") or tc.get("call_id")
                else:
                    tc_id = getattr(tc, "id", None)
                if tc_id in next_tool_call_ids:
                    valid_tool_calls.append(tc)
            
            if len(valid_tool_calls) != len(msg.tool_calls):
                msg.tool_calls = valid_tool_calls

        final_messages.append(msg)

    return final_messages


def compress_messages(
    messages: List[BaseMessage], 
    max_completion_tokens: Optional[int] = None,
    current_completion_tokens: int = 0
) -> Tuple[List[BaseMessage], bool, str]:
    """
    压缩消息列表：当 completion_tokens 累计超过限制时，将旧消息压缩为摘要
    
    Args:
        messages: 消息列表
        max_completion_tokens: 最大 completion_tokens 累计值，如果为 None 则不压缩
        current_completion_tokens: 当前的 completion_tokens 累计值
        
    Returns:
        Tuple[压缩后的消息列表, 是否进行了压缩, 压缩摘要文本]
    """
    if not messages:
        return messages, False, ""
    
    # 如果没有设置 max_completion_tokens 或未超过限制，直接返回
    if max_completion_tokens is None or current_completion_tokens <= max_completion_tokens:
        return messages, False, ""
    
    # 保留系统消息和最近的 N 条消息
    system_messages = [msg for msg in messages if isinstance(msg, SystemMessage)]
    other_messages = [msg for msg in messages if not isinstance(msg, SystemMessage)]
    
    # 保留最近的 10 条消息（约 5 轮对话）
    recent_count = 10
    recent_messages = other_messages[-recent_count:] if len(other_messages) > recent_count else other_messages
    
    # 如果需要压缩，将旧消息压缩为摘要
    if len(other_messages) > recent_count:
        old_messages = other_messages[:-recent_count]
        if old_messages:
            # 使用文本生成模型生成摘要
            try:
                summary_llm = get_text_generation_model()
                
                # 构建摘要 prompt
                old_content_parts = []
                for msg in old_messages:
                    if hasattr(msg, "content") and msg.content:
                        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
                        content = str(msg.content)
                        # 截断过长的消息
                        if len(content) > 500:
                            content = content[:500] + "..."
                        old_content_parts.append(f"{role}: {content}")
                
                if old_content_parts:
                    old_content = "\n".join(old_content_parts)
                    
                    summary_prompt = f"""请将以下对话历史压缩为简洁的摘要（100-200字），保留关键信息和上下文：{old_content}，一定要注意保留好所有工具调用的结果，摘要："""
                    
                    summary_response = summary_llm.invoke([HumanMessage(content=summary_prompt)])
                    summary_text = getattr(summary_response, "content", "") or str(summary_response)
                    
                    # 创建摘要消息
                    summary_msg = AIMessage(content=f"[历史对话摘要] {summary_text}")
                    
                    # 返回：系统消息 + 摘要 + 最近消息
                    compressed_messages = system_messages + [summary_msg] + recent_messages
                    return compressed_messages, True, summary_text
            except Exception as e:
                # 如果摘要失败，只保留最近消息（记录警告但不中断流程）
                warnings.warn(f"消息压缩失败，仅保留最近消息: {e}")
                return system_messages + recent_messages, True, f"压缩失败，已移除 {len(old_messages)} 条旧消息"
    
    return system_messages + recent_messages, False, ""
