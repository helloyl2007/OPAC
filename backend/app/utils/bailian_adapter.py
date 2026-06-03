"""
阿里云百练智能体应用API适配器
将百练API包装成OpenAI格式的接口，以最小化现有代码的修改
"""
import asyncio
import json
import aiohttp
from app.core.config import settings
from app.utils.logger import logger

# 尝试导入DashScope SDK，如果不存在则使用HTTP方式
try:
    from dashscope import Application
    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False
    logger.warning("DashScope SDK未安装，将使用HTTP方式调用百练API")


class BailianChatCompletions:
    """百练聊天完成API适配器"""
    
    def __init__(self, client):
        self.client = client

    async def create(self, model=None, messages=None, temperature=0.7, max_tokens=2000, stream=False, **kwargs):
        """
        创建聊天完成，兼容OpenAI格式
        """
        try:
            # 将OpenAI格式的messages转换为百练应用的prompt（保留完整多轮历史）
            if messages:
                role_map = {
                    "system": "系统",
                    "user": "用户",
                    "assistant": "助手"
                }
                prompt_parts = []
                for msg in messages:
                    role = role_map.get(msg.get("role"), msg.get("role", ""))
                    content = msg.get("content", "")
                    # 使用对话转录格式，便于应用侧理解上下文
                    prompt_parts.append(f"{role}: {content}")
                prompt = "\n\n".join(prompt_parts)
            else:
                prompt = kwargs.get("prompt", "")

            # 透传对话ID（多轮对话）
            conversation_id = kwargs.get("conversation_id") or kwargs.get("session_id")
            
            logger.info(f"调用百练API，prompt长度: {len(prompt)}")
            logger.debug(f"prompt内容: {prompt[:200]}...")
            
            if DASHSCOPE_AVAILABLE:
                return await self._dashscope_call(prompt, stream, conversation_id)
            else:
                return await self._http_call(prompt, stream, conversation_id)
                
        except Exception as e:
            logger.error(f"百练API调用失败: {str(e)}")
            raise Exception(f"百练API调用失败: {str(e)}")

    async def _dashscope_call(self, prompt, stream, conversation_id=None):
        """使用DashScope SDK调用"""
        def sync_call():
            call_kwargs = dict(
                api_key=settings.OPENAI_API_KEY,
                app_id=settings.BAILIAN_APP_ID,
                prompt=prompt,
                stream=stream
            )
            # 如果有对话ID，则一并传入（不同SDK版本可能是 conversation_id 或 session_id，这里优先 conversation_id）
            if conversation_id:
                call_kwargs["conversation_id"] = conversation_id
            response = Application.call(**call_kwargs)
            return response
        
        # 在线程池中执行同步调用
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, sync_call)
        
        if stream:
            # 对于DashScope的流式响应，创建专门的响应对象
            return BailianDashScopeStreamResponse(response)
        else:
            # 转换为OpenAI格式的响应
            return BailianResponse({
                "choices": [{
                    "message": {
                        "content": response.output.text if hasattr(response, 'output') else str(response),
                        "role": "assistant"
                    },
                    "finish_reason": getattr(response.output, 'finish_reason', 'stop') if hasattr(response, 'output') else 'stop'
                }],
                "usage": getattr(response, 'usage', {}),
                "id": getattr(response, 'request_id', ''),
                "object": "chat.completion"
            })

    async def _http_call(self, prompt, stream, conversation_id=None):
        """使用HTTP方式调用"""
        # 构建百练API请求
        url = f"{settings.OPENAI_API_BASE.rstrip('/')}/apps/{settings.BAILIAN_APP_ID}/completion"
        
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # 构建请求数据
        data = {
            "prompt": prompt,
            "stream": stream
        }
        # 透传会话ID，兼容不同字段名
        if conversation_id:
            data["conversation_id"] = conversation_id
            data["session_id"] = conversation_id
                
        logger.info(f"发送百练API请求: {url}")
        logger.debug(f"请求数据: {json.dumps(data, ensure_ascii=False)}")
        
        if stream:
            return self._stream_response(url, headers, data)
        else:
            return await self._non_stream_response(url, headers, data)

    async def _non_stream_response(self, url, headers, data):
        """处理非流式响应"""
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"百练API错误响应: {response.status} - {error_text}")
                    raise Exception(f"百练API错误: {response.status}")
                
                result = await response.json()
                
                # 转换为OpenAI格式的响应
                return BailianResponse({
                    "choices": [{
                        "message": {
                            "content": result.get("output", {}).get("text", ""),
                            "role": "assistant"
                        },
                        "finish_reason": result.get("output", {}).get("finish_reason", "stop")
                    }],
                    "usage": result.get("usage", {}),
                    "id": result.get("request_id", ""),
                    "object": "chat.completion"
                })

    async def _stream_response(self, url, headers, data):
        """处理流式响应"""
        session = aiohttp.ClientSession()
        
        try:
            response = await session.post(url, headers=headers, json=data)
            
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"百练API错误响应: {response.status} - {error_text}")
                await session.close()
                raise Exception(f"百练API错误: {response.status}")
            
            return BailianStreamResponse(response, session)
            
        except Exception as e:
            await session.close()
            raise e


