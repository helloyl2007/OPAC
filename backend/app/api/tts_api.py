import os
import logging
import uuid
import time
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import get_current_user
from app.utils.tts import text_to_speech
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

class TTSRequest(BaseModel):
    text: str = "同学们好，欢迎来到我的课堂"
    voice: str = "aixia"

@router.post("/preview")
async def tts_preview(
    request: TTSRequest,
    current_user = Depends(get_current_user)
):
    """生成语音试听预览"""
    try:
        # 生成唯一文件名
        file_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        output_path = f"static/generated/audio/preview_{file_id}.mp3"
        
        # 确保目录存在
        os.makedirs("static/generated/audio", exist_ok=True)
        
        # 确保临时目录存在 - 虽然阿里云TTS不需要，但仍创建目录保持一致性
        temp_dir = "static/generated/temp"
        os.makedirs(temp_dir, exist_ok=True)
        
        logger.info(f"开始生成阿里云TTS预览音频: {output_path}, 音色: {request.voice}")
        
        # 调用阿里云TTS服务
        success = await text_to_speech(
            text=request.text, 
            output_path=output_path, 
            voice=request.voice,
            temp_dir=temp_dir  # 传递但不会使用
        )
        
        # 检查文件是否成功生成
        if not success or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            logger.error(f"阿里云TTS音频生成失败: {output_path}")
            raise HTTPException(status_code=500, detail="阿里云TTS语音生成失败")
            
        # 返回音频文件URL
        audio_url = f"/static/generated/audio/preview_{file_id}.mp3"
        logger.info(f"阿里云TTS音频生成成功: {output_path}")
        
        # 设置自动清理定时器，30分钟后删除
        async def cleanup_audio():
            await asyncio.sleep(1800)  # 30分钟
            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
                    logger.info(f"已删除临时试听文件: {output_path}")
            except Exception as e:
                logger.error(f"删除临时试听文件失败: {output_path}, {str(e)}")
                
        # 启动异步清理任务
        asyncio.create_task(cleanup_audio())
        
        return {
            "status": "success",
            "audio_url": audio_url
        }
        
    except Exception as e:
        logger.error(f"生成试听语音失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成试听失败: {str(e)}")
