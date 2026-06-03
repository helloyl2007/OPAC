import os
import logging
import json
import http.client
import urllib.parse
import time
from typing import Dict, Any, Optional
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
import tempfile

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 阿里云 TTS 配置 
ALI_TTS_CONFIG = {
    '': '',  # 替换为你的阿里云Access Key ID
    '': '',  # 替换为你的阿里云Access Key Secret
    'region': 'cn-shanghai',  # 使用标准区域
    'host': 'nls-gateway.cn-shanghai.aliyuncs.com',  
    'format': 'mp3',
    'sample_rate': 16000
}

# 简化音色配置 - 直接使用阿里云的原生音色名称
VOICE_OPTIONS = {
    'zhiyan_emo': '知燕（女）',
    'zhimao': '猫小美（女）',
    'zhishuo': '知哥（男）',
    'aishuo': '艾硕（男）',
    'zhibei_emo': '知贝（童）',
    'jielidou': '杰力豆（童）',
    'qingqing': '青青（童）',
    'sicheng': '标准男声',
    'geyou': '磁性男声',
    'zhiwei': '女童声'
}

# 用于缓存token
_token_cache = {
    'token': None,
    'expire_time': 0
}

def get_ali_token() -> str:
    """
    获取阿里云访问令牌，带缓存功能，避免频繁请求
    
    返回:
        有效的访问令牌
    """
    # 检查缓存的令牌是否有效（提前5分钟刷新）
    current_time = int(time.time())
    if _token_cache['token'] and _token_cache['expire_time'] > current_time + 300:
        logger.debug("使用缓存的阿里云令牌")
        return _token_cache['token']
    
    try:
        logger.info("获取新的阿里云访问令牌")
        # 创建AcsClient实例
        client = AcsClient(
            ALI_TTS_CONFIG[''],
            ALI_TTS_CONFIG[''],
            ALI_TTS_CONFIG['region']
        )
        
        # 创建request，并设置参数 - 使用正确的元数据服务域名
        request = CommonRequest()
        request.set_method('POST')
        request.set_domain('nls-meta.cn-shanghai.aliyuncs.com')
        request.set_version('2019-02-28')
        request.set_action_name('CreateToken')
        request.set_protocol_type('https')  # 明确指定使用HTTPS协议
        
        logger.info(f"开始请求阿里云Token，域名: {request.get_domain()}, 区域: {ALI_TTS_CONFIG['region']}")
        
        # 发送请求
        response = client.do_action_with_exception(request)
        jss = json.loads(response)
        
        if 'Token' in jss and 'Id' in jss['Token']:
            token = jss['Token']['Id']
            expire_time = jss['Token']['ExpireTime']
            
            # 更新缓存
            _token_cache['token'] = token
            _token_cache['expire_time'] = expire_time
            
            logger.info(f"成功获取阿里云令牌，有效期至: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expire_time))}")
            return token
        else:
            logger.error(f"获取阿里云令牌失败，响应格式不正确: {jss}")
            return ""
            
    except Exception as e:
        logger.error(f"获取阿里云令牌失败: {str(e)}")
        return ""

async def text_to_speech(text, output_path, voice="aixia", rate="+0%", pitch="+0Hz", temp_dir=None):
    """
    将文本转换为语音 - 使用阿里云TTS服务
    
    参数:
        text (str): 要转换的文本
        output_path (str): 输出MP3文件路径
        voice (str): 阿里云音色名称
        rate (str): 不使用, 保留参数兼容性
        pitch (str): 不使用, 保留参数兼容性
        temp_dir (str): 临时目录, 不使用但保留参数兼容性
    
    返回:
        bool: 是否成功
    """
    try:
        # 确保输出目录存在
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # 记录临时目录信息但不使用
        if temp_dir:
            logger.info(f"收到临时目录参数: {temp_dir}，但阿里云TTS不需要使用")
        
        # 直接调用阿里云TTS服务
        result = await ali_tts(text, output_path, voice)
        
        # 验证生成结果
        if result and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info(f"已生成阿里云TTS语音文件: {output_path}")
            return True
        else:
            logger.error(f"阿里云TTS语音生成失败: {output_path}")
            return False
        
    except Exception as e:
        logger.error(f"阿里云TTS语音生成失败: {str(e)}")
        return False

async def ali_tts(text: str, output_path: str, voice: str) -> bool:
    """
    使用阿里云TTS服务将文本转换为语音
    
    参数:
        text: 要转换的文本
        output_path: 输出语音文件路径
        voice: 阿里云音色名称，如 xiaoxiao, aixia, sicheng 等
        
    返回:
        成功状态
    """
    try:
        # 确保临时和输出目录存在
        temp_dir = "static/generated/temp"
        os.makedirs(temp_dir, exist_ok=True)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 直接使用提供的音色名称，如果未提供则默认使用 aixia
        ali_voice = voice if voice else 'aixia'
        
        # 检查音色是否在支持列表中
        if ali_voice not in VOICE_OPTIONS:
            logger.warning(f"未知的音色名称: {ali_voice}，将使用默认音色 aixia")
            ali_voice = 'aixia'
            
        logger.info(f"使用阿里云音色: {ali_voice} ({VOICE_OPTIONS.get(ali_voice, '未知音色')})")
        
        # 获取有效的token
        token = get_ali_token()
        if not token:
            logger.error("无法获取有效的阿里云令牌")
            return False
        
        # URL编码处理文本
        text_urlencode = urllib.parse.quote_plus(text)
        text_urlencode = text_urlencode.replace("+", "%20")
        text_urlencode = text_urlencode.replace("*", "%2A")
        text_urlencode = text_urlencode.replace("%7E", "~")
        
        # 获取配置
        host = ALI_TTS_CONFIG['host']
        format = ALI_TTS_CONFIG['format']
        sample_rate = ALI_TTS_CONFIG['sample_rate']
        
        # 创建连接
        conn = http.client.HTTPSConnection(host)
        
        # 基于官方示例，实现POST请求的方式
        # 设置请求头
        http_headers = {
            'Content-Type': 'application/json'
        }
        
        # 设置请求体 - 按照官方示例的格式
        body = {
            'appkey': '5FHcDVOK7CuuO96m', 
            'token': token, 
            'text': text, 
            'format': format, 
            'sample_rate': sample_rate,
            'voice': ali_voice
        }
        body_json = json.dumps(body)
        
        logger.debug(f"阿里云TTS请求体: {body_json}")
        
        # 发送请求
        url = '/stream/v1/tts'  # 使用正确的API路径
        conn.request(method='POST', url=url, body=body_json, headers=http_headers)
        
        # 处理响应
        response = conn.getresponse()
        logger.info(f"阿里云TTS响应状态: {response.status} {response.reason}")
        
        content_type = response.getheader('Content-Type')
        response_body = response.read()
        
        # 检查响应是否是音频
        if 'audio/mpeg' == content_type or 'audio/wav' == content_type:
            with open(output_path, mode='wb') as f:
                f.write(response_body)
            logger.info('阿里云TTS请求成功!')
            conn.close()
            return True
        else:
            try:
                error_msg = response_body.decode('utf-8')
                logger.error(f'阿里云TTS请求失败: {error_msg}')
            except:
                logger.error(f'阿里云TTS请求失败，无法解析错误信息')
            conn.close()
            return False
            
    except Exception as e:
        logger.error(f"阿里云TTS服务调用失败: {str(e)}")
        return False
