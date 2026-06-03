import os
import shutil
from datetime import datetime

class FileStorage:
    """文件存储服务"""
    
    def __init__(self, base_dir):
        self.base_dir = base_dir
        
    def get_file_path(self, filename, sub_dir=''):
        """获取文件路径，确保使用正斜杠"""
        # 确保子目录使用正斜杠
        sub_dir = sub_dir.replace('\\', '/')
        
        # 构建并确保目录存在
        dir_path = os.path.join(self.base_dir, sub_dir)
        os.makedirs(dir_path, exist_ok=True)
        
        # 返回绝对路径，但保持正斜杠格式
        return os.path.join(dir_path, filename).replace('\\', '/')
    
    def save_file(self, file_object, filename, sub_dir=''):
        """保存文件并返回保存路径（使用正斜杠）"""
        file_path = self.get_file_path(filename, sub_dir)
        
        # 写入文件
        with open(file_path, 'wb') as f:
            if hasattr(file_object, 'read'):
                # 如果是文件对象，直接读取
                f.write(file_object.read())
            elif isinstance(file_object, bytes):
                # 如果是字节内容，直接写入
                f.write(file_object)
            else:
                raise TypeError("Unsupported file object type")
        
        # 返回相对路径（不含base_dir），并确保使用正斜杠
        rel_path = os.path.join(sub_dir, filename).replace('\\', '/')
        return rel_path
    
    def copy_file(self, src_path, dest_filename, sub_dir=''):
        """复制文件并返回新路径（使用正斜杠）"""
        dest_path = self.get_file_path(dest_filename, sub_dir)
        shutil.copy2(src_path, dest_path)
        
        # 返回相对路径（不含base_dir），并确保使用正斜杠
        rel_path = os.path.join(sub_dir, dest_filename).replace('\\', '/')
        return rel_path
    
    def delete_file(self, file_path):
        """删除文件"""
        abs_path = os.path.join(self.base_dir, file_path)
        if os.path.exists(abs_path):
            os.remove(abs_path)
            return True
        return False
