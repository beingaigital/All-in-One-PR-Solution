#!/usr/bin/env python3
"""
SPO三元组提取器 Cursor Write It-qcf ;
"""

import os
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import warnings

warnings.filterwarnings('ignore')

try:
    import openai
except ImportError:
    print("⚠️ 警告: openai库未安装，请运行: pip install openai")
    openai = None


class SPOTripleExtractor:
    """SPO三元组提取器 Cursor Write It-qcf ;"""

    def __init__(
        self,
        model_name: str = "deepseek/deepseek-chat-v3-0324",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        use_openrouter: bool = True
    ):
        """
        初始化SPO三元组提取器 Cursor Write It-qcf ;
        """
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.use_openrouter = use_openrouter

        # 配置API（去除前后空格）
        if use_openrouter:
            self.api_key = (api_key or os.getenv("OPENROUTER_API_KEY", "")).strip()
            self.base_url = base_url or "https://openrouter.ai/api/v1"
        else:
            self.api_key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
            self.base_url = base_url or None
            
            # 如果使用 OpenAI API，但模型名称包含 "/"（如 deepseek/xxx），提示错误
            if "/" in model_name:
                raise ValueError(
                    f"模型名称 '{model_name}' 包含 '/'，这通常是 OpenRouter 格式。\n"
                    "如果使用 OpenAI API，请使用 OpenAI 支持的模型名称（如 gpt-4, gpt-3.5-turbo）。\n"
                    "如果使用 OpenRouter，请设置 use_openrouter=True。"
                )

        # 初始化OpenAI客户端
        if not self.api_key:
            provider = "OpenRouter" if use_openrouter else "OpenAI"
            env_var = "OPENROUTER_API_KEY" if use_openrouter else "OPENAI_API_KEY"
            raise ValueError(
                f"API key未设置。请设置环境变量 {env_var}（使用 {provider}），"
                "或者在初始化时传入api_key参数。\n"
                f"提示：检查 .env 文件中是否有 {env_var}，并确保等号后面没有多余的空格。"
            )

        try:
            # 禁用 OpenAI 客户端的 HTTP 请求日志，避免干扰进度条显示
            import logging
            openai_logger = logging.getLogger("openai")
            openai_logger.setLevel(logging.WARNING)  # 只显示警告和错误
            
            self.client = openai.OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=60.0  # 增加超时时间到60秒
            )
        except Exception as e:
            raise Exception(f"OpenAI客户端初始化失败: {e}")

        # 系统提示词
        self.extraction_system_prompt = """
你是一个专门的知识图谱提取专家。
你的任务是从给定文本中识别并提取事实性的Subject-Predicate-Object (SPO) 三元组。
专注于准确性，并严格遵循用户提示中要求的JSON输出格式。
提取核心实体和最直接的关系。
"""

        # 用户提示词模板（支持中英文）
        # 注意：JSON示例中的大括号需要转义（{{ 和 }}）以避免被.format()误解析
        self.extraction_user_prompt_template = """
请从以下文本中提取Subject-Predicate-Object (S-P-O) 三元组。

**非常重要的规则：**
1. **输出格式：** 仅响应一个有效的JSON数组。每个元素必须是一个包含"subject"、"predicate"、"object"键的对象。
2. **仅JSON：** 不要在JSON数组前后包含任何文本（例如，不要写"这是JSON："或解释）。不要使用markdown ```json ... ```标签。
3. **简洁谓词：** 保持'predicate'值简洁（1-3个词）。对于中文文本，使用中文动词；对于英文文本，使用英文动词（例如：'launched'、'推出'、'collaborates with'、'合作'）。
4. **语言保持：** 保持原始语言（中文文本用中文，英文文本用英文）。不要强制转换为小写。
5. **代词解析：** 将代词替换为它们基于文本上下文所指的特定实体名称。
6. **具体性：** 捕获具体细节和关系。
7. **完整性：** 提取所有提到的不同事实关系，特别是公司、品牌、活动、策略之间的关系。

**要处理的文本：**
```text
{text_chunk}
```

**必需的JSON输出格式示例：**
[
{{ "subject": "奥迪公司", "predicate": "推出", "object": "2021年电商大促活动" }},
{{ "subject": "奥迪", "predicate": "合作", "object": "京东平台" }},
{{ "subject": "雅诗兰黛", "predicate": "发布", "object": "抗老护肤产品" }}
]

**你的JSON输出（必须以'['开头，以']'结尾）：**
"""

    def chunk_text(
        self,
        text: str,
        chunk_size: int = 150,
        overlap: int = 30
    ) -> List[Dict[str, Any]]:
        """
        将文本分块 Cursor Write It-qcf ;
        """
        if overlap >= chunk_size and chunk_size > 0:
            raise ValueError(f"重叠({overlap})必须小于块大小({chunk_size})")

        words = text.split()
        total_words = len(words)
        chunks = []
        start_index = 0
        chunk_number = 1

        while start_index < total_words:
            end_index = min(start_index + chunk_size, total_words)
            chunk_text = " ".join(words[start_index:end_index])
            chunks.append({
                "text": chunk_text,
                "chunk_number": chunk_number
            })

            # 计算下一个块的起始位置
            next_start_index = start_index + chunk_size - overlap

            # 确保有进展
            if next_start_index <= start_index:
                if end_index == total_words:
                    break
                next_start_index = start_index + 1

            start_index = next_start_index
            chunk_number += 1

            # 安全中断
            if chunk_number > total_words:
                print("⚠️ 警告: 分块循环超过总词数，中断。")
                break

        return chunks

    def extract_triples_from_chunk(
        self,
        chunk_text: str,
        chunk_number: int = 1,
        verbose: bool = False
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        从单个chunk中提取三元组 Cursor Write It-qcf ;
        """
        # 格式化用户提示
        user_prompt = self.extraction_user_prompt_template.format(text_chunk=chunk_text)

        llm_output = None
        error_message = None

        try:
            if verbose:
                print(f"📤 发送请求到LLM (chunk {chunk_number})...")

            # 构建消息
            messages = [
                {"role": "system", "content": self.extraction_system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            # API调用参数
            call_params = {
                "model": self.model_name,
                "messages": messages,
                "max_tokens": self.max_tokens,
            }

            # 某些模型不支持temperature=0.0，使用条件设置
            try:
                call_params["temperature"] = self.temperature
            except:
                pass  # 如果模型不支持，跳过

            # 某些模型可能支持response_format（仅对支持的模型使用）
            # 注意：只有部分 OpenAI 模型支持此参数，OpenRouter 的某些模型可能不支持
            # 如果使用 OpenAI API，且模型名称以 gpt- 开头，才添加此参数
            if not self.use_openrouter and self.model_name.startswith("gpt-"):
                try:
                    call_params["response_format"] = {"type": "json_object"}
                except:
                    pass

            # 增加超时重试机制
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    response = self.client.chat.completions.create(**call_params, timeout=60.0)
                    break
                except Exception as e:
                    error_str = str(e).lower()
                    # 如果是 400 错误，可能是参数问题，不重试直接抛出
                    if "400" in error_str or "bad request" in error_str:
                        if verbose:
                            print(f"❌ API 请求参数错误（400），不重试: {e}")
                        raise
                    # 超时错误才重试
                    if attempt < max_retries - 1 and ("timeout" in error_str or "timed out" in error_str):
                        if verbose:
                            print(f"⚠️ 请求超时，重试 {attempt + 1}/{max_retries}...")
                        continue
                    raise

            if verbose:
                print(f"✅ LLM响应已接收 (chunk {chunk_number})")

            # 提取原始响应内容
            llm_output = response.choices[0].message.content.strip()

            if verbose:
                print(f"--- 原始LLM输出 (Chunk {chunk_number}) ---")
                print(llm_output[:500] + "..." if len(llm_output) > 500 else llm_output)

        except Exception as e:
            error_message = f"API调用错误: {str(e)}"
            if verbose:
                print(f"❌ {error_message}")
            return [], error_message

        # 解析JSON
        parsed_json = None
        parsing_error = None

        if llm_output is not None:
            try:
                # 策略1: 直接解析（理想情况）
                parsed_data = json.loads(llm_output)

                # 处理response_format={'type':'json_object'}返回包含列表的字典的情况
                if isinstance(parsed_data, dict):
                    if verbose:
                        print("   🔍 检测到字典响应，尝试提取列表...")
                    list_values = [v for v in parsed_data.values() if isinstance(v, list)]
                    if len(list_values) == 1:
                        parsed_json = list_values[0]
                        if verbose:
                            print("      ✅ 成功从字典中提取列表")
                    elif isinstance(parsed_data, dict) and any(k in parsed_data for k in ['triples', 'results', 'data', 'items']):
                        # 尝试常见的关键字
                        for key in ['triples', 'results', 'data', 'items']:
                            if key in parsed_data and isinstance(parsed_data[key], list):
                                parsed_json = parsed_data[key]
                                if verbose:
                                    print(f"      ✅ 从字典的'{key}'键中提取列表")
                                break
                        else:
                            # 检查是否是单个三元组字典（包含subject, predicate, object）
                            if all(k in parsed_data for k in ['subject', 'predicate', 'object']):
                                # 单个三元组，转换为列表
                                parsed_json = [parsed_data]
                                if verbose:
                                    print("      ✅ 检测到单个三元组字典，转换为列表")
                            else:
                                raise ValueError("JSON对象接收到了，但不包含单个三元组列表。")
                    elif all(k in parsed_data for k in ['subject', 'predicate', 'object']):
                        # 单个三元组，转换为列表
                        parsed_json = [parsed_data]
                        if verbose:
                            print("      ✅ 检测到单个三元组字典，转换为列表")
                    else:
                        raise ValueError("JSON对象接收到了，但不包含单个三元组列表。")
                elif isinstance(parsed_data, list):
                    parsed_json = parsed_data
                    if verbose:
                        print("   ✅ 成功直接解析JSON列表")
                else:
                    raise ValueError("解析的JSON不是列表或预期的字典包装器。")

            except json.JSONDecodeError as json_err:
                parsing_error = f"JSONDecodeError: {json_err}。尝试正则表达式回退..."
                if verbose:
                    print(f"   ⚠️ {parsing_error}")

                # 策略2: 正则表达式回退（用于可能包装在文本/markdown中的数组）
                match = re.search(r'^\s*(\[.*?\])\s*$', llm_output, re.DOTALL)
                if match:
                    json_string_extracted = match.group(1)
                    if verbose:
                        print("      🔍 正则表达式找到潜在的JSON数组结构")
                    try:
                        parsed_json = json.loads(json_string_extracted)
                        if verbose:
                            print("      ✅ 从正则表达式提取成功解析JSON")
                        parsing_error = None
                    except json.JSONDecodeError as nested_err:
                        parsing_error = f"正则表达式后JSONDecodeError: {nested_err}"
                        if verbose:
                            print(f"      ❌ 错误: 正则表达式内容不是有效的JSON: {nested_err}")
                else:
                    parsing_error = "JSONDecodeError和正则表达式回退都失败了。"
                    if verbose:
                        print("      ❌ 错误: 正则表达式无法找到JSON数组结构")

            except ValueError as val_err:
                parsing_error = f"ValueError: {val_err}"
                if verbose:
                    print(f"   ❌ 错误: {parsing_error}")

        # 验证并提取三元组
        valid_triples = []

        if parsed_json is not None:
            if isinstance(parsed_json, list):
                for item in parsed_json:
                    if not isinstance(item, dict):
                        if verbose:
                            print(f"   ⚠️ 跳过非字典项: {type(item).__name__}")
                        continue
                    
                    # 安全获取字段值
                    subject = item.get('subject')
                    predicate = item.get('predicate')
                    obj = item.get('object')
                    
                    # 检查字段是否存在且为字符串
                    if not all(isinstance(value, str) and value.strip() for value in (subject, predicate, obj)):
                        if verbose:
                            print(f"   ⚠️ 跳过不完整或非字符串值的三元组: {item}")
                        continue
                    
                    # 过滤无效值（占位符、空字符串、纯引号等）
                    subject_clean = subject.strip()
                    predicate_clean = predicate.strip()
                    obj_clean = obj.strip()
                    
                    # 排除占位符字符串（如 '"subject"', 'subject', 'N/A' 等）
                    invalid_values = {'subject', 'predicate', 'object', 'n/a', 'na', 'null', 'none', 
                                    '"subject"', '"predicate"', '"object"', "'subject'", "'predicate'", "'object'"}
                    
                    if (subject_clean.lower() in invalid_values or 
                        predicate_clean.lower() in invalid_values or 
                        obj_clean.lower() in invalid_values):
                        if verbose:
                            print(f"   ⚠️ 跳过包含占位符的三元组: {item}")
                        continue
                    
                    # 确保值不为空
                    if not all([subject_clean, predicate_clean, obj_clean]):
                        if verbose:
                            print(f"   ⚠️ 跳过空值三元组: {item}")
                        continue
                    
                    # 添加到有效三元组
                    valid_triples.append({
                        'subject': subject_clean,
                        'predicate': predicate_clean,
                        'object': obj_clean,
                        'chunk': chunk_number
                    })
            else:
                parsing_error = "解析的数据不是列表，无法提取三元组。"

        if parsing_error and not valid_triples:
            return [], parsing_error

        return valid_triples, None

    def extract_triples_from_text(
        self,
        text: str,
        chunk_size: int = 150,
        overlap: int = 30,
        verbose: bool = False
    ) -> Dict[str, Any]:
        """
        从完整文本中提取所有三元组 Cursor Write It-qcf ;
        """
        # 分块
        if verbose:
            print(f"📝 开始文本分块 (chunk_size={chunk_size}, overlap={overlap})...")
        chunks = self.chunk_text(text, chunk_size, overlap)
        if verbose:
            print(f"✅ 文本已分割为 {len(chunks)} 个块")

        # 提取三元组
        all_extracted_triples = []
        failed_chunks = []

        if verbose:
            print(f"\n🔍 开始从 {len(chunks)} 个块中提取三元组...")

        for chunk_info in chunks:
            chunk_text = chunk_info['text']
            chunk_num = chunk_info['chunk_number']

            triples, error = self.extract_triples_from_chunk(
                chunk_text, chunk_num, verbose=verbose
            )

            if error:
                failed_chunks.append({
                    'chunk_number': chunk_num,
                    'error': error
                })
            else:
                all_extracted_triples.extend(triples)
                if verbose:
                    print(f"   ✅ Chunk {chunk_num}: 提取了 {len(triples)} 个三元组")

        return {
            'triples': all_extracted_triples,
            'failed_chunks': failed_chunks,
            'total_chunks': len(chunks),
            'successful_chunks': len(chunks) - len(failed_chunks)
        }

    def normalize_triples(
        self,
        triples: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        规范化三元组 Cursor Write It-qcf ;
        """
        normalized_triples = []
        seen_triples = set()  # 跟踪(subject, predicate, object)元组

        for triple in triples:
            subject_raw = triple.get('subject')
            predicate_raw = triple.get('predicate')
            object_raw = triple.get('object')
            chunk_num = triple.get('chunk', 'unknown')

            if isinstance(subject_raw, str) and isinstance(predicate_raw, str) and isinstance(object_raw, str):
                # 规范化
                normalized_sub = subject_raw.strip().lower()
                normalized_pred = re.sub(r'\s+', ' ', predicate_raw.strip().lower()).strip()
                normalized_obj = object_raw.strip().lower()

                # 过滤空值
                if normalized_sub and normalized_pred and normalized_obj:
                    triple_identifier = (normalized_sub, normalized_pred, normalized_obj)

                    # 去重
                    if triple_identifier not in seen_triples:
                        normalized_triples.append({
                            'subject': normalized_sub,
                            'predicate': normalized_pred,
                            'object': normalized_obj,
                            'source_chunk': chunk_num
                        })
                        seen_triples.add(triple_identifier)

        return normalized_triples


def test_spo_extractor():
    """测试SPO提取器 Cursor Write It-qcf ;"""
    # 加载 .env 文件
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        # 如果没有 dotenv，尝试手动读取 .env 文件
        env_path = Path(__file__).parent.parent.parent.parent / '.env'
        if env_path.exists():
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
    
    test_text = """
    玛丽·居里，原名玛丽亚·斯克沃多夫斯卡，出生于波兰华沙，是一位开创性的物理学家和化学家。
    她在放射性研究方面进行了开创性的研究。与她的丈夫皮埃尔·居里一起，
    她发现了元素钋和镭。玛丽·居里是第一位获得诺贝尔奖的女性，
    第一位也是唯一一位两次获得诺贝尔奖的女性，
    也是唯一一位在两个不同科学领域获得诺贝尔奖的人。
    """

    print("🧪 测试SPO三元组提取器")
    print("=" * 60)

    try:
        # 优先使用 OpenAI API key，如果没有则使用 OpenRouter
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        
        if openai_key:
            print("✅ 使用 OpenAI API")
            extractor = SPOTripleExtractor(
                model_name="gpt-3.5-turbo",
                use_openrouter=False,
                api_key=openai_key
            )
        elif openrouter_key:
            print("✅ 使用 OpenRouter API")
            extractor = SPOTripleExtractor(
                use_openrouter=True,
                api_key=openrouter_key
            )
        else:
            # 默认使用 OpenRouter（向后兼容）
            print("⚠️ 未找到 API key，尝试使用默认配置（OpenRouter）")
            extractor = SPOTripleExtractor()
        
        result = extractor.extract_triples_from_text(
            test_text,
            chunk_size=50,
            overlap=10,
            verbose=True
        )

        print(f"\n📊 提取结果:")
        print(f"   总块数: {result.get('total_chunks', 0)}")
        print(f"   成功块数: {result.get('successful_chunks', 0)}")
        print(f"   失败块数: {len(result.get('failed_chunks', []))}")
        print(f"   提取的三元组数: {len(result.get('triples', []))}")
        
        # 如果有失败的块，显示详细信息
        failed_chunks = result.get('failed_chunks', [])
        if failed_chunks:
            print(f"\n⚠️ 失败的块:")
            for failed in failed_chunks[:3]:  # 只显示前3个
                print(f"   Chunk {failed.get('chunk_number', '?')}: {failed.get('error', 'Unknown error')}")

        # 规范化
        triples = result.get('triples', [])
        if triples:
            normalized = extractor.normalize_triples(triples)
            print(f"   规范化后的三元组数: {len(normalized)}")
        else:
            normalized = []
            print(f"   ⚠️ 没有提取到三元组")

        print(f"\n📋 前5个三元组:")
        for i, triple in enumerate(normalized[:5]):
            try:
                subject = triple.get('subject', 'N/A')
                predicate = triple.get('predicate', 'N/A')
                obj = triple.get('object', 'N/A')
                print(f"   {i+1}. {subject} --[{predicate}]--> {obj}")
            except Exception as e:
                print(f"   {i+1}. ⚠️ 打印三元组时出错: {e}, 数据: {triple}")

        return normalized

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        print("\n详细错误信息:")
        traceback.print_exc()
        return []


if __name__ == "__main__":
    test_spo_extractor()

