"""交互式运行：支持会话管理和 token 追踪。"""

from __future__ import annotations

import json
import os
import sys
import traceback
import warnings
from typing import Any, Optional, List, Dict
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage, BaseMessage, ToolCall
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt

from agent.reactagent import stream
from utils.path import ensure_task_dirs
from utils.session_manager import get_session_manager
from utils.token_tracker import TokenUsageTracker
from cli.display import (
    print_status,
    print_tool_call,
    print_tool_result,
    print_agent_message,
    print_separator,
    console,
    print_token_usage,
)
from cli.session_ui import show_session_selector
from utils.message_utils import messages_from_session_data
from utils.long_term_memory import append_turn_memory


def run_session_query(
    query: str,
    task_id: str,
    previous_messages: Optional[List[BaseMessage]] = None,
    show_spinner: bool = False
) -> dict[str, Any]:
    """
    在会话中运行查询，支持 token 追踪
    
    Args:
        query: 用户查询
        task_id: 任务 ID
        previous_messages: 之前的消息列表
        
    Returns:
        Agent 的最终状态
    """
    session_manager = get_session_manager()
    token_tracker = TokenUsageTracker()
    last_printed_total_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    
    session_manager.add_message(task_id, "user", query)
    
    final_state = None
    latest_assistant_text = ""
    processed_message_ids = set()
    pending_tool_calls: List[Dict[str, Any]] = []
    
    # 流式显示相关变量
    live_display = None
    current_content = ""
    current_msg_id = None
    is_streaming = False
    
    # 如果显示转圈动效，创建进度条
    progress = None
    if show_spinner:
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True
        )
        progress.start()
        task = progress.add_task("思考中...", total=None)
    
    try:
        # 终端安全模式：默认关闭高频 Markdown Live 重绘，避免部分终端（尤其 Apple Terminal）卡死/崩溃
        raw_live_flag = os.getenv("PRCLAW_LIVE_MARKDOWN", "").strip().lower()
        use_live_markdown = raw_live_flag in {"1", "true", "yes", "on"}

        def _safe_for_console(text: str) -> str:
            """
            将文本降级为当前终端编码可输出的字符串，避免 Windows/GBK 下 Rich 渲染崩溃
            """
            if not text:
                return ""
            # 常见不可编码字符做显式替换（提升可读性）
            text = text.replace("•", "-").replace("👇", "↓")
            encoding = getattr(getattr(console, "file", None), "encoding", None) or "utf-8"
            try:
                return text.encode(encoding, errors="replace").decode(encoding, errors="replace")
            except Exception:
                return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")

        def _print_reply_token_delta(step_name: str = "本次回复") -> None:
            """
            打印「自上次打印以来」新增的 token 使用量

            说明：
            - token_tracker.total_usage 是累计值
            - 这里用 delta 实现“每次回复完成后”打印本轮消耗
            """
            nonlocal last_printed_total_usage
            total = token_tracker.get_total_usage()
            delta_prompt = total["prompt_tokens"] - last_printed_total_usage.get("prompt_tokens", 0)
            delta_completion = total["completion_tokens"] - last_printed_total_usage.get("completion_tokens", 0)
            delta_total = total["total_tokens"] - last_printed_total_usage.get("total_tokens", 0)
            if delta_total <= 0:
                last_printed_total_usage = total
                return

            print_token_usage(step_name, delta_prompt, delta_completion, delta_total)
            session_manager.add_token_usage(task_id, step_name, delta_prompt, delta_completion, delta_total)
            last_printed_total_usage = total

        def _start_stream_output() -> None:
            nonlocal is_streaming
            task_id_display = task_id[:8] if task_id and len(task_id) > 8 else task_id if task_id else ""
            if task_id_display:
                console.print(f"[bold orange1]({task_id_display}) assistant:[/bold orange1]")
            else:
                console.print("[bold orange1]assistant:[/bold orange1]")
            console.print()
            is_streaming = True

        def _render_stream_output(new_content: str) -> None:
            nonlocal current_content, live_display
            if use_live_markdown:
                panel = Panel(
                    Markdown(_safe_for_console(new_content)),
                    border_style="orange1",
                    padding=(1, 2),
                    expand=False,
                )
                if live_display is None:
                    live_display = Live(panel, console=console, refresh_per_second=8)
                    live_display.start()
                else:
                    live_display.update(panel)
                current_content = new_content
                return

            # 安全模式：仅输出增量文本，避免高频 panel redraw
            if new_content.startswith(current_content):
                delta = new_content[len(current_content):]
            else:
                # 内容回退/重算时，直接打印新内容并换行防止视觉重叠
                if current_content:
                    console.print()
                delta = new_content
            if delta:
                console.print(_safe_for_console(delta), end="", markup=False, highlight=False)
            current_content = new_content

        def _stop_stream_output() -> None:
            nonlocal is_streaming, live_display
            if live_display is not None:
                live_display.stop()
                live_display = None
            if is_streaming:
                console.print()
            is_streaming = False

        # 设置当前步骤
        token_tracker.set_step("agent_processing")
        
        has_output = False
        for chunk in stream(query, task_id=task_id, previous_messages=previous_messages, token_tracker=token_tracker):
            
            # 处理 token 级别的流式输出
            if isinstance(chunk, dict) and "type" in chunk:
                chunk_type = chunk.get("type")
                
                # 消息压缩信息
                if chunk_type == "compression":
                    summary = chunk.get("summary", "")
                    original_count = chunk.get("original_count", 0)
                    compressed_count = chunk.get("compressed_count", 0)
                    compressed_messages = chunk.get("compressed_messages", [])
                    
                    console.print()
                    console.print(f"[yellow]对话历史已压缩[/yellow]")
                    if summary:
                        # 截断过长的摘要
                        summary_display = summary[:200] + "..." if len(summary) > 200 else summary
                        console.print(f"[dim]{summary_display}[/dim]")
                    console.print()
                    
                    # 关键修复：将压缩后的消息写回 session，并重置 token_usage
                    if compressed_messages and task_id:
                        session_manager.replace_messages(task_id, compressed_messages, reset_token_usage=True)
                    
                    continue
                
                # Token 级别的流式输出
                if chunk_type == "token":
                    token_content = chunk.get("content", "")
                    accumulated_content = chunk.get("accumulated", "")
                    
                    if token_content:
                        # 如果有转圈动效，先停止
                        if progress and not has_output:
                            progress.stop()
                            has_output = True
                        
                        # 检测是否是新的流式响应开始
                        if not is_streaming:
                            # 开始新的流式响应
                            current_content = ""
                            current_msg_id = chunk.get("message_id", "")
                            _start_stream_output()

                        # 更新流式内容（优先用 accumulated，退化到增量拼接）
                        new_content = accumulated_content or (current_content + token_content)
                        _render_stream_output(new_content)
                        continue
                
                # 完整的消息（流式输出完成）
                elif chunk_type == "message":
                    message = chunk.get("message")
                    if message and isinstance(message, AIMessage):
                        # 关闭流式显示
                        if is_streaming:
                            _stop_stream_output()
                        
                        # 处理消息
                        tool_calls = getattr(message, "tool_calls", None) or []
                        content = str(getattr(message, "content", "")).strip() if hasattr(message, "content") else ""
                        
                        if tool_calls:
                            # 工具调用会在 tool_call 类型中处理，这里只保存消息
                            tool_calls_data = []
                            for tc in tool_calls:
                                if isinstance(tc, dict):
                                    tool_calls_data.append(tc)
                                else:
                                    tool_calls_data.append({
                                        "name": getattr(tc, "name", ""),
                                        "args": getattr(tc, "args", {}),
                                        "id": getattr(tc, "id", "")
                                    })
                            session_manager.add_message(task_id, "assistant", content or "", tool_calls=tool_calls_data)
                            pending_tool_calls = tool_calls_data.copy()
                        elif content:
                            is_tool_result_json = False
                            try:
                                parsed = json.loads(content)
                                # 如果解析成功且是字典，检查是否包含工具返回的典型特征
                                if isinstance(parsed, dict):
                                    tool_result_keywords = [
                                        "result", "error", "path", "file", "save", "output",
                                        "data", "status", "success", "value"
                                    ]
                                    # 检查键名是否包含工具结果关键词
                                    keys = [str(k).lower() for k in parsed.keys()]
                                    has_tool_keywords = any(
                                        keyword in key for key in keys for keyword in tool_result_keywords
                                    )
                                    # 如果包含工具结果关键词，且字段数量较少（通常是工具输出而非复杂文本），则认为是工具结果
                                    if has_tool_keywords and len(parsed) <= 10:
                                        is_tool_result_json = True
                            except (json.JSONDecodeError, TypeError):
                                pass
                            
                            # 如果是工具结果的JSON，跳过保存（工具结果已经通过tool_result类型保存了）
                            if not is_tool_result_json:
                                # 保存最终消息
                                session_manager.add_message(task_id, "assistant", content)
                                latest_assistant_text = content
                                # 每次回复完成后打印 token 消耗（本轮 delta）
                                _print_reply_token_delta("本次回复")
                            current_content = ""
                            current_msg_id = None
                        continue
                
                # 工具调用
                elif chunk_type == "tool_call":
                    tool_name = chunk.get("tool_name", "unknown")
                    tool_args = chunk.get("args", {})
                    
                    if progress and not has_output:
                        progress.stop()
                        has_output = True
                    
                    token_tracker.set_step(f"tool_{tool_name}")
                    print_tool_call(tool_name, tool_args)
                    continue
                
                # 工具结果
                elif chunk_type == "tool_result":
                    tool_name = chunk.get("tool_name", "unknown")
                    tool_result = chunk.get("result", "")
                    
                    # 确保结果是字符串格式
                    if tool_result is None:
                        tool_result = ""
                    elif not isinstance(tool_result, str):
                        # 如果是对象，尝试获取 content 属性
                        if hasattr(tool_result, "content"):
                            tool_result = str(tool_result.content) if tool_result.content else ""
                        else:
                            tool_result = str(tool_result)
                    
                    print_tool_result(tool_name, tool_result)
                    
                    # 打印 token 使用情况（工具执行完成后）
                    step_usage = token_tracker.get_step_usage(token_tracker.current_step or "unknown")
                    if step_usage["total_tokens"] > 0:
                        print_token_usage(
                            token_tracker.current_step or "unknown",
                            step_usage["prompt_tokens"],
                            step_usage["completion_tokens"],
                            step_usage["total_tokens"]
                        )
                        session_manager.add_token_usage(
                            task_id,
                            token_tracker.current_step or "unknown",
                            step_usage["prompt_tokens"],
                            step_usage["completion_tokens"],
                            step_usage["total_tokens"]
                        )
                        token_tracker.step_token_usage[token_tracker.current_step or "unknown"] = {
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "total_tokens": 0
                        }
                    
                    # 保存工具结果到会话
                    run_id = chunk.get("run_id", "")
                    session_manager.add_message(
                        task_id,
                        "tool",
                        str(tool_result),
                        tool_name=tool_name,
                        tool_call_id=run_id
                    )
                    continue
                
                # 状态更新（兼容旧格式）
                elif chunk_type == "state_update":
                    state = chunk.get("state", {})
                    if isinstance(state, dict):
                        for node_name, state_update in state.items():
                            if isinstance(state_update, dict):
                                messages = state_update.get("messages", [])
                            else:
                                continue
                            
                            for msg in messages:
                                msg_id = getattr(msg, "id", None)
                                if not msg_id:
                                    content = str(getattr(msg, "content", ""))
                                    msg_type = type(msg).__name__
                                    if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                                        tool_names = [str(tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")) for tc in msg.tool_calls]
                                        msg_id = f"{msg_type}:{hash((content, tuple(tool_names)))}"
                                    else:
                                        # 对于流式内容，使用消息类型和内容前缀作为临时 ID
                                        content_prefix = content[:50] if len(content) > 50 else content
                                        msg_id = f"{msg_type}:{hash(content_prefix)}"
                                
                                # 对于流式 AIMessage，如果正在流式输出且是同一个消息的更新，允许处理
                                is_streaming_update = False
                                if isinstance(msg, AIMessage) and is_streaming and current_msg_id:
                                    content_str = str(getattr(msg, "content", "")).strip()
                                    # 检查是否是同一个消息的增量更新（新内容包含旧内容，或长度更长）
                                    if content_str and current_content:
                                        if content_str.startswith(current_content) or len(content_str) > len(current_content):
                                            is_streaming_update = True
                                            msg_id = current_msg_id  # 使用当前消息 ID
                                
                                # 如果不是流式更新，且消息已处理过，则跳过
                                if not is_streaming_update and msg_id in processed_message_ids:
                                    continue
                                
                                # 如果不是流式更新，标记消息为已处理
                                if not is_streaming_update:
                                    processed_message_ids.add(msg_id)
                                
                                if isinstance(msg, AIMessage):
                                    tool_calls = getattr(msg, "tool_calls", None) or []
                                    content = str(getattr(msg, "content", "")).strip() if hasattr(msg, "content") else ""
                                    
                                    if tool_calls:
                                        # 如果有流式显示，先关闭它
                                        if is_streaming:
                                            _stop_stream_output()
                                            # 保存流式内容（如果有）
                                            if current_content:
                                                session_manager.add_message(task_id, "assistant", current_content)
                                                latest_assistant_text = current_content
                                            current_content = ""
                                            current_msg_id = None
                                        
                                        if progress and not has_output:
                                            progress.stop()
                                            has_output = True
                                        
                                        for tc in tool_calls:
                                            if isinstance(tc, dict):
                                                tool_name = tc.get("name", "unknown")
                                                tool_args = tc.get("args", {})
                                            else:
                                                tool_name = getattr(tc, "name", "unknown")
                                                tool_args = getattr(tc, "args", {})
                                            
                                            token_tracker.set_step(f"tool_{tool_name}")
                                            print_tool_call(tool_name, tool_args)
                                        
                                        tool_calls_data = []
                                        for tc in tool_calls:
                                            if isinstance(tc, dict):
                                                tool_calls_data.append(tc)
                                            else:
                                                tool_calls_data.append({
                                                    "name": getattr(tc, "name", ""),
                                                    "args": getattr(tc, "args", {}),
                                                    "id": getattr(tc, "id", "")
                                                })
                                        session_manager.add_message(task_id, "assistant", content or "", tool_calls=tool_calls_data)
                                        pending_tool_calls = tool_calls_data.copy()
                                
                                elif isinstance(msg, AIMessage) and content:
                                    # 检查是否是工具结果的中间表示（JSON格式的内容，且没有tool_calls）
                                    content_str = str(msg.content).strip()
                                    is_tool_result_json = False
                                    if content_str:
                                        # 检查是否是JSON格式（工具返回的结果）
                                        try:
                                            parsed = json.loads(content_str)
                                            # 如果解析成功且是字典，检查是否包含工具返回的典型特征
                                            if isinstance(parsed, dict):
                                                # 工具结果JSON的典型特征：
                                                # 1. 包含常见的工具结果关键词（result, error, path, file, save, output等）
                                                # 2. 结构相对简单（字段数量较少，通常是工具的输出结构）
                                                tool_result_keywords = [
                                                    "result", "error", "path", "file", "save", "output",
                                                    "data", "status", "success", "value"
                                                ]
                                                # 检查键名是否包含工具结果关键词
                                                keys = [str(k).lower() for k in parsed.keys()]
                                                has_tool_keywords = any(
                                                    keyword in key for key in keys for keyword in tool_result_keywords
                                                )
                                                # 如果包含工具结果关键词，且字段数量较少（通常是工具输出而非复杂文本），则认为是工具结果
                                                if has_tool_keywords and len(parsed) <= 10:
                                                    is_tool_result_json = True
                                        except (json.JSONDecodeError, TypeError):
                                            pass
                                    
                                    # 如果是工具结果的JSON，跳过保存（工具结果已经通过tool_result类型保存了）
                                    if is_tool_result_json:
                                        continue
                                    
                                    # 否则正常处理
                                    if content_str:
                                        # 如果有转圈动效，先停止
                                        if progress and not has_output:
                                            progress.stop()
                                            has_output = True
                                        
                                        # 检测是否是新的流式响应开始
                                        if not is_streaming:
                                            # 开始新的流式响应
                                            current_content = ""
                                            current_msg_id = msg_id
                                            _start_stream_output()

                                        # 更新流式内容（检查是否是同一个消息的增量更新）
                                        if content_str.startswith(current_content) or len(content_str) > len(current_content):
                                            _render_stream_output(content_str)
                                        
                                        # 检查是否有 tool_calls（如果有，说明消息完整）
                                        tool_calls_data = None
                                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                                            tool_calls_data = []
                                            for tc in msg.tool_calls:
                                                if isinstance(tc, dict):
                                                    tool_calls_data.append(tc)
                                                else:
                                                    tool_calls_data.append({
                                                        "name": getattr(tc, "name", ""),
                                                        "args": getattr(tc, "args", {}),
                                                        "id": getattr(tc, "id", "")
                                                    })
                                        
                                        # 注意：这里不立即保存消息，等流式输出完成后再保存
                                
                                # 处理工具执行结果
                                elif isinstance(msg, ToolMessage):
                                    tool_name = getattr(msg, "name", "unknown")
                                    tool_call_id = getattr(msg, "tool_call_id", "")
                                    content = getattr(msg, "content", "")
                                    if content:
                                        print_tool_result(tool_name, content)
                                    session_manager.add_message(
                                        task_id, 
                                        "tool", 
                                        content, 
                                        tool_name=tool_name,
                                        tool_call_id=tool_call_id
                                    )
                                    pending_tool_calls = [
                                        tc for tc in pending_tool_calls 
                                        if tc.get("id") != tool_call_id
                                    ]
                            
                            step_usage = token_tracker.get_step_usage(token_tracker.current_step or "unknown")
                            if step_usage["total_tokens"] > 0:
                                print_token_usage(
                                    token_tracker.current_step or "unknown",
                                    step_usage["prompt_tokens"],
                                    step_usage["completion_tokens"],
                                    step_usage["total_tokens"]
                                )
                                session_manager.add_token_usage(
                                    task_id,
                                    token_tracker.current_step or "unknown",
                                    step_usage["prompt_tokens"],
                                    step_usage["completion_tokens"],
                                    step_usage["total_tokens"]
                                )
                                token_tracker.step_token_usage[token_tracker.current_step or "unknown"] = {
                                    "prompt_tokens": 0,
                                    "completion_tokens": 0,
                                    "total_tokens": 0
                                }
                    
                    if final_state is None:
                        final_state = {}
                    final_state.update(chunk)
        
        # 流式输出完成，关闭 Live 显示并保存消息
        if is_streaming:
            _stop_stream_output()
            
            # 保存最终消息
            tool_calls_data = None
            # 从 final_state 中查找对应的 AIMessage 来获取 tool_calls
            if final_state:
                for node_name, state_update in final_state.items():
                    if isinstance(state_update, dict):
                        messages = state_update.get("messages", [])
                        for msg in messages:
                            if isinstance(msg, AIMessage):
                                msg_content = str(msg.content).strip()
                                # 匹配当前内容（允许内容完全匹配或当前内容是消息内容的前缀）
                                if msg_content == current_content or (current_content and msg_content.startswith(current_content)):
                                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                                        tool_calls_data = []
                                        for tc in msg.tool_calls:
                                            if isinstance(tc, dict):
                                                tool_calls_data.append(tc)
                                            else:
                                                tool_calls_data.append({
                                                    "name": getattr(tc, "name", ""),
                                                    "args": getattr(tc, "args", {}),
                                                    "id": getattr(tc, "id", "")
                                                })
                                    # 使用最终的消息内容（可能比 current_content 更完整）
                                    if msg_content != current_content:
                                        current_content = msg_content
                                    break
            
            if current_content:
                session_manager.add_message(task_id, "assistant", current_content, tool_calls=tool_calls_data)
                latest_assistant_text = current_content
                # 每次回复完成后打印 token 消耗（本轮 delta）
                _print_reply_token_delta("本次回复")
            
            current_content = ""
            current_msg_id = None
        
        if progress and not has_output:
            progress.stop()
        
    except KeyboardInterrupt:
        if progress:
            progress.stop()
        # 关闭流式显示
        if is_streaming:
            _stop_stream_output()
            # 保存已生成的内容
            if current_content:
                session_manager.add_message(task_id, "assistant", current_content)
                latest_assistant_text = current_content
        print_status("用户中断了执行", "warning")
        for tc in pending_tool_calls:
            tool_call_id = tc.get("id", "")
            tool_name = tc.get("name", "unknown")
            if tool_call_id:
                session_manager.add_message(
                    task_id,
                    "tool",
                    "",  # content为空
                    tool_name=tool_name,
                    tool_call_id=tool_call_id
                )
        raise
    except Exception as e:
        if progress:
            progress.stop()
        # 关闭流式显示
        if is_streaming:
            _stop_stream_output()
            # 保存已生成的内容
            if current_content:
                session_manager.add_message(task_id, "assistant", current_content)
                latest_assistant_text = current_content
        print_status(f"执行出错: {str(e)}", "error")
        
        for tc in pending_tool_calls:
            tool_call_id = tc.get("id", "")
            tool_name = tc.get("name", "unknown")
            if tool_call_id:
                session_manager.add_message(
                    task_id,
                    "tool",
                    "",  # content为空
                    tool_name=tool_name,
                    tool_call_id=tool_call_id
                )
        traceback.print_exc()
        raise
    
    # 确保每次回复结束后至少打印一次 token
    _print_reply_token_delta("本次回复")

    # 打印总 token 使用（每次回复完成后都显示）
    total_usage = token_tracker.get_total_usage()
    # 若已在“本次回复”处打印过 delta，则此处避免重复打印同样的总计
    if total_usage["total_tokens"] > 0 and total_usage != last_printed_total_usage:
        print_separator()
        print_token_usage(
            "总计",
            total_usage["prompt_tokens"],
            total_usage["completion_tokens"],
            total_usage["total_tokens"]
        )
    
    if not show_spinner:
        print_separator()
        print_status("处理完成", "success")

    # 写入长期记忆（轻量 LTM）
    if latest_assistant_text.strip():
        append_turn_memory(task_id=task_id, query=query, response=latest_assistant_text)
    
    return final_state or {}


def run_session_loop(task_id: Optional[str] = None) -> None:
    """
    运行会话循环
    
    Args:
        task_id: 任务 ID，如果为 None 则创建新会话
    """
    session_manager = get_session_manager()
    previous_messages = []
    
    # 如果没有提供 task_id，创建新会话
    if task_id is None:
        # 先创建会话，获取任务ID（使用临时查询）
        task_id = session_manager.create_session("新会话")
        ensure_task_dirs(task_id)
        print_status(f"会话已创建，任务 ID: {task_id}", "info")
        
        # 直接显示 user 输入提示（带任务ID格式）
        task_id_display = task_id[:8] if task_id and len(task_id) > 8 else task_id if task_id else ""
        # 在 user 提示前添加绿色横线作为对话区隔
        console.print("[green]────────────────────────────────────────────────────────────[/green]")
        initial_query = Prompt.ask(f"[bold cyan]({task_id_display}) user[/bold cyan]")
        if not initial_query:
            console.print("[yellow]未输入查询，退出。[/yellow]")
            return
        
        # 更新会话的初始查询
        session_data = session_manager.load_session(task_id)
        if session_data:
            session_data["initial_query"] = initial_query
            # 关键修复：必须立即保存，否则会话列表/恢复时仍显示 create_session("新会话") 的占位描述
            session_manager.save_session(task_id, session_data, final_query=initial_query)
        
        # 立即执行初始查询（带转圈动效）
        try:
            run_session_query(initial_query, task_id, previous_messages, show_spinner=True)
            # 执行完后更新 previous_messages
            session_data = session_manager.load_session(task_id)
            if session_data:
                previous_messages = messages_from_session_data(session_data)
        except Exception as e:
            console.print()  # 换行
            console.print(f"\n[red]执行初始查询失败: {str(e)}[/red]\n")
            traceback.print_exc()
    else:
        # 加载会话
        session_data = session_manager.load_session(task_id)
        if not session_data:
            console.print(f"[red]无法加载会话: {task_id}[/red]")
            return
        
        ensure_task_dirs(task_id)
        print_status(f"已恢复会话: {task_id}", "info")
        print_status(f"描述: {session_data.get('description', 'N/A')}", "info")
        
        # 恢复消息
        previous_messages = messages_from_session_data(session_data)
    
    # 会话循环（等待后续查询）
    while True:
        try:
            # 在agent运行时也显示user:提示，便于输入/exit等
            task_id_display = task_id[:8] if task_id and len(task_id) > 8 else task_id if task_id else ""
            # 在 user 提示前添加绿色横线作为对话区隔
            console.print("[green]────────────────────────────────────────────────────────────[/green]")
            user_input = Prompt.ask(f"[bold cyan]({task_id_display}) user[/bold cyan]")
            
            if not user_input:
                continue
            
            # 处理系统级命令（以 / 开头）
            if user_input.strip().startswith("/"):
                # 处理 /exit 命令（退出到主页面）
                if user_input.strip() == "/exit":
                    # 保存会话
                    session_data = session_manager.load_session(task_id)
                    if session_data:
                        session_manager.save_session(task_id, session_data)
                    # 显示任务目录信息（只在退出时显示）
                    print_status(f"任务目录: sandbox/{task_id}/", "info")
                    console.print(f"\n[cyan]会话已保存，已退出到主页面[/cyan]\n")
                    return  # 返回到主页面
                
                # 其他系统命令在main.py中处理，这里只处理/exit
                console.print(f"[yellow]在会话中，只能使用 /exit 退出会话[/yellow]")
                continue
            
            run_session_query(user_input, task_id, previous_messages, show_spinner=True)
            
            # 更新 previous_messages（查询完成后重新加载会话以获取最新消息）
            session_data = session_manager.load_session(task_id)
            if session_data:
                previous_messages = messages_from_session_data(session_data)
            
        except KeyboardInterrupt:
            # 保存会话
            session_data = session_manager.load_session(task_id)
            if session_data:
                session_manager.save_session(task_id, session_data)
            console.print(f"\n\n[cyan]会话已保存，感谢使用 [bold magenta]PRClaw[/bold magenta]！[/cyan]\n")
            sys.exit(0)
        except EOFError:
            session_data = session_manager.load_session(task_id)
            if session_data:
                session_manager.save_session(task_id, session_data)
            console.print(f"\n\n[cyan]会话已保存，感谢使用 [bold magenta]PRClaw[/bold magenta]！[/cyan]\n")
            sys.exit(0)
        except Exception as e:
            console.print(f"\n[red]发生错误: {str(e)}[/red]\n")
            traceback.print_exc()
