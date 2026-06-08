from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.agents.base import BaseWorkflowAgent, split_tech_stack
from src.models import InterviewQuestion, ProjectAnalysis, ResumeBullet, ResumePackage, ScoreCard, SessionState


class ResumeWriterAgent(BaseWorkflowAgent):
    name = "简历改写Agent"
    system_prompt = (
        "你是技术简历写作专家。你会把项目材料改写成真实、具体、技术导向的简历表达。"
        "要求：只能基于用户材料和项目分析写作；不新增用户没有说过的事实；"
        "每条经历尽量以动作开头；突出职责、技术方案和结果。"
    )

    def write_package(self, session: SessionState, analysis: ProjectAnalysis) -> ResumePackage:
        prompt = f"""
根据项目分析结果生成简历项目优化包。只输出严格 JSON，字段必须完整。

项目名称：{session.project_name}
目标岗位：{session.target_role}
用户原始描述：{session.rough_description}
用户填写技术栈：{session.tech_stack or "未填写"}
用户追问回答：
{self._format_user_answers(session)}
分析结果：{analysis.model_dump()}

硬性事实规则：
1. 简历正文、bullet、技术亮点、架构流程、结果价值，只能写用户原始描述、技术栈、追问回答或分析结果中已有的事实。
2. 不要自行补充用户没有提供的工具、库名、指标、耗时、部署方式、实验结论或对比结论。
3. 没有真实数字时，不要编写看似精确的量化成果。
4. 想建议用户补强的内容，只能放入 missing_info 或 next_actions，不能写成已完成。
5. 如果信息不足，宁可写得保守，也不要写得像真的。

JSON 字段：
{{
  "project_name": "...",
  "target_role": "...",
  "positioning": "一句话项目定位",
  "resume_summary": "简历项目简介，80-140字",
  "resume_bullets": [
    {{"text": "简历 bullet", "focus": "突出点", "why_it_works": "为什么有效"}}
  ],
  "technical_highlights": ["技术亮点"],
  "architecture_points": ["架构/流程点"],
  "quantified_results": ["结果；没有真实数字就写可验证结果"],
  "interview_questions": [
    {{"question": "面试官可能问什么", "answer_strategy": "回答策略"}}
  ],
  "missing_info": ["仍需补充的信息"],
  "score_card": {{
    "clarity": 0,
    "technical_depth": 0,
    "business_impact": 0,
    "interview_readiness": 0,
    "notes": ["评分说明"]
  }},
  "next_actions": ["下一步补强建议"],
  "reflection_notes": []
}}
"""
        data = self.run_json(prompt)
        if data:
            try:
                package = ResumePackage.model_validate(data)
                return package
            except ValidationError:
                pass
        return self._fallback(session, analysis)

    def _format_user_answers(self, session: SessionState) -> str:
        if not session.rounds:
            return "暂无"
        return "\n".join(f"- {record.answer}" for record in session.rounds if record.answer.strip()) or "暂无"

    def _fallback(self, session: SessionState, analysis: ProjectAnalysis) -> ResumePackage:
        techs = analysis.technical_stack or split_tech_stack(session.tech_stack)
        tech_text = "、".join(techs[:3]) if techs else "待补充技术栈"
        result = analysis.results or ["暂未提供真实量化结果，建议补充演示记录、输出样例或人工验收结论后再写入简历。"]

        bullets = [
            ResumeBullet(
                text=(
                    f"围绕「{session.project_name}」的项目目标，整理输入场景、核心功能和输出结果，"
                    "形成可用于简历展示和面试说明的项目描述。"
                ),
                focus="项目概括",
                why_it_works="基于用户提供材料表达项目目标，不引入未证实指标。",
            ),
            ResumeBullet(
                text=(
                    f"基于已确认技术信息（{tech_text}）描述项目实现路径，"
                    "将未提供证据的库名、阈值、耗时和模型对比结论标记为待补充。"
                ),
                focus="技术边界",
                why_it_works="既保留技术方向，也避免把猜测内容写成已完成事实。",
            ),
            ResumeBullet(
                text=(
                    "根据项目材料拆分已完成事实、缺失证据和后续补强项，"
                    "保证简历表述真实、可解释且方便面试追问。"
                ),
                focus="真实表达",
                why_it_works="主动暴露信息边界，降低面试时被追问穿帮的风险。",
            ),
        ]

        return ResumePackage(
            project_name=session.project_name,
            target_role=session.target_role,
            positioning=f"围绕「{session.project_name}」的真实项目材料进行简历表达优化。",
            resume_summary=(
                f"{session.project_name} 是一个基于用户已提供材料整理的项目经历。"
                f"当前已确认技术信息包括 {tech_text}。"
                "简历表达只保留已确认事实，未提供证据的指标、工具和实验结论会进入补充建议。"
            ),
            resume_bullets=bullets,
            technical_highlights=[f"已确认技术信息：{tech}" for tech in techs[:4]] or ["技术栈仍需补充"],
            architecture_points=[
                "根据用户材料整理项目输入、核心处理流程和输出结果",
                "将未提供证据的实现细节标记为待确认，避免写入简历正文",
            ],
            quantified_results=result,
            interview_questions=[
                InterviewQuestion(
                    question="这个项目中哪些功能是你已经实现的，哪些只是后续计划？",
                    answer_strategy="先讲用户材料中已经明确提供的功能，再把缺少证据的库、指标和优化项说明为待补充或后续计划。",
                ),
                InterviewQuestion(
                    question="如果面试官追问项目效果，你有哪些真实证据？",
                    answer_strategy="只回答已提供的演示结果、样例或数据；如果没有真实指标，就说明目前缺少量化数据，后续会补充测试记录。",
                ),
                InterviewQuestion(
                    question="这个项目最需要补充哪类技术细节？",
                    answer_strategy="结合 missing_info 回答，例如技术栈版本、核心模块、质量评估方式、运行截图或测试样例。",
                ),
            ],
            missing_info=analysis.missing_info,
            score_card=ScoreCard(
                clarity=8 if not analysis.missing_info else 6,
                technical_depth=7,
                business_impact=6,
                interview_readiness=7 if not analysis.missing_info else 5,
                notes=["当前版本适合形成简历初稿；补充真实指标后说服力会更强。"],
            ),
            next_actions=[
                "补充真实技术栈版本、核心模块和运行方式",
                "补充可验证效果，如输出样例、演示截图、人工验收结论或真实测试数据",
                "准备 2 分钟项目介绍和 3 个技术追问答案",
            ],
        )
