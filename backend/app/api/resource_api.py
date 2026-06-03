from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from app.utils.resource_manager import resource_manager
from app.api.deps import get_current_user
from app.schemas.user import User
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/cleanup/session/{session_id}")
async def cleanup_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """清理指定会话ID的资源"""
    try:
        # 在后台任务中执行清理，不阻塞请求
        background_tasks.add_task(resource_manager.cleanup_on_request, session_id)
        return {"status": "success", "message": "资源清理任务已启动"}
    except Exception as e:
        logger.error(f"启动会话资源清理任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动清理任务失败: {str(e)}")

@router.post("/cleanup/temp")
async def cleanup_temp(
    current_user: User = Depends(get_current_user)
):
    """手动触发临时文件清理"""
    # 检查是否为管理员
    if "admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="需要管理员权限")
        
    try:
        cleanup_count = resource_manager.cleanup_temp_files()
        return {
            "status": "success", 
            "message": f"临时文件清理完成，共清理 {cleanup_count} 项"
        }
    except Exception as e:
        logger.error(f"手动触发临时文件清理失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清理失败: {str(e)}")
