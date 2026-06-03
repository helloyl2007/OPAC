from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.models import VideoFile
import os
from app.utils.logger import logger

# 视频状态常量
VIDEO_STATUS = {
    "PENDING": "pending",
    "PROCESSING": "processing",
    "COMPLETED": "completed",
    "FAILED": "failed"
}

def save_video_record(filepath, user_id, session_id=None, original_filename=None, status="pending"):
    """
    保存视频记录到数据库
    
    Args:
        filepath: 视频文件路径
        user_id: 用户ID
        session_id: 会话ID，可选
        original_filename: 原始文件名，如果提供则使用它作为视频标题
        status: 视频状态
        
    Returns:
        int: 创建的视频记录ID
    """
    db = SessionLocal()
    try:
        # 如果没有提供原始文件名，则使用路径中的文件名
        if not original_filename:
            original_filename = os.path.basename(filepath)
            
        # 如果原始文件名中包含扩展名，去掉扩展名
        if original_filename.lower().endswith(('.mp4', '.avi', '.mov', '.wmv')):
            original_filename = os.path.splitext(original_filename)[0]
            
        # 确保filepath使用正斜杠存储
        filepath = filepath.replace("\\", "/")
            
        # 创建视频记录
        video_record = VideoFile(
            filename=original_filename,  # 使用传入的名称或标题
            filepath=filepath,
            user_id=user_id,
            status=status,
            session_id=session_id
        )
        
        db.add(video_record)
        db.commit()
        db.refresh(video_record)
        
        return video_record.id
        
    except Exception as e:
        db.rollback()
        logger.error(f"保存视频记录失败: {str(e)}")
        raise
    finally:
        db.close()

def update_video_status(video_id, status, error=None, progress=None):
    """
    更新视频状态
    
    Args:
        video_id: 视频ID
        status: 新状态
        error: 错误信息（如果有）
        progress: 处理进度（百分比）
        
    Returns:
        bool: 是否更新成功
    """
    db = SessionLocal()
    try:
        video = db.query(VideoFile).filter(VideoFile.id == video_id).first()
        if not video:
            logger.warning(f"视频记录不存在: ID={video_id}")
            return False
            
        video.status = status
        
        if error:
            video.error_message = error[:255]  # 限制长度
            
        if progress is not None:
            # 如果有meta_info，尝试解析并更新progress字段
            if video.meta_info:
                try:
                    import json
                    meta = json.loads(video.meta_info)
                    meta['progress'] = progress
                    video.meta_info = json.dumps(meta)
                except:
                    # 如果解析失败，创建新的meta_info
                    video.meta_info = json.dumps({'progress': progress})
            else:
                # 如果没有meta_info，创建新的
                video.meta_info = json.dumps({'progress': progress})
        
        db.commit()
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"更新视频状态失败: {str(e)}")
        return False
    finally:
        db.close()
