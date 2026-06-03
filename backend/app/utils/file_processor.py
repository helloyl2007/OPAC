import os
import subprocess
from pathlib import Path
import tempfile
from app.utils.logger import logger

def extract_text_from_file(file_path):
    """从不同类型的文件中提取文本内容"""
    file_ext = os.path.splitext(file_path)[1].lower()
    
    try:
        if file_ext == '.txt':
            # 处理txt文件
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
                
        elif file_ext == '.pdf':
            # 使用pdftotext处理PDF文件
            # 注意：需要安装pdftotext工具
            try:
                with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as temp_file:
                    temp_file_path = temp_file.name
                
                # 使用subprocess调用pdftotext
                subprocess.run(['pdftotext', file_path, temp_file_path], check=True)
                
                # 读取提取的文本
                with open(temp_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
                
                # 删除临时文件
                os.unlink(temp_file_path)
                return text
            except Exception as e:
                logger.error(f"PDF处理失败: {str(e)}")
                # 如果pdftotext不可用，尝试使用PyPDF2等库
                try:
                    import PyPDF2
                    with open(file_path, 'rb') as f:
                        pdf_reader = PyPDF2.PdfReader(f)
                        text = ""
                        for page_num in range(len(pdf_reader.pages)):
                            text += pdf_reader.pages[page_num].extract_text()
                        return text
                except ImportError:
                    return "无法处理PDF文件，请安装PyPDF2或pdftotext工具。"
                
        elif file_ext in ['.doc', '.docx']:
            # 使用textract处理Word文档
            try:
                import textract
                text = textract.process(file_path).decode('utf-8')
                return text
            except ImportError:
                # 如果textract不可用，尝试使用python-docx
                try:
                    if file_ext == '.docx':
                        import docx
                        doc = docx.Document(file_path)
                        return "\n".join([para.text for para in doc.paragraphs])
                    else:
                        return "无法处理DOC文件，请安装textract库。"
                except ImportError:
                    return "无法处理Word文件，请安装python-docx或textract库。"
        else:
            return f"不支持的文件类型: {file_ext}"
    
    except Exception as e:
        logger.error(f"提取文件内容失败: {str(e)}")
        return f"提取文件内容失败: {str(e)}"