class BailianResponse:
    """百练响应对象，兼容OpenAI格式"""
    
    def __init__(self, data):
        self.data = data
        self.choices = [BailianChoice(choice) for choice in data.get("choices", [])]


class BailianChoice:
    """百练选择对象"""
    
    def __init__(self, choice_data):
        self.message = BailianMessage(choice_data.get("message", {}))
        self.finish_reason = choice_data.get("finish_reason")


class BailianMessage:
    """百练消息对象"""
    
    def __init__(self, message_data):
        self.content = message_data.get("content", "")
        self.role = message_data.get("role", "assistant")


class BailianStreamResponse:
    """百练流式响应对象"""
    
    def __init__(self, response, session):
        self.response = response
        self.session = session

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            line = await self.response.content.readline()
            if not line:
                if self.session:
                    await self.session.close()
                raise StopAsyncIteration
            
            line = line.decode('utf-8').strip()
            
            if not line or line.startswith(':'):
                return await self.__anext__()
            
            if line.startswith('data: '):
                data_str = line[6:]  # 移除 "data: " 前缀
                
                if data_str == '[DONE]':
                    if self.session:
                        await self.session.close()
                    raise StopAsyncIteration
                
                try:
                    data = json.loads(data_str)
                    # 转换为OpenAI格式
                    if "output" in data:
                        # 百练格式转换
                        content = data.get("output", {}).get("text", "")
                        return BailianStreamChunk({
                            "choices": [{
                                "delta": {
                                    "content": content
                                }
                            }]
                        })
                    else:
                        # 已经是OpenAI格式或其他格式
                        return BailianStreamChunk(data)
                        
                except json.JSONDecodeError:
                    logger.warning(f"无法解析JSON数据: {data_str}")
                    return await self.__anext__()
            
            return await self.__anext__()
            
        except Exception as e:
            if self.session:
                await self.session.close()
            logger.error(f"流式响应处理错误: {str(e)}")
            raise StopAsyncIteration


class BailianDashScopeStreamResponse:
    """DashScope流式响应对象"""
    
    def __init__(self, response):
        self.response = response
        self._iterator = None
        self._last_content = ""  # 记录上次的完整内容，用于计算增量

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            if self._iterator is None:
                # 创建迭代器
                self._iterator = iter(self.response)
            
            # 在线程池中执行next()操作，因为DashScope的迭代可能是同步的
            loop = asyncio.get_event_loop()
            chunk = await loop.run_in_executor(None, next, self._iterator, None)
            
            if chunk is None:
                raise StopAsyncIteration
            
            # 转换为OpenAI格式
            current_content = ""
            if hasattr(chunk, 'output') and hasattr(chunk.output, 'text'):
                current_content = chunk.output.text
            elif hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                current_content = chunk.choices[0].message.content
            else:
                current_content = str(chunk)
            
            # 计算增量内容（新增的部分）
            if current_content.startswith(self._last_content):
                # 如果当前内容以上次内容开头，则提取增量部分
                delta_content = current_content[len(self._last_content):]
            else:
                # 如果不是累积式，直接使用当前内容
                delta_content = current_content
            
            # 更新上次内容记录
            self._last_content = current_content
            
            # 只有当有新增内容时才返回
            if delta_content:
                return BailianStreamChunk({
                    "choices": [{
                        "delta": {
                            "content": delta_content
                        }
                    }]
                })
            else:
                # 如果没有新增内容，继续获取下一个chunk
                return await self.__anext__()
            
        except StopIteration:
            # 同步迭代器正常结束
            raise StopAsyncIteration
        except StopAsyncIteration:
            # 异步迭代器正常结束：不应记录为错误
            raise
        except Exception as e:
            # 真实异常才记录错误，避免正常结束被误判
            logger.error(f"DashScope流式响应处理错误: {str(e)}")
            raise StopAsyncIteration


class BailianStreamChunk:
    """百练流式响应块"""
    
    def __init__(self, data):
        self.choices = [BailianStreamChoice(choice) for choice in data.get("choices", [])]


class BailianStreamChoice:
    """百练流式选择对象"""
    
    def __init__(self, choice_data):
        self.delta = BailianDelta(choice_data.get("delta", {}))


class BailianDelta:
    """百练增量对象"""
    
    def __init__(self, delta_data):
        self.content = delta_data.get("content")


class BailianChatAPI:
    """百练聊天API"""
    
    def __init__(self):
        self.completions = BailianChatCompletions(self)


class AsyncBailianClient:
    """百练异步客户端，兼容OpenAI AsyncOpenAI接口"""
    
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.base_url = base_url or settings.OPENAI_API_BASE
        self.chat = BailianChatAPI()