from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, AsyncGenerator
from datetime import datetime
import uuid
import os
import json
import subprocess
from PIL import Image, ImageDraw, ImageFont
import platform
import random
from sqlalchemy.orm import Session
from app.utils.ppt_generate_llm import generate_ppt_outline
from app.services.ppt_generator import PPTGenerator
from app.services.template_manager import TemplateManager
from app.services.file_storage import FileStorage
from app.utils.logger import logger 
from app.core.auth import get_current_user
from app.models.models import PPTFile, User
from app.core.database import get_db
from app.utils.ppt_utils import extract_ppt_thumbnail
from app.api.users import router as auth_router
from app.api.ppt2video import router as ppt2video_router
from app.utils.task_manager import task_manager  # 导入任务管理器
from app.core.config import settings  # 导入配置

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(ppt2video_router, prefix="/ppt2video", tags=["ppt2video"])

class OutlineRequest(BaseModel):
    topic: str
    reviewPoints: str
    commonMistakes: str
    nextPoints: str
    grade: str
    subject: str

class OutlineResponse(BaseModel):
    outline: List[str]

class GeneratePPTRequest(BaseModel):
    topic: str
    content: str  # JSON字符串
    template_id: str

# 初始化服务
template_manager = TemplateManager('static/templates')
file_storage = FileStorage('static')

@api_router.post("/ppt/outline")
async def generate_outline(request: OutlineRequest):
    try:
        async def generate() -> AsyncGenerator[str, None]:
            try:
                async for chunk in generate_ppt_outline(
                    topic=request.topic,
                    review_points=request.reviewPoints,
                    common_mistakes=request.commonMistakes,
                    next_points=request.nextPoints,
                    grade=request.grade,
                    subject=request.subject
                ):
                    yield chunk
            except Exception as e:
                logger.error(f"Stream generation error: {str(e)}")
                raise
                
        return StreamingResponse(
            generate(),
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no'
            }
        )
    except Exception as e:
        logger.error(f"生成提纲失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"生成提纲失败: {str(e)}"
        )

@api_router.post("/ppt/templates")
async def get_templates():
    try:
        templates = template_manager.get_all_templates()
        if not templates:
            templates = [
                {"id": "1", "name": "简约商务", "preview": f"{settings.BASE_URL}/static/templates/previews/1.jpg", "file_name": "template1.pptx"},
                {"id": "2", "name": "科技风格", "preview": f"{settings.BASE_URL}/static/templates/previews/2.jpg", "file_name": "template2.pptx"},
                {"id": "3", "name": "创意设计", "preview": f"{settings.BASE_URL}/static/templates/previews/3.jpg", "file_name": "template3.pptx"}
            ]
            template_manager.templates = templates
            template_manager._save_templates()
        else:
            for template in templates:
                if not template["preview"].startswith("http"):
                    template["preview"] = f"{settings.BASE_URL}{template['preview']}"
        return {"templates": templates}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取模板失败: {str(e)}")

async def generate_ppt_file(topic: str, content: dict, template_id: str, file_name: str):
    """生成PPT文件"""
    try:
        # 获取模板路径和输出路径
        template_path = template_manager.get_template(template_id)
        output_path = file_storage.get_file_path(file_name, "generated/ppts")
        
        # 创建PPT生成器并生成PPT
        generator = PPTGenerator(template_path)
        generator.generate_ppt(topic, content, output_path)
        
        return f"/static/generated/ppts/{file_name}"
        
    except Exception as e:
        logger.error(f"PPT生成失败: {str(e)}", exc_info=True)
        raise Exception(f"PPT生成失败: {str(e)}")

