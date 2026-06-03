import os
import shutil
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta
import asyncio
import threading

logger = logging.getLogger(__name__)

class ResourceManager:
    """资源管理器 - 负责清理临时文件和优化存储空间"""
    
    def __init__(self):
        self._cleanup_running = False
        self._cleanup_thread = None
        self._temp_dirs = set()
        
        # 清理阈值和间隔配置
        self.cleanup_interval = 28800  # 清理检查间隔，默认8小时
        self.temp_expiry_hours = 48  # 临时文件超时时间，默认48小时
        self.expired_content_days = 120  # 内容文件过期时间，默认120天
        
        # 文件路径配置
        self.temp_directories = [
            "static/ppt_upload/pdf_tmp",
            "static/ppt_upload/ppt_img_tmp"
        ]
        self.content_directories = [
            "static/generated/videos",
            "static/thumbnails"
        ]
        
    def register_temp_directory(self, directory: str):
        """注册需要清理的临时目录"""
        if os.path.exists(directory):
            self._temp_dirs.add(directory)
            logger.info(f"已注册临时目录: {directory}")
        else:
            logger.warning(f"临时目录不存在，无法注册: {directory}")
            
    def start_cleanup_thread(self):
        """启动后台清理线程"""
        if self._cleanup_running:
            logger.warning("清理线程已在运行")
            return False
            
        self._cleanup_running = True
        self._cleanup_thread = threading.Thread(
            target=self._run_cleanup_loop, 
            daemon=True,
            name="ResourceCleanupThread"
        )
        self._cleanup_thread.start()
        logger.info("资源清理线程已启动")
        return True
        
    def _run_cleanup_loop(self):
        """运行清理循环"""
        logger.info("开始资源清理循环")
        while self._cleanup_running:
            try:
                # 执行清理操作
                self.cleanup_temp_files()
                self.cleanup_expired_content()
                
            except Exception as e:
                logger.error(f"资源清理发生错误: {str(e)}")
                
            # 等待下一次清理周期
            time.sleep(self.cleanup_interval)
            
    def stop_cleanup_thread(self):
        """停止清理线程"""
        self._cleanup_running = False
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5.0)
        logger.info("资源清理线程已停止")
    
    def cleanup_temp_files(self):
        """清理临时文件"""
        cleanup_count = 0
        expiry_time = datetime.now() - timedelta(hours=self.temp_expiry_hours)
        
        # 清理已注册的临时目录
        for temp_dir in self._temp_dirs:
            if os.path.exists(temp_dir):
                try:
                    logger.info(f"清理临时目录: {temp_dir}")
                    shutil.rmtree(temp_dir)
                    os.makedirs(temp_dir, exist_ok=True)
                    cleanup_count += 1
                    logger.info(f"已清理并重新创建临时目录: {temp_dir}")
                except Exception as e:
                    logger.error(f"清理临时目录失败 {temp_dir}: {str(e)}")
        
        # 清理系统配置的临时目录中的过期文件
        for directory in self.temp_directories:
            if not os.path.exists(directory):
                continue
                
            try:
                for item in os.listdir(directory):
                    item_path = os.path.join(directory, item)
                    
                    # 跳过目录
                    if os.path.isdir(item_path):
                        continue
                        
                    # 检查文件修改时间
                    file_mod_time = datetime.fromtimestamp(os.path.getmtime(item_path))
                    if file_mod_time < expiry_time:
                        try:
                            os.remove(item_path)
                            cleanup_count += 1
                        except Exception as e:
                            logger.error(f"删除过期文件失败 {item_path}: {str(e)}")
            except Exception as e:
                logger.error(f"处理目录失败 {directory}: {str(e)}")
                
        logger.info(f"临时文件清理完成，共清理 {cleanup_count} 项")
        return cleanup_count
        
    def cleanup_expired_content(self):
        """清理过期内容文件"""
        cleanup_count = 0
        expiry_time = datetime.now() - timedelta(days=self.expired_content_days)
        
        # 检查是否有database connection可以查询文件是否仍在使用
        # 这里只进行简单的基于时间的清理
        
        for directory in self.content_directories:
            if not os.path.exists(directory):
                continue
                
            try:
                for item in os.listdir(directory):
                    item_path = os.path.join(directory, item)
                    
                    # 跳过目录和特殊文件
                    if os.path.isdir(item_path) or ".gitkeep" in item:
                        continue
                        
                    # 检查文件修改时间
                    try:
                        file_mod_time = datetime.fromtimestamp(os.path.getmtime(item_path))
                        # 只删除过期的文件
                        if file_mod_time < expiry_time:
                            # 检查文件是否可以访问(不被锁定)
                            if os.access(item_path, os.R_OK | os.W_OK):
                                file_size = os.path.getsize(item_path)
                                os.remove(item_path)
                                cleanup_count += 1
                                logger.info(f"已删除过期文件: {item_path}, 大小: {file_size/1024:.2f} KB")
                    except Exception as e:
                        logger.error(f"处理文件失败 {item_path}: {str(e)}")
            except Exception as e:
                logger.error(f"处理目录失败 {directory}: {str(e)}")
                
        logger.info(f"内容文件清理完成，共清理 {cleanup_count} 项")
        return cleanup_count
        
    def create_temp_directory(self, prefix="temp_"):
        """创建临时目录并注册到清理列表"""
        temp_dir = os.path.join("static", "temp", f"{prefix}{int(time.time())}")
        os.makedirs(temp_dir, exist_ok=True)
        self._temp_dirs.add(temp_dir)
        return temp_dir
        
    async def cleanup_on_request(self, session_id: str):
        """根据会话ID清理相关资源"""
        if not session_id:
            logger.warning("无效会话ID，跳过清理")
            return 0
        
        cleanup_count = 0
        
        # 1. 清理基础文件
        paths_to_check = [
            f"static/ppt_upload/{session_id}_info.json",
            f"static/ppt_upload/pdf_tmp/{session_id}.pdf",
        ]
        
        # 2. 清理目录
        directories_to_check = [
            f"static/ppt_upload/ppt_img_tmp/{session_id}_slides"
        ]
        
        # 3. 清理与会话ID相关的视频文件（通过名称匹配）
        video_directories = [
            "static/generated/videos"
        ]
        
        # 先处理基础文件
        for path in paths_to_check:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    cleanup_count += 1
                    logger.info(f"已删除会话文件: {path}")
                except Exception as e:
                    logger.error(f"删除会话文件失败 {path}: {str(e)}")
        
        # 处理目录
        for directory in directories_to_check:
            if os.path.exists(directory):
                try:
                    shutil.rmtree(directory)
                    cleanup_count += 1
                    logger.info(f"已删除会话目录: {directory}")
                except Exception as e:
                    logger.error(f"删除会话目录失败 {directory}: {str(e)}")
        
        # 处理可能以会话ID开头的视频文件
        for video_dir in video_directories:
            if os.path.exists(video_dir):
                try:
                    for filename in os.listdir(video_dir):
                        # 判断文件是否与会话ID相关（以会话ID为前缀，或包含会话ID）
                        if filename.startswith(f"{session_id}_") or f"_{session_id}" in filename or f"draft_{session_id}" in filename:
                            file_path = os.path.join(video_dir, filename)
                            try:
                                os.remove(file_path)
                                cleanup_count += 1
                                logger.info(f"已删除相关视频文件: {file_path}")
                                
                                # 同时检查并删除可能的缩略图
                                thumbnail_path = os.path.join("static", "thumbnails", f"{os.path.splitext(filename)[0]}.jpg")
                                if os.path.exists(thumbnail_path):
                                    os.remove(thumbnail_path)
                                    cleanup_count += 1
                                    logger.info(f"已删除相关缩略图: {thumbnail_path}")
                            except Exception as e:
                                logger.error(f"删除相关文件失败 {file_path}: {str(e)}")
                except Exception as e:
                    logger.error(f"处理视频目录失败 {video_dir}: {str(e)}")
        
        logger.info(f"会话 {session_id} 资源清理完成，共删除 {cleanup_count} 项")
        return cleanup_count

# 创建全局资源管理器实例
resource_manager = ResourceManager()
