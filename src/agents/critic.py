from __future__ import annotations

from src.agents.base import BaseWorkflowAgent
from src.models import ResumePackage, ScoreCard, SessionState
from src.utils.json_utils import extract_json_object


REFLECTION_PROMPTS = {
    "initial": """
你是严格的技术简历审稿人。请根据证据上下文审稿并输出改进后的严格 JSON，不要输出 Markdown。

任务：
{task}
""",
    "reflect": """
请审查下面这版简历优化结果，重点检查：
1. 每个事实是否能在证据上下文中找到依据
2. 是否把用户没说过的工具、指标、耗时、部署、模型对比或实验结论写成事实
3. 是否把“不知道、没有统计、没有记录”的内容包装成了成果
4. 不确定内容是否放进 missing_info 或 next_actions，而不是正文
5. 简历 bullet 是否具体、真实、便于面试追问

原始任务：
{task}

当前回答：
{content}

如果无需改进，回复“无需改进”。否则给出具体修改意见。
""",
    "refine": """
请根据反馈改写上一版。只输出严格 JSON，不要输出 Markdown，不要解释。

原始任务：
{task}

上一版：
{last_attempt}

反馈：
{feedback}
""",
}


class ResumeCriticAgent(BaseWorkflowAgent):
    name = "证据审核Agent"
    system_prompt = (
        "你是严格的技术面试官和事实审核员。你的任务不是把简历写得更华丽，"
        "而是根据证据上下文删除虚构、降级不确定表述，并保留真实可讲的项目内容。"
    )

    def review_and_refine(
        self,
        session: SessionState,
        package: ResumePackage,
        notes_summary: str = "",
    ) -> ResumePackage:
        evidence_context = self._build_evidence_context(session, package, notes_summary)
        reflected = self._reflect_package(session, package, evidence_context)
        reviewed = self._review_score(session, reflected, evidence_context)
        reflected.score_card = reviewed
        return reflected

    def _build_evidence_context(
        self,
        session: SessionState,
        package: ResumePackage,
        notes_summary: str,
    ) -> str:
        return self.runtime.build_context(
            user_query=f"审核 {session.project_name} 的简历优化包是否忠于用户证据",
            system_instructions=(
                "下面是唯一可作为事实依据的证据上下文。审核时只能引用这些证据。"
                "如果简历内容没有被这里支持，就必须删除、降级，或放入 missing_info/next_actions。"
            ),
            packets=[
                (self._session_evidence(session), {"type": "user_session_evidence"}),
                (notes_summary or "NoteTool 暂无额外记录。", {"type": "note_tool_evidence"}),
                (self._package_snapshot(package), {"type": "resume_package_to_review"}),
            ],
            max_tokens=7000,
        )

    def _reflect_package(
        self,
        session: SessionState,
        package: ResumePackage,
        evidence_context: str,
    ) -> ResumePackage:
        task = f"""
请基于证据上下文审稿并改进这个简历项目优化包。必须保持 JSON 字段和原结构一致。

证据上下文：
{evidence_context}

审核对象：
{package.model_dump()}

硬性要求：
1. 简历正文、bullet、技术亮点、架构流程、结果价值，只能写证据上下文支持的内容。
2. 证据上下文没有出现的工具、库名、指标、耗时、部署方式、并发、缓存、模型对比、实验结论，一律不能写成已完成事实。
3. 如果用户回答里出现“大概、左右、可能、不知道、没有、没统计、没记录”，必须保留不确定性，不能改写成确定成果。
4. 对于没有证据或证据不足的内容：
   - 从 resume_summary、resume_bullets、technical_highlights、architecture_points、quantified_results 中删除或降级；
   - 放入 missing_info 或 next_actions；
   - 在 reflection_notes 里说明“已根据证据上下文移除或降级不确定内容”。
5. 可以润色表达，但不能新增事实。
6. 只输出严格 JSON，不要输出解释。
"""
        text = self.runtime.run_reflection(
            name=self.name,
            task=task,
            custom_prompts=REFLECTION_PROMPTS,
            max_iterations=2,
        )
        data = extract_json_object(text)
        if not data:
            package.reflection_notes.append("证据审核Agent未返回可解析 JSON，保留改写初稿。")
            return package
        try:
            refined = ResumePackage.model_validate(data)
            refined.reflection_notes.append("已经过证据上下文审稿。")
            return refined
        except Exception:
            package.reflection_notes.append("证据审核Agent返回结构不完整，保留改写初稿。")
            return package

    def _review_score(
        self,
        session: SessionState,
        package: ResumePackage,
        evidence_context: str,
    ) -> ScoreCard:
        prompt = f"""
请基于证据上下文审核这个简历项目优化结果，只输出 JSON：
{{
  "clarity": 0-10,
  "technical_depth": 0-10,
  "business_impact": 0-10,
  "interview_readiness": 0-10,
  "notes": ["具体问题或优点"]
}}

证据上下文：
{evidence_context}

优化结果：
{package.model_dump()}

评分规则：
- 如果简历结果仍包含证据上下文没有支持的事实，interview_readiness 不得超过 6。
- 如果缺少真实效果数据，business_impact 不得超过 6。
- 如果 missing_info 中仍有关键缺口，请在 notes 中指出。
"""
        data = self.run_json(prompt)
        if data:
            try:
                return ScoreCard.model_validate(data)
            except Exception:
                pass
        return package.score_card

    def _session_evidence(self, session: SessionState) -> str:
        rounds = "\n".join(
            (
                f"- 阶段：{record.stage}\n"
                f"  问题：{record.question}\n"
                f"  用户回答：{record.answer}"
            )
            for record in session.rounds
        ) or "暂无追问回答"
        return f"""
项目名称：{session.project_name}
目标岗位：{session.target_role}
技术栈：{session.tech_stack or "未填写"}
用户原始描述：
{session.rough_description}

用户追问回答：
{rounds}
"""

    def _package_snapshot(self, package: ResumePackage) -> str:
        return f"""
当前简历优化包 JSON：
{package.model_dump()}
"""
