"""
测试百练API适配器
"""
import asyncio
import sys
import os

# 添加项目根路径到sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.bailian_adapter import AsyncBailianClient
from app.core.config import settings

async def test_bailian_api():
    """测试百练API调用"""
    try:
        client = AsyncBailianClient()
        
        messages = [
            {"role": "system", "content": ""},
            {"role": "user", "content": "请先理解三年级语文《读不完的大书》的内容，生成一份完整教案"}
        ]
        
        # 测试流式调用
        print("\n测试流式调用...")
        response_stream = await client.chat.completions.create(
            messages=messages,
            stream=True
        )
        
        content = ""
        async for chunk in response_stream:
            if chunk.choices[0].delta.content:
                content += chunk.choices[0].delta.content
                print(chunk.choices[0].delta.content, end="")
        
        print(f"\n流式调用成功！")
        
    except Exception as e:
        print(f"测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print(f"API Key: {settings.OPENAI_API_KEY[:10]}...")
    print(f"Base URL: {settings.OPENAI_API_BASE}")
    print(f"App ID: {settings.BAILIAN_APP_ID}")
    
    asyncio.run(test_bailian_api())