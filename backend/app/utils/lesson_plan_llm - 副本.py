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

# 更新系统提示词为表格化的教案格式
SYSTEM_PROMPT = """
如果用户输入的科目和课题不一致（如：语文、乘除法）则输出提示检查科目和课题。不再执下以下的输出操作。
你是一位经验丰富的教育专家，擅长编写教案。我需要你按照以下固定格式输出一份可执行的教案，注意这不是提纲或建议，尤其是教学过程的内容要具体细致。
"""

async def generate_lesson_plan(
    subject_scope: str,
    topic: str,
    plan_details: str,
    lesson_count: int = 1 
):
    """生成教案内容，支持流式输出"""
    
    try:
        user_prompt = f"""
请为以下课程生成教案：

学科范围：{subject_scope}
课题：{topic}
课时数：{lesson_count}
课时计划与要求：
{plan_details or "请按照教学大纲和课程标准进行规范化设计"}

请生成一份完整的教案，包含所有必要的教学环节。根据课时数{lesson_count}合理安排教学过程。
内容需要用网页表格的形式呈现，请必需使用html标签格式输出，不能带有“```html”标识，括号“（）”里的内容为提示词，不需要输出，格式如下：
"
<table>
    <tr>
        <td>教学内容</td>
        <td colspan="2">（填写课程主题，如与所选年级不符需提示）</td>
    </tr>
    <tr>
        <td>课时数</td>
        <td colspan="2">（总课时数，如2课时；可注明分课时安排，如"第一课时：XXX；第二课时：XXX"）</td>
    </tr>
    <tr>
        <td rowspan="4">教学目标</td>
        <td><strong>知识与技能</strong></td>
        <td>（具体描述学生需掌握的知识或技能）</td>
    </tr>
    <tr>
        <td>高频考题</td>
        <td>（历年对本课题出题较多的考试内容，并列举相应示例）</td>
    </tr>    
    <tr>
        <td>跨学科融合</td>
        <td>（将不同学科的知识点串联，包括语、数、英、科学、道法等）</td>
    </tr>
    <tr>
        <td>过程与方法</td>
        <td>（描述学习方法或活动形式）</td>
    </tr>
    <tr>
        <td>重点</td>
        <td colspan="2">（明确教学重点内容，如关键概念、核心技能等）</td>
    </tr>
    <tr>
        <td>难点</td>
        <td colspan="2">（指出教学难点及突破方法，如抽象概念、复杂操作等）</td>
    </tr>
    <tr>
        <td rowspan="2">教学准备</td>
        <td><strong>教具/材料</strong></td>
        <td>（如PPT、实验器材、视频等）</td>
    </tr>
    <tr>
        <td>学生预习</td>
        <td>（如阅读资料、准备工具等）</td>
    </tr>
    <tr>
        <td rowspan="2">教学过程</td>
        <td><strong>第一课时</strong></td>
        <td><strong>环节1</strong>：（活动名称+时长）<br>&nbsp;&nbsp;- 活动描述：（具体步骤）<br>&nbsp;&nbsp;- 设计意图：（说明活动目的）</td>
    </tr>
    <tr>
        <td>第二课时</td>
        <td><strong>环节1</strong>：...<br>（同第一课时结构）</td>
    </tr>
    <tr>
        <td>板书设计</td>
        <td colspan="2"><pre>（用思维导图方式描述板书框架）</pre></td>
    </tr>
    <tr>
        <td>课后反思</td>
        <td colspan="2">参考:<br>（提供课后填写改进建议）</td>
    </tr>
</table>     
"           
"""

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
        logger.error(f"生成教案内容失败: {str(e)}")
        raise Exception(f"生成教案内容失败: {str(e)}")
