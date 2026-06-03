import os
import logging
import asyncio
import time
import uuid
import numpy as np
from typing import List, Dict, Optional
from PIL import Image
from moviepy.editor import ImageClip, concatenate_videoclips, AudioFileClip, CompositeAudioClip
from app.utils.tts import text_to_speech
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建线程池执行器，用于并行处理图片
# 线程池大小为CPU核心数×2，适合IO密集型任务
thread_pool = ThreadPoolExecutor(max_workers=os.cpu_count() * 2)

# 自定义 ImageClip 函数，确保尺寸为偶数并优化临时文件处理
def create_even_sized_clip(img_path, duration, temp_dir=None):
    """创建具有偶数宽高的图片剪辑，优化临时文件处理"""
    try:
        # 先用 PIL 打开图片，确保宽高为偶数
        with Image.open(img_path) as img:
            width, height = img.size
            
            # 检查并调整为偶数尺寸
            if width % 2 != 0:
                width -= 1
            if height % 2 != 0:
                height -= 1
                
            # 如果尺寸有变化，调整图片
            if img.size != (width, height):
                img = img.resize((width, height), Image.LANCZOS)
                
                # 使用传入的临时目录或默认的static/generated/temp
                if not temp_dir:
                    temp_dir = "static/generated/temp"
                    os.makedirs(temp_dir, exist_ok=True)
                
                # 创建临时文件名
                temp_filename = f"temp_{os.path.basename(img_path)}"
                temp_path = os.path.join(temp_dir, temp_filename)
                
                # 以最佳品质保存图片
                img.save(temp_path, quality=95, optimize=True)
                
                # 使用临时文件创建剪辑
                return ImageClip(temp_path, duration=duration), temp_path
        
        # 如果不需要调整，直接使用原图
        return ImageClip(img_path, duration=duration), None
    except Exception as e:
        logger.error(f"处理图片 {img_path} 失败: {str(e)}")
        raise

# 并行处理图片函数
def process_image(args):
    """在线程池中处理单个图片"""
    img_path, duration, temp_dir = args
    try:
        clip, temp_file = create_even_sized_clip(img_path, duration, temp_dir)
        return clip, temp_file
    except Exception as e:
        logger.error(f"并行处理图片 {img_path} 失败: {str(e)}")
        return None, None

