from fastapi import APIRouter, HTTPException, Depends, Request, File, UploadFile, Form
from fastapi.responses import StreamingResponse, JSONResponse
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
import asyncio
import os
import shutil
from pathlib import Path
import uuid
from app.utils.exam_generate_llm import generate_exam_questions
from app.core.auth import get_current_user
from app.utils.logger import logger
from app.utils.file_processor import extract_text_from_file
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import TextbookContent

router = APIRouter()  # 正确定义了路由器

class ExamRequest(BaseModel):
    """试题生成请求模型"""
    scopeSelection: List[str]  # 级联选择器选择的值：[教育阶段, 年级, 学科]
    selectedTopics: List[str]  # 选中的考查范围
    requirements: Optional[str] = None  # 具体要求
    questionTypes: Dict[str, int]  # 题目类型和数量 {"singleChoice": 2, "multipleChoice": 3, ...}
    bookType: Optional[str] = None  # 上册/下册
    selectedUnits: Optional[List[str]] = None  # 选中的单元列表
    referenceContent: Optional[str] = None  # 添加参考资料内容字段

class CleanupRequest(BaseModel):
    """文件清理请求模型"""
    filename: str

class RemoveFileRequest(BaseModel):
    filename: str

@router.post("/upload-reference")
async def upload_reference(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """上传参考资料接口"""
    try:
        # 确保已认证
        if not current_user:
            return JSONResponse(
                status_code=401,
                content={"success": False, "message": "未认证的用户"}
            )
        
        # 确保目录存在
        temp_dir = Path("static/generated/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成唯一文件名
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = temp_dir / unique_filename
        
        # 保存文件
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 提取文件内容
        file_content = extract_text_from_file(str(file_path))
        
        logger.info(f"用户 {current_user.get('username')} 上传参考资料: {file.filename}")
        
        return JSONResponse(content={
            "success": True,
            "message": "文件上传成功",
            "filename": unique_filename,
            "original_name": file.filename,
            "content": file_content
        })
            
    except Exception as e:
        logger.error(f"上传参考资料失败: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"上传参考资料失败: {str(e)}"}
        )

@router.post("/remove-file")
async def remove_file(
    req: RemoveFileRequest,
    current_user: dict = Depends(get_current_user)
):
    """直接删除上传的文件"""
    try:
        if not req.filename:
            return JSONResponse(content={"success": False, "message": "文件名不能为空"})
            
        # 直接构建文件路径并删除
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

@router.get("/get-textbook-content")
async def get_textbook_content(
    subject: str, 
    semester: str, 
    units: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """获取教材内容"""
    try:
        # 添加详细日志，便于调试
        logger.info(f"尝试获取教材内容: subject={subject}, semester={semester}, units={units}")
        
        # 将逗号分隔的字符串转换为列表
        unit_list = units.split(',') if units else []
        
        if not unit_list:
            logger.warning("未选择任何单元")
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "未选择任何单元"}
            )
        
        # 构造完整的学科名称进行精确匹配
        # 前端传来的是"语文"，需要根据级联选择器构建完整名称如"小学一年级语文"
        # 这里需要在前端调用时构建完整的学科名称，因此需要修改前端代码
        
        try:
            # 使用精确匹配而非模糊匹配
            query = db.query(TextbookContent).filter(
                TextbookContent.subject == subject,  # 精确匹配
                TextbookContent.semester == semester,
                TextbookContent.unit.in_(unit_list)
            )
            
            # 打印SQL，便于调试
            query_string = str(query.statement.compile(
                compile_kwargs={"literal_binds": True}
            ))
            logger.info(f"SQL查询: {query_string}")
            
            result = query.all()
            logger.info(f"查询结果数量: {len(result)}")
            
            # 检查是否找到了内容
            if not result:
                # 列出所有可用学科，帮助诊断
                distinct_subjects = db.query(TextbookContent.subject).distinct().all()
                available_subjects = [item.subject for item in distinct_subjects]
                
                logger.warning(f"未找到相关教材内容: subject={subject}, semester={semester}, units={unit_list}")
                logger.info(f"可用的学科有: {available_subjects}")
                
                return JSONResponse(content={
                    "success": True,
                    "content": f"在数据库中找不到\"{subject}\"的{semester}的{', '.join(unit_list)}内容。"
                })
            
            # 组合结果
            content = "\n\n".join([f"【{item.unit}】\n{item.content}" for item in result])
            
            logger.info(f"获取教材内容成功: 单元数={len(result)}, 内容长度={len(content)}")
            
            return JSONResponse(content={
                "success": True,
                "content": content
            })
        except Exception as db_error:
            logger.error(f"数据库查询错误: {str(db_error)}")
            return JSONResponse(
                status_code=500, 
                content={"success": False, "message": f"数据库查询错误: {str(db_error)}"}
            )
        
    except Exception as e:
        logger.error(f"获取教材内容失败: {str(e)}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        return JSONResponse(
            status_code=500, 
            content={"success": False, "message": f"获取教材内容失败: {str(e)}"}
        )

@router.post("/generate")  # 路由路径正确
async def generate_exam(
    req: ExamRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """生成试题接口"""
    try:
        # 优化判断逻辑，增加更详细的日志
        is_content_mode = req.referenceContent and req.referenceContent.strip() != ""
        logger.info(f"出题模式判断: 参考内容存在={bool(req.referenceContent)}, 参考内容非空={bool(req.referenceContent and req.referenceContent.strip() != '')}")
        logger.info(f"出题模式: {'按内容出题' if is_content_mode else '按科目出题'}")
        
        # 题型数量检查 (通用验证)
        has_questions = any(count > 0 for count in req.questionTypes.values())
        if not has_questions:
            raise HTTPException(status_code=400, detail="请至少选择一种题型")
        
        # 只有在按科目出题模式下才检查科目选择
        if not is_content_mode:
            # 按科目出题模式的验证
            if not req.scopeSelection or len(req.scopeSelection) < 3:
                raise HTTPException(status_code=400, detail="请选择考试范围到科目级别")
            if not req.bookType:
                raise HTTPException(status_code=400, detail="请选择上册或下册")
            if not req.selectedUnits or len(req.selectedUnits) == 0:
                raise HTTPException(status_code=400, detail="请至少选择一个单元")
                
            # 获取教材内容，使用精确匹配
            # 构建完整学科名称
            education = req.scopeSelection[0]  # 如 "小学"
            grade = req.scopeSelection[1]     # 如 "一年级"
            subject_name = req.scopeSelection[2]  # 如 "语文"
            full_subject = f"{education}{grade}{subject_name}"  # 组合为 "小学一年级语文"
            
            try:
                # 使用精确匹配查询
                textbook_contents = db.query(TextbookContent).filter(
                    TextbookContent.subject == full_subject,  # 精确匹配
                    TextbookContent.semester == req.bookType,
                    TextbookContent.unit.in_(req.selectedUnits)
                ).all()
                
                # 如果找到了教材内容，则合并作为参考资料
                if textbook_contents:
                    textbook_content = "\n\n".join([f"【{item.unit}】\n{item.content}" for item in textbook_contents])
                    req.referenceContent = (req.referenceContent or "") + "\n\n教材内容参考:\n" + textbook_content
                    logger.info(f"找到 {len(textbook_contents)} 条教材内容记录")
                else:
                    logger.warning(f"未找到教材内容: full_subject={full_subject}, semester={req.bookType}, units={req.selectedUnits}")
            except Exception as db_error:
                logger.error(f"查询教材内容出错: {str(db_error)}")
                # 继续使用用户提供的参考内容
        else:
            # 按内容出题模式下，使用用户提供的参考内容
            logger.info("使用参考资料出题模式，不进行科目验证，参考内容长度: " + str(len(req.referenceContent)))
            if not req.referenceContent or req.referenceContent.strip() == "":
                raise HTTPException(status_code=400, detail="请提供参考内容")

        # 构建学科范围字符串
        subject_scope = ""
        if req.scopeSelection and len(req.scopeSelection) >= 3:
            subject_scope = "".join(req.scopeSelection)  # 合并完整的选择路径
            if req.bookType:
                subject_scope += req.bookType
            if req.selectedUnits and len(req.selectedUnits) > 0:
                units_text = "，".join(req.selectedUnits[:3])
                if len(req.selectedUnits) > 3:
                    units_text += f"等{len(req.selectedUnits)}个单元"
                subject_scope += f"（{units_text}）"
        elif is_content_mode:
            # 按内容出题模式下，如果没有选择科目，使用一个通用标识
            subject_scope = "按内容出题"
        
        # 处理考查范围
        selected_topics = []
        if req.selectedTopics:
            if "所有内容" in req.selectedTopics:
                selected_topics = ["所有内容"]
            else:
                selected_topics = req.selectedTopics
        
        # 整理其他参数
        requirements = req.requirements if req.requirements else ""
        reference_content = req.referenceContent if req.referenceContent else ""
        
        # 日志记录
        logger.info(f"用户 {current_user.get('username')} 请求生成试题: " +
                   f"模式={'按内容出题' if is_content_mode else '按科目出题'}, " +
                   f"范围={subject_scope}, 题型数量={req.questionTypes}, " +
                   f"参考内容长度={len(reference_content)}")

        # 创建流式响应
        return StreamingResponse(
            generate_exam_questions(
                subject_scope=subject_scope,
                selected_topics=selected_topics,
                requirements=requirements,
                question_types=req.questionTypes,
                reference_content=reference_content
            ),
            media_type="text/event-stream"
        )
    
    except Exception as e:
        logger.error(f"生成试题失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成试题失败: {str(e)}")
