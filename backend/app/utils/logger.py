import logging
import os
from datetime import datetime

# 确保日志目录存在
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(log_dir, f'app_{datetime.now().strftime("%Y%m%d")}.log'), 
            encoding='utf-8'
        )
    ]
)

logger = logging.getLogger('edu_system')
