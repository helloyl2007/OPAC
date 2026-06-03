from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50))
    password = Column(String(100))
    roles = Column(String(50)) 
    created_at = Column(DateTime)
    mobile = Column(String(30))
    status = Column(Integer)
    
    # 添加反向关系
    videos = relationship("VideoFile", back_populates="user")
    ppt_files = relationship("PPTFile", back_populates="user")

class PPTFile(Base):
    __tablename__ = "ppt_files"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)  # 使用英文文件名
    title = Column(String, nullable=False)     # 保留中文标题
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    thumbnail_path = Column(String, nullable=True)  # 缩略图路径
    file_path = Column(String, nullable=False)      # 文件存储路径
    file_size = Column(Integer, nullable=True)      # 文件大小
    status = Column(String, default="pending")      # 状态：pending, running, completed, failed
    task_id = Column(String, nullable=True)         # 任务ID，用于追踪后台任务
    error_message = Column(String, nullable=True)   # 错误信息
    
    # 添加关系
    user = relationship("User", back_populates="ppt_files")
    videos = relationship("VideoFile", back_populates="ppt")

# 添加视频文件模型
class VideoFile(Base):
    __tablename__ = "video_files"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)  # 原始PPT的文件名
    filepath = Column(String(512), nullable=False)  # 视频文件的存储路径
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ppt_id = Column(Integer, ForeignKey("ppt_files.id"), nullable=True)  # 可能关联到PPT文件
    status = Column(String, default="completed")  # 状态：completed, processing, failed
    duration = Column(Integer)  # 视频时长（秒）
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    session_id = Column(String)  # 存储生成时的会话ID
    meta_info = Column(Text, nullable=True)  # 存储进度和错误信息
    
    # 定义关系
    user = relationship("User", back_populates="videos")
    ppt = relationship("PPTFile", back_populates="videos")
    
    # 可以添加一个属性方法来确保返回的路径始终使用正斜杠
    @property
    def normalized_path(self):
        if self.filepath:
            return self.filepath.replace("\\", "/")
        return None

class TextbookContent(Base):
    __tablename__ = "textbook_content"
    
    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String, nullable=False)  # 学科
    semester = Column(String, nullable=False)  # 学期（上册/下册）
    unit = Column(String, nullable=False)      # 单元
    content = Column(Text, nullable=False)     # 内容