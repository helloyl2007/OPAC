from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import shutil
from pathlib import Path
import os
import uuid
from app.core.auth import get_current_user
from app.utils.lesson_plan_llm import generate_lesson_plan
from app.utils.logger import logger
from app.utils.file_processor import extract_text_from_file
import time
from datetime import datetime, timedelta

router = APIRouter()

class LessonPlanRequest(BaseModel):
    scopeSelection: List[str]  # [教育阶段, 年级, 学科]
    topic: str  # 课题
    planDetails: str  # 课时计划详情
    lessonCount: int  # 课时数

class RemoveFileRequest(BaseModel):
    filename: str

@router.post("/generate")
async def create_lesson_plan(
    req: LessonPlanRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        if not req.scopeSelection or len(req.scopeSelection) < 3:
            raise HTTPException(status_code=400, detail="请选择年级和科目")
        
        if not req.topic:
            raise HTTPException(status_code=400, detail="请输入课题")

        # 构建学科范围字符串
        subject_scope = "".join(req.scopeSelection[1:3])  # 年级+学科

        # 日志记录
        logger.info(f"用户 {current_user.get('username')} 请求生成教案: " +
                   f"范围={subject_scope}, 课题={req.topic}")

        return StreamingResponse(
            generate_lesson_plan(
                subject_scope=subject_scope,
                topic=req.topic,
                plan_details=req.planDetails,
                lesson_count=req.lessonCount
            ),
            media_type="text/event-stream"
        )

    except Exception as e:
        logger.error(f"生成教案失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成教案失败: {str(e)}")

@router.post("/upload-plan") 
async def upload_plan(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """上传教学计划文件接口"""
    try:
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "message": "未认证的用户"}
            )
        
        # 确保目录存在
        temp_dir = Path("static/generated/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 清理过期文件(24小时前的文件)
        try:
            current_time = datetime.now()
            for old_file in temp_dir.glob("*"):
                if old_file.is_file():
                    file_modified_time = datetime.fromtimestamp(old_file.stat().st_mtime)
                    if current_time - file_modified_time > timedelta(hours=24):
                        try:
                            os.remove(old_file)
                            logger.info(f"清理过期文件: {old_file.name}")
                        except Exception as e:
                            logger.warning(f"清理过期文件失败 {old_file.name}: {str(e)}")
        except Exception as e:
            logger.warning(f"检查过期文件失败: {str(e)}")
        
        # 生成唯一文件名
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = temp_dir / unique_filename
        
        # 保存文件
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as e:
            logger.error(f"保存文件失败: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "文件保存失败"}
            )
            
        # 提取文件内容
        try:
            file_content = extract_text_from_file(str(file_path))
        except Exception as e:
            logger.error(f"提取文件内容失败: {str(e)}")
            if file_path.exists():
                os.remove(file_path)
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "文件内容提取失败"}
            )
        
        logger.info(f"用户 {current_user.get('username')} 上传教学计划: {file.filename}")
        
        return JSONResponse(content={
            "success": True,
            "message": "文件上传成功",
            "filename": unique_filename,
            "original_name": file.filename,
            "content": file_content
        })
            
    except Exception as e:
        logger.error(f"上传教学计划失败: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"上传失败: {str(e)}"}
        )

@router.post("/remove-file")  # 路径正确，不需要加 /api/lesson-plan 前缀
async def remove_file(
    req: RemoveFileRequest,
    current_user: dict = Depends(get_current_user)
):
    """删除上传的文件"""
    try:
        if not req.filename:
            return JSONResponse(content={"success": False, "message": "文件名不能为空"})
            
        file_path = Path("static/generated/temp") / req.filename
        
        try:
            if file_path.exists():
                os.remove(file_path)
                logger.info(f"已删除文件: {req.filename}")
            else:
                logger.info(f"文件不存在: {req.filename}")
        except Exception as e:
            logger.error(f"删除文件时出错: {str(e)}")
            
        return JSONResponse(content={"success": True})
            
    except Exception as e:
        logger.error(f"处理删除文件请求时出错: {str(e)}")
        return JSONResponse(content={"success": False, "message": str(e)})
        
if __name__ == "__main__":
    print("Lesson plan router initialized")