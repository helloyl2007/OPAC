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

# 出题系统提示词
SYSTEM_PROMPT = """
你是一位经验丰富的教学专家，擅长编写试题。你会得到我提供给你的相应年级的某学科考察的一些不同知识点，同时会得到为你提供的单选题、多选题、填空题、判断题、解答题和拔高题的数量需求。
所有题目内容要符合中国大陆的教育体系和考试要求，模拟真实试卷的题目内容和形式。
如果在数据库中找不到相应的内容，只需用红色字提示:“⚠️没有相关单元的内容哦！请检查一下选项是否正确❤️😊。”，不需要再出题。
"""

async def generate_exam_questions(
    subject_scope: str,
    selected_topics: list, 
    requirements: str, 
    question_types: dict,
    reference_content: str = ""
):
    """生成试题内容，支持流式输出"""
    
    # 添加日志，确认收到的参数
    logger.info(f"生成试题函数收到参数: subject_scope={subject_scope}, selected_topics={selected_topics}, requirements={requirements}")
    logger.info(f"参考资料内容长度: {len(reference_content) if reference_content else 0}")
    
    # 确保 selected_topics 和 requirements 有值
    selected_topics = selected_topics if selected_topics else []
    requirements = requirements if requirements else ""
    
    # 构造基础提示词
    base_prompt = """请为我生成一套试题，具体要求如下：\n\n"""
    
    # 根据是否有参考资料构建不同的提示词
    if reference_content and len(reference_content.strip()) > 0:
        user_prompt = base_prompt
        if subject_scope:
            user_prompt += f"学科范围：{subject_scope}；出题类型：{selected_topics};\n"
        
        user_prompt += f"""{selected_topics}；\n\n
参考资料内容：
{reference_content}

题目形式及数量：
{', '.join([f"{get_question_type_name(qtype)}：{count}道" for qtype, count in question_types.items() if count > 0])}

具体要求：{requirements or "请基于参考资料内容出题，题目类型为，确保题目紧密结合资料中的知识点。题目难度要合理，解答要详细。"}

请以上述参考资料为重点内容出题，确保题目紧密结合参考资料中的知识点和内容。
"""
    else:
        # 原有的基于学科范围的提示词逻辑
        user_prompt = f"""{base_prompt}
学科范围：{subject_scope}
出题类型：{', '.join(selected_topics)}

出题形式及数量：
{', '.join([f"{get_question_type_name(qtype)}：{count}道" for qtype, count in question_types.items() if count > 0])}

具体要求：{requirements or "请遵循标准出题规范，题目难度适中，涵盖所选学科范围的核心知识点，按指定的出题类型出题。"}
"""

    user_prompt += """
请按照出题形式分组，依次输出题目、选项（如有）、答案和解析，题目类型要丰富。
如果是英语科目的题目，请使用中文出题。
如果是语文科目的题目，所有题目形式只按指定的出题类型出题，包括单选、多选、填空等；如果出题类型为“所有内容”，根据{subject_scope}的内容范畴，出题类型需包拼音、组词、阅读理解、默写、作文等题型。
如果是数学科目的题目，所有题目形式只按指定的出题类型出题，包括单选、多选、填空等；如果出题类型为“所有内容”，根据{subject_scope}的内容范畴，出题类型需包含计算、应用题、几何等题型，其中加为“+”，减为“-”，乘为“*”，除为“/”。
用markdown输出，格式要求如下：
1. 每种题型使用二级标题，如"## 一、单选题"
2. 每道题目使用三级标题编号，如"### 1. 题目内容"
3. 选择题选项展示形式：
    A. 选项内容 
    B. 选项内容
    C. 选项内容
    D. 选项内容
4. 答案和解析使用引用格式：
   > 答案：B
   > 解析：详细的解析内容
5. 题目之间使用分隔线分隔
6. 确保输出内容清晰规范,适合阅读和编辑
7. 如果题目形式里包含解答题，则在数学科目中改为“应用题”；在语文科目中改为“阅读理解”，阅读理解一般提供100字左右的一段文字（可以课内，也可以是课外），标出重点词、句，请学生去理解。
8. 题目中的重点字、词、句要用下划线标出。

**数学符号LaTeX格式要求：**
- 分数使用：$\\frac{分子}{分母}$，如 $\\frac{1}{2}$
- 根号使用：$\\sqrt{内容}$，如 $\\sqrt{16}$
- 平方根使用：$\\sqrt[n]{内容}$，如 $\\sqrt[3]{8}$
- 次方使用：$x^2$、$2^3$等
- 下标使用：$x_1$、$a_n$等
- 大于等于：$\\geq$，小于等于：$\\leq$
- 不等于：$\\neq$
- 乘法：$\\times$，除法：$\\div$
- 角度：$\\angle$，度数：$^\\circ$
- 圆周率：$\\pi$
- 无穷大：$\\infty$
- 求和：$\\sum$，积分：$\\int$
- 三角函数：$\\sin$、$\\cos$、$\\tan$等
- 绝对值：$|x|$
- 几何图形可以用：△ABC（三角形）、⊙O（圆）、∠ABC（角）等

请根据需求依次给出题目和答案解析。如果提供了参考资料，请重点根据参考资料内容来出题，确保题目贴合参考资料的核心知识点。
"""

    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            stream=True,
        )
        
        async for chunk in response:
            if chunk.choices[0].delta.content is not None:
                yield f"data: {json.dumps({'choices': [{'delta': {'content': chunk.choices[0].delta.content}}]})}\n\n"
        
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error(f"生成试题内容失败: {str(e)}")
        raise Exception(f"生成试题内容失败: {str(e)}")

def get_question_type_name(question_type):
    """将题目类型代码转换为中文名称"""
    type_mapping = {
        'singleChoice': '单选题',
        'multipleChoice': '多选题',
        'fillBlank': '填空题',
        'trueFalse': '判断题',
        'shortAnswer': '解答题',
        'advanced': '拔高题'
    }
    return type_mapping.get(question_type, question_type)
