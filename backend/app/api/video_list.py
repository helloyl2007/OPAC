from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
import os
import time
import json
import cv2
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import VideoFile, User
from app.schemas.user import User as UserSchema
from app.api.deps import get_current_user
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# 获取视频列表，添加用户筛选功能
@router.get("/list")
async def get_video_list(
    user_id: Optional[int] = Query(None, description="用户ID, 管理员可查询"),
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_user)
):
    try:
        # 检查是否为管理员
        is_admin = "admin" in current_user.roles if current_user.roles else False
        
        # 如果是管理员且指定了用户ID，则查询该用户的视频
        # 否则普通用户只能查看自己的视频
        if is_admin and user_id is not None:
            target_user_id = user_id
            logger.info(f"管理员 {current_user.id} 查询用户 {target_user_id} 的视频列表")
        else:
            target_user_id = current_user.id
            logger.info(f"用户 {target_user_id} 查询自己的视频列表")
        
        # 查询视频列表
        if is_admin and user_id is None:
            # 管理员查询所有视频
            videos = db.query(VideoFile).order_by(VideoFile.created_at.desc()).all()
            logger.info(f"管理员查询所有视频，共 {len(videos)} 条记录")
        else:
            # 查询特定用户的视频
            videos = db.query(VideoFile).filter(
                VideoFile.user_id == target_user_id
            ).order_by(VideoFile.created_at.desc()).all()
            logger.info(f"查询到用户 {target_user_id} 的视频，共 {len(videos)} 条记录")
        
        result = []
        for video in videos:
            # 构建视频URL
            video_url = f"/static/generated/videos/{os.path.basename(video.filepath)}"
            
            # 查询视频所属用户信息
            user = db.query(User).filter(User.id == video.user_id).first()
            username = user.username if user else "未知用户"
            
            # 解析元数据，获取进度信息
            progress = None
            error = None
            if video.meta_info:  # 使用 meta_info 替代 metadata
                try:
                    metadata = json.loads(video.meta_info)
                    progress = metadata.get('progress')
                    error = metadata.get('error')
                except:
                    pass
            
            # 为视频生成缩略图URL
            thumbnail_url = await generate_thumbnail(video_url) if video.status == "completed" else None
            
            result.append({
                "id": video.id,
                "filename": video.filename,
                "status": video.status,
                "progress": progress,  # 添加进度信息
                "error": error,        # 添加错误信息
                "duration": format_duration(video.duration) if video.duration else None,
                "createTime": video.created_at,
                "videoUrl": video_url,
                "thumbnailUrl": thumbnail_url,  # 添加缩略图URL
                "fileSize": get_file_size(video.filepath),
                "userId": video.user_id,  # 添加用户ID
                "username": username  # 添加用户名
            })
            
        return result
    except Exception as e:
        logger.error(f"获取视频列表失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取视频列表失败: {str(e)}")

# 获取单个视频信息，支持管理员访问任意视频
@router.get("/{video_id}")
async def get_video_detail(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_user)
):
    # 检查是否为管理员
    is_admin = "admin" in current_user.roles if current_user.roles else False
    
    # 构建查询
    query = db.query(VideoFile).filter(VideoFile.id == video_id)
    
    # 如果不是管理员，只能查看自己的视频
    if not is_admin:
        query = query.filter(VideoFile.user_id == current_user.id)
        
    video = query.first()
    
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在或无权访问")
    
    # 查询视频所属用户信息
    user = db.query(User).filter(User.id == video.user_id).first()
    username = user.username if user else "未知用户"
    
    # 构建视频URL，添加时间戳防止缓存
    video_url = f"/static/generated/videos/{os.path.basename(video.filepath)}?v={int(time.time())}"
    
    # 对于已完成的视频，确保生成缩略图
    thumbnail_url = None
    if video.status == "completed":
        # 先检查是否已有缩略图
        thumbnail_path = get_thumbnail_path(video.filepath)
        if os.path.exists(thumbnail_path):
            # 已有缩略图，直接使用
            thumbnail_url = f"/static/thumbnails/{os.path.basename(thumbnail_path)}?v={int(time.time())}"
        else:
            # 没有缩略图，尝试生成
            thumbnail_url = await generate_thumbnail(video_url)
            # 如果生成成功，添加时间戳
            if thumbnail_url:
                thumbnail_url = f"{thumbnail_url}?v={int(time.time())}"
    
    return {
        "id": video.id,
        "filename": video.filename,
        "status": video.status,
        "duration": format_duration(video.duration) if video.duration else None,
        "createTime": video.created_at,
        "videoUrl": video_url,
        "thumbnailUrl": thumbnail_url,
        "fileSize": get_file_size(video.filepath),
        "userId": video.user_id,
        "username": username
    }

