import os
import subprocess
import logging
import hashlib
import re
import tempfile
from PIL import Image

logger = logging.getLogger(__name__)

def extract_ppt_thumbnail(ppt_path, output_dir, filename):
    """
    使用LibreOffice提取PPT第一页作为缩略图
    
    Args:
        ppt_path: PPT文件绝对路径
        output_dir: 缩略图输出目录绝对路径
        filename: 原PPT文件名
    
    Returns:
        str: 生成的缩略图路径(相对于static目录)
    """
    try:
        logger.info(f"开始提取PPT缩略图，参数：")
        logger.info(f"PPT路径: {ppt_path}")
        logger.info(f"输出目录: {output_dir}")
        logger.info(f"文件名: {filename}")
        
        # 检查文件是否存在
        if not os.path.exists(ppt_path):
            logger.error(f"PPT文件不存在: {ppt_path}")
            return None
            
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 使用哈希值创建唯一安全的文件名，避免中文和特殊字符问题
        safe_filename = generate_safe_filename(filename)
        thumbnail_filename = f"{safe_filename}.jpg"
        thumbnail_path = os.path.join(output_dir, thumbnail_filename)
        
        # 创建临时目录用于存放导出的图片
        with tempfile.TemporaryDirectory() as temp_dir:
            # 使用LibreOffice将PPT导出为图片
            # 使用绝对路径，确保LibreOffice能找到文件
            cmd = [
                'soffice',  # 或者使用'libreoffice'，取决于系统配置
                '--headless',
                '--convert-to', 'jpg',
                '--outdir', temp_dir,
                ppt_path  # 使用绝对路径
            ]
            
            logger.info(f"执行LibreOffice命令: {' '.join(cmd)}")
            
            # 执行命令
            process = subprocess.run(cmd, capture_output=True, text=True)
            
            # 检查命令执行是否成功
            if process.returncode != 0:
                logger.error(f"LibreOffice命令执行失败，返回码: {process.returncode}")
                logger.error(f"错误输出: {process.stderr}")
                # 尝试不同的命令
                alternative_cmd = [
                    'libreoffice',
                    '--headless',
                    '--convert-to', 'jpg',
                    '--outdir', temp_dir,
                    ppt_path
                ]
                logger.info(f"尝试替代命令: {' '.join(alternative_cmd)}")
                process = subprocess.run(alternative_cmd, capture_output=True, text=True)
                if process.returncode != 0:
                    logger.error(f"替代命令也失败了: {process.stderr}")
                    return None
            
            # 列出临时目录中的所有文件，帮助调试
            temp_files = os.listdir(temp_dir)
            logger.info(f"临时目录中的文件: {temp_files}")
            
            if not temp_files:
                logger.error("临时目录为空，LibreOffice未生成任何文件")
                return None
                
            # 找到临时目录中生成的图片文件
            # 由于可能有中文路径问题，我们查找任何jpg文件
            jpg_files = [f for f in temp_files if f.lower().endswith('.jpg')]
            
            if not jpg_files:
                logger.error(f"在临时目录中没有找到jpg文件")
                return None
                
            # 使用找到的第一个jpg文件
            exported_path = os.path.join(temp_dir, jpg_files[0])
            logger.info(f"找到导出的图片: {exported_path}")
            
            # 使用PIL调整大小并保存为标准尺寸
            with Image.open(exported_path) as img:
                # 调整为16:9的标准尺寸
                img = img.resize((800, 450), Image.LANCZOS)
                img.save(thumbnail_path, "JPEG", quality=90)
            
            logger.info(f"成功创建缩略图并保存到: {thumbnail_path}")
            
            # 返回相对于static目录的路径
            return f"/thumbnails/ppt_thumb/{thumbnail_filename}"
            
    except Exception as e:
        logger.error(f"提取PPT缩略图失败: {str(e)}", exc_info=True)
        return None

def generate_safe_filename(original_filename):
    """
    生成安全的文件名，避免中文和特殊字符问题
    """
    # 提取文件名（不含扩展名）
    basename = os.path.splitext(os.path.basename(original_filename))[0]
    
    # 使用MD5生成哈希值
    filename_hash = hashlib.md5(basename.encode('utf-8')).hexdigest()[:12]
    
    # 提取ASCII部分
    ascii_part = re.sub(r'[^a-zA-Z0-9]', '', basename)[:10]
    
    # 组合安全文件名
    safe_name = f"{filename_hash}_{ascii_part}" if ascii_part else filename_hash
    
    return safe_name
