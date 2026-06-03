import asyncio
import logging
import uuid
import time
from typing import Dict, Callable, Any, Optional
import threading
import traceback
import functools

logger = logging.getLogger(__name__)

# 简单的任务状态跟踪器
class TaskManager:
    def __init__(self):
        self.tasks = {}  # 存储任务信息
        self.lock = threading.Lock()  # 线程锁，用于保护任务字典
        
    def create_task(self, func, *args, **kwargs) -> str:
        """创建并启动一个后台任务"""
        task_id = str(uuid.uuid4())
        
        # 包装任务函数，以确保参数被正确闭包
        @functools.wraps(func)
        async def task_wrapper():
            try:
                self.update_task_status(task_id, "running")
                # 将参数深拷贝到此处，确保在线程间传递
                captured_args = list(args)
                captured_kwargs = dict(kwargs)
                
                # 记录任务参数，确保参数被正确传递
                logger.info(f"执行任务 {task_id} - 参数: {captured_args}, 关键字参数: {captured_kwargs}")
                
                result = await func(*captured_args, **captured_kwargs)
                self.update_task_status(task_id, "completed", result=result)
                return result
            except Exception as e:
                error_msg = str(e)
                stack_trace = traceback.format_exc()
                logger.error(f"Task {task_id} failed: {error_msg}\n{stack_trace}")
                self.update_task_status(task_id, "failed", error=error_msg)
                raise
        
        # 确保在新线程中获取到当前参数
        def run_in_thread():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                task = loop.create_task(task_wrapper())
                loop.run_until_complete(task)
                loop.close()
            except Exception as e:
                logger.error(f"Thread execution error: {str(e)}", exc_info=True)
        
        # 记录初始任务状态
        with self.lock:
            self.tasks[task_id] = {
                "status": "pending",
                "created": time.time(),
                "result": None,
                "error": None
            }
        
        # 启动线程
        thread = threading.Thread(target=run_in_thread)
        thread.daemon = True  # 守护线程，不会阻止程序退出
        thread.start()
        logger.info(f"后台任务已启动: {task_id}")
        
        return task_id
    
    def update_task_status(self, task_id: str, status: str, **kwargs):
        """更新任务状态"""
        if task_id not in self.tasks:
            logger.warning(f"尝试更新不存在的任务状态: {task_id}")
            return False
        
        with self.lock:
            self.tasks[task_id].update({
                "status": status,
                "updated": time.time(),
                **kwargs
            })
            logger.info(f"任务 {task_id} 状态已更新为: {status}")
        return True
    
    def get_task_status(self, task_id: str) -> Dict:
        """获取任务状态"""
        with self.lock:
            if task_id not in self.tasks:
                logger.warning(f"尝试获取不存在的任务状态: {task_id}")
                return {"status": "not_found"}
            return self.tasks.get(task_id)
    
    def cleanup_old_tasks(self, max_age_hours=24):
        """清理旧任务记录"""
        now = time.time()
        max_age_secs = max_age_hours * 3600
        
        with self.lock:
            for task_id in list(self.tasks.keys()):
                if now - self.tasks[task_id]["created"] > max_age_secs:
                    del self.tasks[task_id]
                    logger.info(f"已清理旧任务: {task_id}")

# 创建全局任务管理器实例
task_manager = TaskManager()