async def generate_audio(text, output_path, voice_type="aixia", temp_dir="static/generated/temp"):
    """生成音频文件 - 使用阿里云TTS"""
    try:
        # 确保临时目录存在（虽然阿里云TTS不需要，但为了保持一致性）
        os.makedirs(temp_dir, exist_ok=True)
        
        # 调用阿里云TTS函数转换文本到语音
        logger.info(f"生成阿里云TTS音频: {output_path}, 音色: {voice_type}")
        success = await text_to_speech(
            text=text, 
            output_path=output_path, 
            voice=voice_type,
            temp_dir=temp_dir  # 不会使用但保持接口一致性
        )
        
        # 检查文件是否成功生成
        if success and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info(f"阿里云TTS音频生成成功: {output_path}, 大小: {os.path.getsize(output_path)} 字节")
            return {
                "success": True,
                "path": output_path
            }
        else:
            logger.error(f"阿里云TTS生成音频失败: {output_path}")
            return {
                "success": False,
                "error": "阿里云TTS生成音频文件失败"
            }
    except Exception as e:
        logger.error(f"阿里云TTS生成音频失败: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

async def generate_video(
    image_paths: List[str], 
    output_path: str, 
    notes: List[str] = None,
    slide_duration: int = 5,
    voice_type: str = "zh-CN-YunyangNeural",
    progress_callback = None
) -> Dict:
    """
    根据图片生成视频
    
    参数:
        image_paths: 图片路径列表
        output_path: 输出视频路径
        notes: 每张图片的解说文字
        slide_duration: 每张图片显示时长(秒)
        voice_type: 语音类型
        progress_callback: 进度回调函数，传入参数为(当前步骤,总步骤,消息)
    
    返回:
        成功状态和相关信息
    """
    # 创建临时目录用于存放处理过程中的文件
    temp_dir = "static/generated/temp"
    os.makedirs(temp_dir, exist_ok=True)
    
    # 为当前会话创建唯一子文件夹以避免冲突
    session_id = f"video_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    temp_dir = os.path.join(temp_dir, session_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    temp_files = []  # 跟踪所有临时文件
    
    try:
        logger.info(f"开始生成视频，共{len(image_paths)}张图片")
        
        # 检查路径有效性
        for path in image_paths:
            if not os.path.exists(path):
                return {"success": False, "error": f"图片路径不存在: {path}"}
                
        # 确保notes列表长度与图片数量一致
        if notes:
            if len(notes) < len(image_paths):
                notes.extend([""] * (len(image_paths) - len(notes)))
            elif len(notes) > len(image_paths):
                notes = notes[:len(image_paths)]
        else:
            notes = [""] * len(image_paths)
        
        # 改进的进度计算
        notes_count = sum(1 for note in notes if note and note.strip())
        image_steps = len(image_paths)
        audio_steps = notes_count
        video_steps = 4
        total_steps = image_steps + audio_steps + video_steps
        
        current_step = 0
        
        # 上次更新进度的时间，用于控制刷新频率
        last_progress_update = time.time()
        progress_update_interval = 1.0  # 进度更新间隔，单位为秒
        
        # 更新进度的辅助函数，带有频率限制
        async def update_progress(step, total, message):
            nonlocal last_progress_update
            current_time = time.time()
            if progress_callback and (current_time - last_progress_update >= progress_update_interval or step == total):
                await progress_callback(step, total, message)
                last_progress_update = current_time
                
        # 首先为每个幻灯片生成音频，并计算所需的持续时间
        logger.info("开始生成音频并计算持续时间")
        slide_durations = []  # 存储每张幻灯片最终的持续时间
        audio_files = []      # 存储生成的音频文件路径
        
        for i, note in enumerate(notes):
            # 默认使用设定的持续时间
            duration = slide_duration
            audio_path = None
            
            # 如果有解说文本，生成音频
            if note and note.strip():
                try:
                    # 更新进度
                    current_step += 1
                    await update_progress(current_step, total_steps, f"生成音频 {i+1}/{notes_count}")
                    
                    # 生成唯一的音频文件名
                    audio_filename = f"slide_{i+1}_{int(time.time())}.mp3"
                    audio_path = os.path.join(temp_dir, audio_filename)
                    temp_files.append(audio_path)
                    
                    # 执行文本到语音转换，确保传递临时目录
                    audio_result = await generate_audio(
                        text=note, 
                        output_path=audio_path, 
                        voice_type=voice_type,
                        temp_dir=temp_dir
                    )
                    
                    if not audio_result["success"]:
                        logger.warning(f"语音生成失败: {audio_result.get('error', '未知错误')}")
                        logger.warning(f"将使用默认时长 {duration} 秒")
                        audio_path = None
                    else:
                        # 确保文件存在且可读
                        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                            # 获取音频持续时间，并确保幻灯片持续时间不小于音频时长
                            try:
                                audio_clip = AudioFileClip(audio_path)
                                audio_duration = audio_clip.duration
                                audio_clip.close()  # 关闭以释放资源
                                
                                # 确保幻灯片持续时间足够长以容纳音频
                                duration = max(duration, audio_duration + 1)  # 额外1秒用于缓冲
                                logger.info(f"幻灯片 {i+1}，音频长度 {audio_duration:.2f} 秒，最终持续时间 {duration:.2f} 秒")
                            except Exception as e:
                                logger.error(f"读取音频文件失败: {str(e)}")
                                audio_path = None
                        else:
                            logger.error(f"音频文件生成失败或为空: {audio_path}")
                            audio_path = None
                        
                except Exception as e:
                    logger.error(f"语音生成出错: {str(e)}")
                    audio_path = None
            
            # 保存幻灯片持续时间和音频文件路径
            slide_durations.append(duration)
            audio_files.append(audio_path)
        
        # 并行处理图片 - 现在使用计算好的持续时间
        logger.info("开始并行处理图片")
        await update_progress(current_step, total_steps, "准备处理图片...")
        
        # 准备并行处理的参数，使用计算好的持续时间
        processing_args = [(img_path, slide_durations[i], temp_dir) for i, img_path in enumerate(image_paths)]
        
        # 使用线程池并行处理图片
        processed_clips = list(thread_pool.map(process_image, processing_args))
        
        # 更新进度
        current_step += len(image_paths)
        await update_progress(current_step, total_steps, f"完成图片处理: {len(processed_clips)}/{len(image_paths)}")
        
        # 处理结果
        clips = []
        total_duration = 0
        
        for i, ((clip, temp_file), audio_path) in enumerate(zip(processed_clips, audio_files)):
            if temp_file:
                temp_files.append(temp_file)
            
            if clip is None:
                logger.error(f"图片 {i+1} 处理失败，跳过")
                continue
                
            clips.append(clip)
            
            # 使用音频文件创建音频剪辑
            if audio_path and os.path.exists(audio_path):
                audio_clip = AudioFileClip(audio_path)
                # 将音频添加到对应的视频剪辑
                clip = clip.set_audio(audio_clip)
                # 更新剪辑
                clips[-1] = clip
            
            # 更新总时长
            total_duration += slide_durations[i]
        
        # 更新进度 - 视频预处理
        current_step += 1
        await update_progress(current_step, total_steps, "视频预处理中...")
            
        # 合并所有图片剪辑
        try:
            # 检查所有剪辑的尺寸是否一致，如果不一致，将它们调整为相同的尺寸
            if len(clips) > 1:
                target_size = clips[0].size
                logger.info(f"统一所有剪辑尺寸为: {target_size}")
                for i in range(1, len(clips)):
                    if clips[i].size != target_size:
                        clips[i] = clips[i].resize(target_size)
            
            # 更新进度 - 合成视频帧
            current_step += 1
            await update_progress(current_step, total_steps, "合成视频帧...")
            
            video = concatenate_videoclips(clips, method="compose")
            logger.info(f"视频剪辑合并成功，最终视频尺寸: {video.size}")
            
        except Exception as e:
            logger.error(f"合并视频剪辑失败: {str(e)}")
            return {"success": False, "error": f"合并视频剪辑失败: {str(e)}"}
        
        # 我们现在已经将音频添加到了各个剪辑，所以跳过原来的音频处理步骤
        # 但仍然更新进度计数器以保持总步骤数一致
        current_step += 2
        
        # 确保输出路径有正确的扩展名
        if not output_path.lower().endswith('.mp4'):
            output_path = os.path.splitext(output_path)[0] + '.mp4'
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 更新进度 - 导出视频文件
        current_step += 1
        await update_progress(current_step, total_steps, "导出视频文件...")
        
        # 写入视频文件 - 使用兼容Windows Media Player的参数
        logger.info(f"写入视频文件: {output_path}")
        video.write_videofile(
            output_path, 
            fps=24, 
            codec="libx264",
            audio_codec="aac", 
            bitrate="2000k", 
            audio_bitrate="128k",
            ffmpeg_params=[
                "-pix_fmt", "yuv420p",      # 使用常见的像素格式
                "-profile:v", "main",       # 使用主配置文件
                "-level", "3.1",            # 兼容级别
                "-movflags", "+faststart"   # 优化Web流媒体传输
            ],
            logger=None  # 禁用moviepy内部日志以减少输出噪音
        )
        
        # 关闭视频对象
        video.close()
        
        # 最终进度更新
        await update_progress(total_steps, total_steps, "视频生成完成")
            
        logger.info(f"视频生成完成: {output_path}")
        return {
            "success": True, 
            "output_path": output_path,
            "duration": total_duration
        }
        
    except Exception as e:
        logger.error(f"视频生成失败: {str(e)}", exc_info=True)
        return {"success": False, "error": str(e)}
    finally:
        # 清理所有临时文件
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logger.debug(f"已删除临时文件: {temp_file}")
            except Exception as e:
                logger.warning(f"删除临时文件失败: {temp_file}, 错误: {str(e)}")
        
        # 删除临时目录
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug(f"已删除临时目录: {temp_dir}")
        except Exception as e:
            logger.warning(f"删除临时目录失败: {temp_dir}, 错误: {str(e)}")
