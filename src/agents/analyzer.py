from __future__ import annotations

from typing import Any

from src.agents.base import BaseWorkflowAgent, as_list, split_tech_stack
from src.models import ProjectAnalysis, SessionState


class ProjectAnalyzerAgent(BaseWorkflowAgent):
    name = "项目分析Agent"
    system_prompt = (
        "你是资深技术面试官和简历顾问。你擅长把学生的项目描述拆成背景、职责、"
        "技术难点、解决方案、结果、风险和缺失信息。必须实事求是，只能使用用户原始描述、"
        "技术栈和追问回答中明确出现的信息；不能编造不存在的工具、指标、耗时、阈值或实验结论。"
    )

    def analyze(self, session: SessionState, notes_summary: str = "") -> ProjectAnalysis:
        context = self.runtime.build_context(
            user_query=f"分析项目 {session.project_name} 的简历价值",
            system_instructions=self.system_prompt,
            packets=[
                (self._session_material(session), {"type": "project_material"}),
                (notes_summary, {"type": "tool_result"}),
            ],
            max_tokens=5200,
        )
        prompt = f"""
请基于下面上下文，输出严格 JSON。

{context}

事实约束：
1. 只能把用户材料中明确出现的内容写成事实。
2. 如果用户没有明确说使用某个库、阈值、校验方法、耗时、通过率、准确率或模型对比结果，不能写入 results/solutions/technical_stack。
3. 不确定的内容必须放入 missing_info 或 honesty_notes。
4. 不要把“可以做”“建议做”“未来可扩展”的内容写成已经完成。

JSON 字段：
{{
  "problem": "项目解决的问题",
  "scenario": "使用场景",
  "personal_role": ["个人职责1", "个人职责2"],
  "technical_stack": ["技术1", "技术2"],
  "technical_challenges": ["难点1", "难点2"],
  "solutions": ["解决方案1", "解决方案2"],
  "results": ["结果1", "结果2"],
  "risks": ["可能被面试追问或需要解释的风险"],
  "missing_info": ["仍缺失的信息"],
  "honesty_notes": ["哪些地方不能夸大"]
}}
"""
        data = self.run_json(prompt)
        if data:
            try:
                analysis = ProjectAnalysis.model_validate(self._normalize(data, session))
                return analysis
            except Exception:
                pass
        return self._fallback(session)

    def _session_material(self, session: SessionState) -> str:
        rounds = "\n".join(f"- {record.question}\n  {record.answer}" for record in session.rounds) or "暂无"
        return f"""
项目名称：{session.project_name}
目标岗位：{session.target_role}
技术栈：{session.tech_stack or "未填写"}
原始描述：{session.rough_description}
追问记录：
{rounds}
"""

    def _normalize(self, data: dict[str, Any], session: SessionState) -> dict[str, Any]:
        return {
            "problem": str(data.get("problem") or session.rough_description).strip(),
            "scenario": str(data.get("scenario") or "学习/项目实践/求职展示场景").strip(),
            "personal_role": as_list(data.get("personal_role")),
            "technical_stack": as_list(data.get("technical_stack")) or split_tech_stack(session.tech_stack),
            "technical_challenges": as_list(data.get("technical_challenges")),
            "solutions": as_list(data.get("solutions")),
            "results": as_list(data.get("results")),
            "risks": as_list(data.get("risks")),
            "missing_info": as_list(data.get("missing_info")),
            "honesty_notes": as_list(data.get("honesty_notes")),
        }

    def _fallback(self, session: SessionState) -> ProjectAnalysis:
        role_answers = [record.answer for record in session.rounds if record.stage == "role"]
        technical_answers = [record.answer for record in session.rounds if record.stage == "technical"]
        impact_answers = [record.answer for record in session.rounds if record.stage == "impact"]
        overview_answers = [record.answer for record in session.rounds if record.stage == "overview"]

        missing = []
        if not session.tech_stack.strip():
            missing.append("技术栈还不够明确")
        if not role_answers:
            missing.append("个人职责边界还不够明确")
        if not technical_answers:
            missing.append("技术难点和解决方案还不够明确")
        if not impact_answers:
            missing.append("缺少项目结果或可验证效果")

        return ProjectAnalysis(
            problem=overview_answers[-1] if overview_answers else session.rough_description,
            scenario="基于用户已提供项目材料整理的应用场景",
            personal_role=role_answers,
            technical_stack=split_tech_stack(session.tech_stack),
            technical_challenges=technical_answers,
            solutions=[],
            results=impact_answers,
            risks=["如果用户没有提供真实证据，不应编造百分比、用户规模、耗时、阈值、库名或模型对比结果"],
            missing_info=missing,
            honesty_notes=[
                "没有真实指标时，只写可验证结果，不写虚假量化数据",
                "没有明确说过的工具库、校验方法和实验结论不能当作已完成事实",
            ],
        )
