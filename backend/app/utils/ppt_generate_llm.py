from openai import AsyncOpenAI
from app.core.config import settings
from app.utils.logger import logger
from app.utils.bailian_adapter import AsyncBailianClient
import json

# 根据配置选择使用的客户端
if settings.BAILIAN_APP_ID:
    # 使用百练智能体应用
    client = AsyncBailianClient(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_API_BASE
    )
else:
    # 使用原有的OpenAI客户端
    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_API_BASE
    )

async def generate_ppt_outline(topic: str, review_points: str, common_mistakes: str, next_points: str, grade:str, subject:str):
    """生成PPT提纲和内容，支持流式输出"""
    prompt = f"""请按照以下结构生成一个用于视频讲解的PPT内容，内容可以详细和口语化一些：

主题：{topic}
1. 复习要点：{review_points}
2. 普遍错题：{common_mistakes}
3. 下一节要点：{next_points}

请基于课本{topic}的内容，总结{review_points}复习要点，和与{review_points}有关的{common_mistakes}错题的原因和解析，基于{next_points}生成要点，生成一个PPT提纲和内容。

完全按照以下格式返回JSON代码，不能包含"```json"等备注，注意："//"符号后的为提示词，不需要输出，desc中的每个小标题需要保留（如“知识点1：”，“知识点2：”），contents里的每一点都需要举个有趣的例子来辅助解释说明，格式如下：
{{
    "topic": "{topic}",
    "pages": [
        {{
            "title": "一、复习要点",
            "pages": [
                {{
                    "sub_title": "核心知识点",
                    "desc": [
                        "知识点1：""//+10个字以内的概括",
                        "知识点2：""//+10个字以内的概括",
                        "知识点3：""//+10个字以内的概括"
                    ],
                    "contents": [
                        "//展开描述知识点1的具体内容，30-40字。",
                        "//展开描述知识点2的具体内容，30-40字。",
                        "//展开描述知识点3的具体内容，30-40字。"
                    ]
                }},
                {{
                    "sub_title": "学习技巧",
                    "desc": [
                        "技巧要点1：""//+10个字以内的概括",
                        "技巧要点2：""//+10个字以内的概括",
                        "技巧要点3：""//+10个字以内的概括"
                    ],
                    "contents": [
                        "//技巧要点1的具体方法说明1，30-40字",
                        "//技巧要点2的具体方法说明2，30-40字",
                        "//技巧要点3的具体方法说明3，30-40字"
                    ]
                }},
                {{
                    "sub_title": "典型例子",
                    "desc": [
                        "例子场景1：""//+10个字以内的概括",
                        "例子场景2：""//+10个字以内的概括",
                        "例子场景3：""//+10个字以内的概括"
                    ],
                    "contents": [
                        "//具体例子1，30-40字",
                        "//具体例子2，30-40字",
                        "//具体例子3，30-40字"
                    ]
                }}
            ]
        }},
        {{
            "title": "二、错题突破",
            "pages": [
                {{
                    "sub_title": "普遍错误",
                    "desc": [
                        "错误类型1：""//+10个字以内的概括",
                        "错误类型2：""//+10个字以内的概括",
                        "错误类型3：""//+10个字以内的概括"
                    ],
                    "contents": [
                        "//错误类型1的具体分析，要解释错在哪里，30-40字",
                        "//错误类型2的具体分析，要解释错在哪里，30-40字",
                        "//错误类型3的具体分析，要解释错在哪里，30-40字"
                    ]
                }},
                {{
                    "sub_title": "错题解析",
                    "desc": [
                        "解析要点1：""//+根据上面的错误类型1进行解析，10个字以内的概括",
                        "解析要点2：""//+根据上面的错误类型2进行解析，10个字以内的概括",
                        "解析要点3：""//+根据上面的错误类型3进行解析，10个字以内的概括"
                    ],
                    "contents": [
                        "//具体解析要点1，要有详细的思路和方法，30-40字",
                        "//具体解析要点2，要有详细的思路和方法，30-40字",
                        "//具体解析要点3，要有详细的思路和方法，30-40字"
                    ]
                }}
            ]
        }},
        {{
            "title": "三、下一节准备",
            "pages": [
                {{
                    "sub_title": "下一节准备",
                    "desc": [
                        "学习目标：""//+10个字以内的概括",
                        "预习重点：""//+10个字以内的概括"
                    ],
                    "contents": [
                        "//悬念式提问，引起学生兴趣，30-40字",
                        "//预习建议，30-40字"
                    ]
                }}
            ]
        }}
    ]
}}"""

    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {
                    "role": "system", 
                    "content": f"你是一位有丰富教学经验的{grade}{subject}老师。请用通俗易懂、生动有趣的语言给学生讲解复习内容和技巧，需举例子时，优先引用课本{topic}相关内容。"
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=2000,
            stream=True,
        )
        
        async for chunk in response:
            if chunk.choices[0].delta.content is not None:
                # 使用更简洁的格式
                yield f"data: {json.dumps({'choices': [{'delta': {'content': chunk.choices[0].delta.content}}]})}\n\n"
        
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error(f"生成PPT内容失败: {str(e)}")
        raise Exception(f"生成PPT内容失败: {str(e)}")