@api_router.post("/ppt/generate")
async def generate_ppt(
    request: GeneratePPTRequest, 
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # 输入验证
        if not request.topic or not request.content or not request.template_id:
            raise HTTPException(status_code=400, detail="缺少必要参数")
        
        # 获取用户ID
        user_id = int(current_user.get('id'))
        
        # 生成安全的英文文件名
        unique_id = uuid.uuid4().hex[:8]
        safe_filename = f"ppt_{unique_id}.pptx"
        
        # 创建文件相对路径 - 使用正斜杠
        rel_path = os.path.join("generated", "ppts", safe_filename).replace("\\", "/")
        
        # 创建数据库记录
        ppt_file = PPTFile(
            filename=safe_filename,
            title=request.topic,
            user_id=user_id,
            file_path=rel_path,
            status="pending"  # 添加状态字段表示生成中
        )
        
        db.add(ppt_file)
        db.commit()
        db.refresh(ppt_file)  # 获取自增ID
        
        # 使用任务管理器启动任务，而不是FastAPI的background_tasks
        task_id = task_manager.create_task(
            _generate_ppt_task,
            request.topic,
            request.content, 
            request.template_id,
            safe_filename,
            ppt_file.id
        )
        
        # 保存任务ID到数据库，方便后续查询
        ppt_file.task_id = task_id
        db.commit()
        
        logger.info(f"启动PPT生成任务: ID={ppt_file.id}, TaskID={task_id}")
        
        return {
            "status": "pending",
            "message": "PPT生成任务已开始",
            "file_id": ppt_file.id,
            "task_id": task_id,
            "title": request.topic,
            "filename": safe_filename,
            "createTime": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
            
    except Exception as e:
        logger.error(f"处理PPT生成请求失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# 将原有的_generate_ppt_background函数修改为适合task_manager的异步函数
async def _generate_ppt_task(topic: str, content: str, template_id: str, filename: str, ppt_id: int):
    """后台任务：生成PPT"""
    try:
        logger.info(f"开始执行PPT生成任务: ID={ppt_id}")
        
        # 获取数据库连接
        db = next(get_db())
        
        try:
            # 更新状态为运行中
            ppt_record = db.query(PPTFile).filter(PPTFile.id == ppt_id).first()
            if ppt_record:
                ppt_record.status = "running"
                db.commit()
        except Exception as e:
            logger.error(f"更新PPT任务状态失败: {str(e)}")
            db.rollback()
        
        # 解析内容字符串为JSON
        content_data = json.loads(content)
        
        # 获取模板路径和输出路径
        template_path = template_manager.get_template(template_id)
        output_path = file_storage.get_file_path(filename, "generated/ppts")
        
        # 创建PPT生成器并生成PPT
        generator = PPTGenerator(template_path)
        generator.generate_ppt(topic, content_data, output_path)
        
        # 获取文件大小
        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        
        # 设置路径
        base_dir = os.path.abspath(os.getcwd())
        temp_dir = os.path.join(base_dir, "static", "generated", "temp")
        thumb_dir = os.path.join(base_dir, "static", "thumbnails", "ppt_thumb")
        
        # 确保目录存在
        os.makedirs(temp_dir, exist_ok=True)
        os.makedirs(thumb_dir, exist_ok=True)
        
        # 获取PPT文件的绝对路径
        ppt_path = os.path.abspath(output_path)
        
        logger.info(f"PPT文件生成完成: {ppt_path}")
        logger.info(f"文件大小: {file_size} 字节")
        
        # 提取缩略图 - 简化并统一路径处理
        thumbnail_rel_path = None
        if os.path.exists(ppt_path) and file_size > 1024:
            # 使用PPT文件名作为缩略图文件名，确保一致性
            thumb_filename = os.path.splitext(filename)[0] + ".jpg"
            thumb_rel_path = f"/thumbnails/ppt_thumb/{thumb_filename}"  # 相对路径(用于URL)
            thumb_abs_path = os.path.join(base_dir, "static", thumb_rel_path.lstrip('/'))  # 绝对路径
            
            try:
                # 确保目录存在
                os.makedirs(os.path.dirname(thumb_abs_path), exist_ok=True)
                
                # LibreOffice转换命令
                cmd = [
                    'libreoffice',
                    '--headless',
                    '--convert-to', 'jpg',
                    '--outdir', temp_dir,
                    ppt_path
                ]
                
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                
                if process.returncode == 0:
                    # 查找生成的JPG文件
                    jpg_files = [f for f in os.listdir(temp_dir) if f.lower().endswith('.jpg')]
                    if jpg_files:
                        temp_jpg_path = os.path.join(temp_dir, jpg_files[0])
                        
                        # 调整大小并保存到最终位置
                        with Image.open(temp_jpg_path) as img:
                            img = img.resize((500, 281), Image.LANCZOS)
                            img.save(thumb_abs_path, "JPEG", quality=80)
                        
                        # 保存相对路径用于数据库
                        thumbnail_rel_path = thumb_rel_path
                        
                        # 清理临时文件
                        try:
                            os.remove(temp_jpg_path)
                        except Exception as e:
                            logger.warning(f"清理临时文件失败: {str(e)}")
                            
            except Exception as e:
                logger.error(f"生成缩略图失败: {str(e)}", exc_info=True)
        
        # 更新数据库记录
        try:
            ppt_record = db.query(PPTFile).filter(PPTFile.id == ppt_id).first()
            if ppt_record:
                ppt_record.file_size = file_size
                if thumbnail_rel_path:
                    ppt_record.thumbnail_path = thumbnail_rel_path.replace("\\", "/")  # 确保使用正斜杠
                ppt_record.status = "completed"  # 更新为完成状态
                # 确保file_path使用正斜杠
                if ppt_record.file_path:
                    ppt_record.file_path = ppt_record.file_path.replace("\\", "/")
                db.commit()
                logger.info(f"数据库记录更新成功: ID={ppt_id}")
            else:
                logger.warning(f"未找到PPT记录: ID={ppt_id}")
        except Exception as e:
            logger.error(f"更新数据库记录失败: {str(e)}")
            db.rollback()
        finally:
            db.close()
            
        return {"status": "success", "ppt_id": ppt_id, "file_size": file_size}
        
    except Exception as e:
        logger.error(f"生成PPT失败: {str(e)}", exc_info=True)
        
        # 更新数据库中的状态为失败
        try:
            db = next(get_db())
            ppt_record = db.query(PPTFile).filter(PPTFile.id == ppt_id).first()
            if ppt_record:
                ppt_record.status = "failed"
                ppt_record.error_message = str(e)[:200]  # 记录错误信息，限制长度
                db.commit()
        except Exception as db_error:
            logger.error(f"更新失败状态时出错: {str(db_error)}")
        finally:
            try:
                db.close()
            except:
                pass
                
        return {"status": "failed", "error": str(e)}

@api_router.get("/ppt/status/{ppt_id}")
async def check_ppt_status(ppt_id: int, db: Session = Depends(get_db)):
    try:
        ppt_record = db.query(PPTFile).filter(PPTFile.id == ppt_id).first()
        
        if not ppt_record:
            raise HTTPException(status_code=404, detail="找不到PPT记录")
        
        response_data = {
            "status": ppt_record.status,
            "id": ppt_record.id,
            "filename": ppt_record.filename,
            "title": ppt_record.title,
        }
        
        # 简化缩略图URL处理
        if ppt_record.status == "completed":
            response_data["download_url"] = f"/static/{ppt_record.file_path}"
            if ppt_record.thumbnail_path:
                # 确保缩略图文件存在
                thumb_path = os.path.join("static", ppt_record.thumbnail_path.lstrip('/'))
                if os.path.exists(thumb_path):
                    response_data["thumbnail"] = f"/static{ppt_record.thumbnail_path}"
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"检查PPT状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/ppt/list")
async def get_ppt_list(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取PPT列表"""
    try:
        # 根据用户角色决定查询范围
        if current_user.get('roles') == 'admin':
            # 管理员可以查看所有课件
            ppt_files_db = db.query(PPTFile).order_by(
                PPTFile.created_at.desc()
            ).all()
        else:
            # 普通用户只能查看自己的课件
            ppt_files_db = db.query(PPTFile).filter(
                PPTFile.user_id == current_user['id']
            ).order_by(PPTFile.created_at.desc()).all()
        
        ppt_files = []
        for ppt in ppt_files_db:
            # 检查file_path是否为空，避免join错误
            file_path = None
            if ppt.file_path:
                file_path = os.path.join("static", ppt.file_path)
            else:
                file_path = os.path.join("static", "generated", "ppts", ppt.filename)
                # 更新数据库中缺失的file_path，确保使用正斜杠
                try:
                    normalized_path = os.path.join("generated", "ppts", ppt.filename).replace("\\", "/")
                    ppt.file_path = normalized_path
                    db.commit()
                    logger.info(f"更新PPT file_path: ID={ppt.id}, path={ppt.file_path}")
                except Exception as e:
                    logger.error(f"更新file_path失败: {str(e)}")
                    db.rollback()
            
            # 检查文件状态
            exists = os.path.exists(file_path)
            file_size = os.path.getsize(file_path) if exists else 0
            status = 'completed' if exists and file_size > 1024 else 'pending'
            
            # 处理缩略图路径
            thumbnail_url = None
            if ppt.thumbnail_path:
                thumbnail_url = f"/static{ppt.thumbnail_path}"
            
            # 获取下载URL - 确保使用正斜杠
            download_url = None
            if status == "completed":
                if ppt.file_path:
                    download_url = f"/static/{ppt.file_path}"
                else:
                    normalized_path = f"generated/ppts/{ppt.filename}"
                    download_url = f"/static/{normalized_path}"
            
            # 获取创建者信息
            creator = None
            if current_user.get('roles') == 'admin':
                try:
                    user = db.query(User).filter(User.id == ppt.user_id).first()
                    if user:
                        creator = user.username
                except Exception as e:
                    logger.error(f"获取创建者信息失败: {str(e)}")
            
            ppt_files.append({
                "id": ppt.id,
                "filename": ppt.filename,
                "title": ppt.title,
                "createTime": ppt.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                "status": status,
                "download_url": download_url,
                "thumbnail": thumbnail_url,
                "creator": creator
            })
            
        return {"items": ppt_files}
        
    except Exception as e:
        logger.error(f"获取PPT列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取PPT列表失败: {str(e)}")

@api_router.delete("/ppt/delete/{ppt_id}")
async def delete_ppt(
    ppt_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除PPT文件"""
    try:
        # 根据用户角色决定查询条件
        if current_user.get('roles') == 'admin':
            # 管理员可以删除任何PPT
            ppt_file = db.query(PPTFile).filter(PPTFile.id == ppt_id).first()
        else:
            # 普通用户只能删除自己的PPT
            ppt_file = db.query(PPTFile).filter(
                PPTFile.id == ppt_id,
                PPTFile.user_id == current_user['id']
            ).first()
        
        if not ppt_file:
            raise HTTPException(status_code=404, detail="文件不存在或无权访问")

        # 获取文件路径
        file_path = os.path.join("static", ppt_file.file_path) if ppt_file.file_path else None
        
        # 获取缩略图路径
        thumbnail_path = None
        if ppt_file.thumbnail_path:
            thumbnail_path = os.path.join("static", ppt_file.thumbnail_path)
            
        # 删除物理文件
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"已删除文件: {file_path}")
            except Exception as e:
                logger.error(f"删除文件失败: {str(e)}")
            
        # 删除缩略图
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                os.remove(thumbnail_path)
                logger.info(f"已删除缩略图: {thumbnail_path}")
            except Exception as e:
                logger.error(f"删除缩略图失败: {str(e)}")
                
        # 删除数据库记录
        db.delete(ppt_file)
        db.commit()
            
        return {"message": "文件删除成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除PPT文件失败: {str(e)}")
        raise HTTPException(status_code=500, detail="删除文件失败: {str(e)}")