# 删除视频，支持管理员删除任意视频
@router.delete("/{video_id}")
async def delete_video(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: UserSchema = Depends(get_current_user)
):
    # 检查是否为管理员
    is_admin = "admin" in current_user.roles if current_user.roles else False
    
    # 构建查询
    query = db.query(VideoFile).filter(VideoFile.id == video_id)
    
    # 如果不是管理员，只能删除自己的视频
    if not is_admin:
        query = query.filter(VideoFile.user_id == current_user.id)
        
    video = query.first()
    
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在或无权删除")
    
    try:
        logger.info(f"用户 {current_user.id} {'(管理员)' if is_admin else ''} 正在删除视频 {video_id}")
        
        # 获取session_id用于清理关联资源
        session_id = video.session_id
        
        # 获取视频文件路径
        video_path = video.filepath
        
        # 删除视频文件
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
            logger.info(f"已删除视频文件: {video_path}")
            
        # 删除缩略图
        thumbnail_path = get_thumbnail_path(video_path)
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
            logger.info(f"已删除缩略图: {thumbnail_path}")
            
        # 清理会话相关的资源（如果提供了会话ID）
        if session_id:
            # 清理PPT相关文件
            from app.utils.resource_manager import resource_manager
            cleanup_count = await resource_manager.cleanup_on_request(session_id)
            logger.info(f"清理会话资源: {session_id}, 共删除 {cleanup_count} 项")
        
        # 删除数据库记录
        db.delete(video)
        db.commit()
        
        return {"status": "success", "message": "视频及相关资源已完全删除"}
    except Exception as e:
        db.rollback()
        logger.error(f"删除视频失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除视频失败: {str(e)}")

# 辅助函数 - 格式化视频时长
def format_duration(seconds):
    if not seconds:
        return None
        
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"

# 辅助函数 - 获取文件大小
def get_file_size(filepath):
    try:
        if os.path.exists(filepath):
            size_bytes = os.path.getsize(filepath)
            # 格式化为人类可读的大小
            return format_file_size(size_bytes)
    except:
        pass
    return None

# 为视频生成缩略图的函数
async def generate_thumbnail(video_url: str) -> Optional[str]:
    """为视频生成缩略图"""
    if not video_url:
        return None
        
    try:
        # 清除URL中的查询参数
        video_url = video_url.split('?')[0] if '?' in video_url else video_url
        
        # 将URL路径转换为文件系统路径
        video_path = os.path.join("static", video_url.lstrip("/static/"))
        if not os.path.exists(video_path):
            logger.error(f"视频文件不存在: {video_path}")
            return None
            
        # 生成缩略图路径
        thumbnail_path = get_thumbnail_path(video_path)
        
        # 如果缩略图已存在，直接返回URL
        if os.path.exists(thumbnail_path):
            return f"/static/thumbnails/{os.path.basename(thumbnail_path)}"
            
        # 确保目录存在
        os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
        
        # 使用OpenCV从视频中提取第一帧
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, 10)  # 尝试获取第10帧，避免黑屏
        success, frame = cap.read()
        
        if not success:
            # 如果获取第10帧失败，尝试获取第1帧
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            success, frame = cap.read()
            
            if not success:
                logger.error(f"无法读取视频帧: {video_path}")
                cap.release()
                return None
            
        # 调整图片大小为宽度500像素
        height, width = frame.shape[:2]
        new_width = 500
        new_height = int(height * (new_width / width))
        frame = cv2.resize(frame, (new_width, new_height))
            
        # 保存帧为JPEG图片
        cv2.imwrite(thumbnail_path, frame)
        cap.release()
        
        logger.info(f"成功生成视频缩略图: {thumbnail_path}")
        
        # 返回缩略图URL
        return f"/static/thumbnails/{os.path.basename(thumbnail_path)}"
        
    except Exception as e:
        logger.error(f"生成视频缩略图失败: {str(e)}")
        return None

# 获取缩略图路径的辅助函数
def get_thumbnail_path(video_path: str) -> str:
    """生成缩略图路径"""
    video_filename = os.path.basename(video_path)
    filename_no_ext = os.path.splitext(video_filename)[0]
    return os.path.join("static", "thumbnails", f"{filename_no_ext}.jpg")

# 格式化文件大小的辅助函数
def format_file_size(size_in_bytes: int) -> str:
    """将字节大小格式化为人类可读格式"""
    if not size_in_bytes:
        return "0 B"
        
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024.0
    
    return f"{size_in_bytes:.2f} PB"
