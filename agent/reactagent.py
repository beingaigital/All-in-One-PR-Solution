"""ReAct Agent：将实例化的LLM封装为Agent"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage, ToolMessage
from typing import Optional, List, Dict, Any
import asyncio
import queue
import threading
from datetime import datetime

try:
    # LangChain 新版本接口
    from langchain.agents import create_agent
except ImportError:
    # 兼容旧版本：用 create_tool_calling_agent + AgentExecutor 组合出等价能力
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

    def create_agent(*, model, tools, system_prompt):
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                MessagesPlaceholder(variable_name="messages"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )
        runnable_agent = create_tool_calling_agent(model, tools, prompt)
        return AgentExecutor(agent=runnable_agent, tools=tools)

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from model.factory import get_react_model
from utils.message_utils import messages_from_session_data
from utils.prompt_loader import get_system_prompt_with_tools
from utils.long_term_memory import format_relevant_memories_for_prompt
from utils.skill_registry import format_active_skills_for_prompt
from utils.tool_registry import load_agent_tools
from utils.task_context import set_task_id, get_task_id
from utils.token_tracker import TokenUsageTracker
from utils.message_utils import compress_messages
from utils.session_manager import get_session_manager
import warnings

# 当前注册的工具列表（来自动态注册中心）
AGENT_TOOLS = load_agent_tools()
if not AGENT_TOOLS:
    warnings.warn("未发现可用工具。请检查 config/tools.yaml 或 tools 目录下的工具实现。")

# Callback 处理器：在工具执行时设置任务ID上下文
class TaskContextCallback(BaseCallbackHandler):
    """Callback 处理器：在工具执行时设置任务ID上下文"""
    
    def __init__(self, task_id: str | None = None):
        super().__init__()
        self.task_id = task_id
    
    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: str,
        parent_run_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """工具开始执行时设置任务ID上下文"""
        if self.task_id:
            set_task_id(self.task_id)
        return super().on_tool_start(
            serialized, input_str, run_id=run_id, parent_run_id=parent_run_id, tags=tags, metadata=metadata, **kwargs
        )

# 消息记忆实现
class SessionChatMessageHistory(BaseChatMessageHistory):
    """基于 SessionManager 的聊天消息历史实现"""
    
    def __init__(self, task_id: str):
        super().__init__()
        self.task_id = task_id
        self.session_manager = get_session_manager()
    
    @property
    def messages(self) -> List[BaseMessage]:
        """从 SessionManager 加载消息"""
        session_data = self.session_manager.load_session(self.task_id)
        if not session_data:
            return []
        
        return messages_from_session_data(session_data)
    
    def add_message(self, message: BaseMessage) -> None:
        """添加消息到 SessionManager"""
        session_manager = get_session_manager()
        
        if isinstance(message, HumanMessage):
            session_manager.add_message(self.task_id, "user", message.content)
        elif isinstance(message, AIMessage):
            tool_calls = getattr(message, "tool_calls", None) or []
            tool_calls_data = []
            if tool_calls:
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        tool_calls_data.append(tc)
                    else:
                        tool_calls_data.append({
                            "name": getattr(tc, "name", ""),
                            "args": getattr(tc, "args", {}),
                            "id": getattr(tc, "id", "")
                        })
            session_manager.add_message(
                self.task_id, 
                "assistant", 
                message.content or "", 
                tool_calls=tool_calls_data if tool_calls_data else None
            )
        elif isinstance(message, ToolMessage):
            session_manager.add_message(
                self.task_id,
                "tool",
                message.content,
                tool_name=getattr(message, "name", "unknown"),
                tool_call_id=message.tool_call_id
            )
    
    def clear(self) -> None:
        """清空消息历史"""
        session_data = self.session_manager.load_session(self.task_id)
        if session_data:
            session_data["messages"] = []
            self.session_manager.save_session(self.task_id, session_data)

# 获取会话历史
def _get_session_history(task_id: str) -> BaseChatMessageHistory:
    """获取会话历史"""
    return SessionChatMessageHistory(task_id)

# 延迟初始化 ReAct Agent，避免模块导入阶段强依赖模型配置
_react_agent = None
_react_agent_init_error: Exception | None = None


def _get_react_agent():
    """获取（并在首次调用时初始化）ReAct Agent。"""
    global _react_agent, _react_agent_init_error

    if _react_agent is not None:
        return _react_agent
    if _react_agent_init_error is not None:
        raise RuntimeError(f"ReAct Agent 初始化失败: {_react_agent_init_error}") from _react_agent_init_error

    try:
        system_prompt = get_system_prompt_with_tools(AGENT_TOOLS)
        llm = get_react_model()
        _react_agent = create_agent(
            model=llm,
            tools=AGENT_TOOLS,
            system_prompt=system_prompt,
        )
        return _react_agent
    except Exception as exc:
        _react_agent_init_error = exc
        raise RuntimeError(f"ReAct Agent 初始化失败: {exc}") from exc

# 创建带消息历史的 Agent
# 注意：此函数目前未使用，保留作为预留功能，用于未来可能需要直接使用带历史管理的 Agent 的场景
def _create_agent_with_history():
    """
    创建带消息历史管理的 Agent
    
    注意：此函数目前未被调用，保留作为预留功能。
    当前代码直接使用 react_agent 和 SessionChatMessageHistory 来实现消息历史管理。
    """
    return RunnableWithMessageHistory(
        _get_react_agent(),
        _get_session_history,
        input_messages_key="messages",
        history_messages_key="messages",
    )

# 流式运行
def stream(
    user_input: str,
    task_id: str | None = None,
    previous_messages: Optional[List] = None,
    token_tracker: Optional[TokenUsageTracker] = None,
    max_context_tokens: int = 20000
):
    """
    流式运行 ReAct Agent（token 级别），支持自动消息压缩
    
    Args:
        user_input: 用户输入
        task_id: 任务 ID
        previous_messages: 之前的消息列表（短期记忆）
        token_tracker: Token 追踪器
        max_context_tokens: 最大上下文 token 数，超过此值将压缩旧消息
        
    """
    react_agent = _get_react_agent()

    # 设置任务ID（使用辅助函数，同时设置 ContextVar 和全局存储）
    set_task_id(task_id)
    
    # 构建消息列表
    messages = []
    ltm_context = format_relevant_memories_for_prompt(user_input, top_k=3)
    if ltm_context:
        messages.append(SystemMessage(content=ltm_context))
    skill_context = format_active_skills_for_prompt(user_input)
    if skill_context:
        messages.append(SystemMessage(content=skill_context))
    if previous_messages:
        messages.extend(previous_messages)
    messages.append(HumanMessage(content=user_input))
    
    # 获取当前的 completion_tokens 累计值
    current_completion_tokens = 0
    if task_id:
        session_manager = get_session_manager()
        session_data = session_manager.load_session(task_id)
        if session_data and "token_usage" in session_data:
            current_completion_tokens = session_data["token_usage"].get("completion_tokens", 0)
    
    # 应用消息压缩（如果 completion_tokens 超过限制）
    original_count = len(messages)
    compressed_messages, was_compressed, compression_summary = compress_messages(
        messages, 
        max_completion_tokens=max_context_tokens,
        current_completion_tokens=current_completion_tokens
    )
    messages = compressed_messages
    
    inputs = {"messages": messages}
    config = {"configurable": {"task_id": task_id}} if task_id else {}
    
    # 添加 callbacks：token tracker 和 task context callback
    callbacks = []
    if token_tracker:
        callbacks.append(token_tracker)
    if task_id:
        callbacks.append(TaskContextCallback(task_id=task_id))
    
    if callbacks:
        config["callbacks"] = callbacks
    
    # 使用 astream_events 获取 token 级别的流式输出
    result_queue = queue.Queue()
    exception_holder = [None]
    
    # 如果进行了压缩，先发送压缩信息和压缩后的消息列表
    if was_compressed:
        # 将压缩后的消息转换为 session 格式（dict 列表）
        compressed_messages_dict = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                # 系统消息通常不保存到 session
                continue
            elif isinstance(msg, HumanMessage):
                compressed_messages_dict.append({
                    "role": "user",
                    "content": msg.content,
                    "timestamp": datetime.now().isoformat()
                })
            elif isinstance(msg, AIMessage):
                tool_calls_data = []
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        if isinstance(tc, dict):
                            tool_calls_data.append(tc)
                        else:
                            tool_calls_data.append({
                                "name": getattr(tc, "name", ""),
                                "args": getattr(tc, "args", {}),
                                "id": getattr(tc, "id", "")
                            })
                compressed_messages_dict.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": tool_calls_data if tool_calls_data else None,
                    "timestamp": datetime.now().isoformat()
                })
            elif isinstance(msg, ToolMessage):
                compressed_messages_dict.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_name": getattr(msg, "name", "unknown"),
                    "tool_call_id": msg.tool_call_id,
                    "timestamp": datetime.now().isoformat()
                })
        
        result_queue.put({
            "type": "compression",
            "summary": compression_summary,
            "original_count": original_count,
            "compressed_count": len(messages),
            "compressed_messages": compressed_messages_dict
        })
    
    def run_async_stream():
        """在单独的线程中运行异步流"""
        try:
            # 获取当前任务ID（在主线程中）
            current_task_id = get_task_id()
            
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def _stream_events():
                # 在新线程中恢复任务ID上下文
                if current_task_id:
                    set_task_id(current_task_id)
                
                current_message_id = None
                current_content = ""
                # 追踪当前正在执行的工具 run_id，用于过滤工具内部 LLM 的流式输出
                active_tool_run_ids: set[str] = set()
                
                async for event in react_agent.astream_events(
                    inputs,
                    version="v2",
                    include_names=["ChatOpenAI", "ChatTongyi", "ChatGoogleGenerativeAI"] + [tool.name for tool in AGENT_TOOLS],
                    config=config
                ):
                    # 在每个事件处理前都确保任务ID上下文设置（防止上下文丢失）
                    if current_task_id:
                        set_task_id(current_task_id)
                    
                    event_type = event.get("event", "")
                    event_name = event.get("name", "")
                    parent_run_id = event.get("parent_run_id")
                    data = event.get("data", {})
                    
                    # Token 级别的流式输出
                    if event_type == "on_chat_model_stream":
                        # 过滤：工具执行期间的 chat_model_stream 多半来自工具内部 LLM
                        if active_tool_run_ids:
                            continue
                        chunk = data.get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            if current_message_id is None:
                                current_message_id = event.get("run_id", "")
                            
                            current_content += chunk.content
                            result_queue.put({
                                "type": "token",
                                "content": chunk.content,
                                "message_id": current_message_id,
                                "accumulated": current_content
                            })
                    
                    # 完整的消息
                    elif event_type == "on_chat_model_end":
                        # 过滤：工具执行期间的 chat_model_end 多半来自工具内部 LLM
                        if active_tool_run_ids:
                            continue
                        output = data.get("output")
                        if output and hasattr(output, "content") and output.content:
                            result_queue.put({
                                "type": "message",
                                "message": output,
                                "message_id": event.get("run_id", "")
                            })
                            current_message_id = None
                            current_content = ""
                    
                    # 工具调用
                    elif event_type == "on_tool_start":
                        # 在工具执行前设置任务ID上下文
                        event_task_id = None
                        event_data_config = data.get("config", {})
                        if isinstance(event_data_config, dict):
                            event_configurable = event_data_config.get("configurable", {})
                            event_task_id = event_configurable.get("task_id")
                        
                        # 使用事件中的任务ID，否则使用当前任务ID
                        task_id_to_set = event_task_id or current_task_id
                        if task_id_to_set:
                            set_task_id(task_id_to_set)
                        
                        tool_name = event_name
                        tool_input = data.get("input", {})
                        run_id = event.get("run_id", "") or ""
                        if run_id:
                            active_tool_run_ids.add(run_id)
                        result_queue.put({
                            "type": "tool_call",
                            "tool_name": tool_name,
                            "args": tool_input,
                            "run_id": run_id
                        })
                    
                    # 工具结果
                    elif event_type == "on_tool_end":
                        # 确保任务ID上下文仍然设置（工具执行后）
                        if current_task_id:
                            set_task_id(current_task_id)
                        
                        tool_name = event_name
                        tool_output = data.get("output", "")
                        run_id = event.get("run_id", "") or ""
                        if run_id:
                            active_tool_run_ids.discard(run_id)
                        # 确保工具输出被转换为字符串
                        if tool_output is None:
                            tool_output = ""
                        elif not isinstance(tool_output, str):
                            tool_output = str(tool_output)
                        result_queue.put({
                            "type": "tool_result",
                            "tool_name": tool_name,
                            "result": tool_output,
                            "run_id": run_id
                        })
                    
                    # 捕获消息流中的工具消息
                    elif event_type == "on_chain_stream":
                        # 确保任务ID上下文设置
                        if current_task_id:
                            set_task_id(current_task_id)
                        
                        chunk = data.get("chunk", {})
                        if isinstance(chunk, dict) and "messages" in chunk:
                            messages = chunk.get("messages", [])
                            for msg in messages:
                                # 检查是否是 ToolMessage
                                if isinstance(msg, ToolMessage):
                                    tool_name = getattr(msg, "name", "unknown")
                                    tool_content = getattr(msg, "content", "")
                                    tool_call_id = getattr(msg, "tool_call_id", "")
                                    # 确保内容是字符串格式
                                    if tool_content is None:
                                        tool_content_str = ""
                                    elif isinstance(tool_content, str):
                                        tool_content_str = tool_content
                                    else:
                                        tool_content_str = str(tool_content)
                                    result_queue.put({
                                        "type": "tool_result",
                                        "tool_name": tool_name,
                                        "result": tool_content_str,
                                        "run_id": tool_call_id
                                    })
                    
                    # 状态更新（兼容旧格式）
                    elif event_type == "on_chain_end" and event_name == "AgentExecutor":
                        output = data.get("output")
                        if isinstance(output, dict) and "messages" in output:
                            result_queue.put({
                                "type": "state_update",
                                "state": output
                            })
                # 结束标记
                result_queue.put(None)  
            
            loop.run_until_complete(_stream_events())
            loop.close()
            
        except Exception as e:
            exception_holder[0] = e
            result_queue.put(None)
    
    # 启动异步流线程
    thread = threading.Thread(target=run_async_stream, daemon=True)
    thread.start()
    
    # 从队列中获取结果
    while True:
        try:
            item = result_queue.get(timeout=1.0)
            if item is None:
                break
            if exception_holder[0]:
                raise exception_holder[0]
            yield item
        except queue.Empty:
            # 检查线程是否还在运行
            if not thread.is_alive():
                if exception_holder[0]:
                    raise exception_holder[0]
                break
            continue
    
    # 等待线程完成
    thread.join(timeout=5.0)
    
    # 如果还有异常，抛出
    if exception_holder[0]:
        # 如果 astream_events 失败，回退到旧的 stream 方法
        warnings.warn(f"Token-level streaming failed, falling back to message-level: {exception_holder[0]}")
        for chunk in react_agent.stream(inputs, stream_mode="updates", config=config):
            yield {"type": "state_update", "state": chunk}
