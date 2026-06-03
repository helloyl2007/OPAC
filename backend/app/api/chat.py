from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import json
from app.core.auth import get_current_user
from app.utils.bailian_adapter import AsyncBailianClient
from app.utils.logger import logger

router = APIRouter()

class ChatMessage(BaseModel):
    role: str  # "user" 或 "assistant"
    content: str

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = []
    stream: Optional[bool] = True
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    message: str
    success: bool

@router.post("/send")
async def send_chat_message(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """发送聊天消息"""
    try:
        logger.info(f"用户 {current_user.get('username')} 发送聊天消息: {req.message[:50]}...")
        
        # 构建消息历史
        messages = []
        
        # 添加系统提示
        messages.append({
            "role": "system", 
            "content": """
            你是一个AI智教助手，专门帮助老师解答教学相关的问题，提供教学建议和支持。请用简洁、专业、友好的语言回答问题，如TA让你继续进一步建议时，则需要详细回答问题。
            如果有不明确的地方，可以先说理由再询问细节，如果TA没有具体想法，你告诉TA你可以给出建议，但不要直接编造答案，经确认后再输出。
            """
        })
        
        # 添加历史对话
        if req.history:
            for msg in req.history:
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        # 添加当前用户消息
        messages.append({
            "role": "user",
            "content": req.message
        })
        
        # 调用百练API
        client = AsyncBailianClient()
        
        if req.stream:
            # 流式响应
            async def generate_response():
                try:
                    response_stream = await client.chat.completions.create(
                        messages=messages,
                        stream=True,
                        session_id=req.session_id
                    )
                    
                    async for chunk in response_stream:
                        if chunk.choices[0].delta.content:
                            # 构造SSE格式的数据
                            data = {
                                "content": chunk.choices[0].delta.content,
                                "finished": False
                            }
                            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                    
                    # 发送结束标记
                    end_data = {"content": "", "finished": True}
                    yield f"data: {json.dumps(end_data, ensure_ascii=False)}\n\n"
                    
                except Exception as e:
                    logger.error(f"聊天流式响应错误: {str(e)}")
                    error_data = {"error": f"聊天响应错误: {str(e)}", "finished": True}
                    yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
            
            return StreamingResponse(
                generate_response(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    # 禁用 Nginx 等反向代理的缓冲，确保及时发送流式数据
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # 非流式响应
            response = await client.chat.completions.create(
                messages=messages,
                stream=False,
                session_id=req.session_id
            )
            
            return ChatResponse(
                message=response.choices[0].message.content,
                success=True
            )
            
    except Exception as e:
        logger.error(f"聊天API错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"聊天服务错误: {str(e)}")