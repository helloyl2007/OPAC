import os
import json
import shutil
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches
from app.utils.logger import logger 

class TemplateManager:
    """PPT模板管理器"""
    
    def __init__(self, templates_dir):
        """初始化模板管理器"""
        self.templates_dir = templates_dir
        self.config_path = os.path.join(templates_dir, 'templates.json')
        self.templates = []
        
        # 确保目录结构存在
        os.makedirs(templates_dir, exist_ok=True)
        os.makedirs(os.path.join(templates_dir, 'previews'), exist_ok=True)
        
        # 加载模板配置
        self._load_templates()
    
    def _load_templates(self):
        """加载模板配置"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.templates = json.load(f)
            except Exception as e:
                print(f"无法加载模板配置: {str(e)}")
                self.templates = []
    
    def _save_templates(self):
        """保存模板配置"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.templates, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存模板配置失败: {str(e)}")
            return False
    
    def get_all_templates(self):
        """获取所有可用模板"""
        return self.templates
    
    def get_template(self, template_id):
        """根据ID获取模板文件路径"""
        for template in self.templates:
            if template['id'] == template_id:
                # 构建并返回绝对路径，确保使用正斜杠
                template_path = os.path.join(self.templates_dir, template['file_name']).replace("\\", "/")
                return template_path
        return None
    
    def add_template(self, name, file_path, preview_path=None):
        """添加新模板"""
        # 生成唯一ID
        template_id = str(len(self.templates) + 1)
        
        # 确定文件名和预览图路径
        file_name = f"template_{template_id}.pptx"
        dest_path = os.path.join(self.templates_dir, file_name)
        
        # 复制模板文件
        shutil.copy2(file_path, dest_path)
        
        # 处理预览图
        preview_rel_path = None
        if preview_path:
            preview_ext = Path(preview_path).suffix
            preview_dest = os.path.join(self.templates_dir, 'previews', f"{template_id}{preview_ext}")
            shutil.copy2(preview_path, preview_dest)
            preview_rel_path = f"/static/templates/previews/{template_id}{preview_ext}"
        else:
            # 默认预览图
            preview_rel_path = f"/static/templates/previews/{template_id}.jpg"
        
        # 添加到配置
        self.templates.append({
            'id': template_id,
            'name': name,
            'preview': preview_rel_path,
            'file_name': file_name
        })
        
        # 保存配置
        self._save_templates()
        
        return template_id
    
    def remove_template(self, template_id):
        """删除模板"""
        for i, template in enumerate(self.templates):
            if template['id'] == template_id:
                # 删除文件
                file_path = os.path.join(self.templates_dir, template['file_name'])
                if os.path.exists(file_path):
                    os.remove(file_path)
                
                # 删除预览图
                preview_path = template['preview'].replace('/static', '')
                if os.path.exists(preview_path):
                    os.remove(preview_path)
                
                # 从配置移除
                self.templates.pop(i)
                self._save_templates()
                return True
        
        return False
