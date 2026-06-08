from __future__ import annotations

from dataclasses import dataclass, field

from src.agents.base import BaseWorkflowAgent, as_list
from src.models import AnswerIntent, QuestionSource, RoundRecord, SessionState, Stage


STAGE_LABELS: dict[Stage, str] = {
    "overview": "项目定位",
    "role": "个人职责",
    "technical": "技术难点",
    "impact": "结果量化",
    "finalizing": "生成中",
    "done": "完成",
}


STAGE_GOALS: dict[Stage, list[str]] = {
    "overview": ["目标用户", "用户痛点", "项目目标", "核心产出"],
    "role": ["个人负责模块", "独立完成部分", "团队/教程提供部分", "个人贡献边界"],
    "technical": ["技术路线", "关键难点", "解决方案", "为什么这样设计"],
    "impact": ["最终效果", "可验证结果", "真实指标", "不能夸大的部分"],
    "finalizing": [],
    "done": [],
}


FALLBACK_QUESTIONS: dict[Stage, list[str]] = {
    "overview": [
        "这个项目主要面向哪些用户？他们原来遇到的痛点是什么？",
        "这个项目最终希望输出什么结果？比如简历 bullet、项目简介、面试追问，还是完整报告？",
        "用户使用这个项目时，从输入到输出的大致流程是什么？",
        "这个项目和普通的大模型聊天相比，最核心的差异是什么？",
    ],
    "role": [
        "这个项目中哪些模块是你亲自设计和实现的？",
        "有没有参考教程、开源项目或团队已有代码？如果有，你自己新增或改造了哪些部分？",
        "你负责的是前端、后端、Agent 流程、提示词、数据存储，还是部署？请具体说。",
        "如果面试官问你的个人贡献边界，你会怎么说明？",
    ],
    "technical": [
        "这个项目最核心的技术流程是什么？请按输入、处理、输出讲一下。",
        "你是如何调用大模型 API 的？模型输入了什么，输出又如何被程序使用？",
        "项目里最容易出错或最难控制的一点是什么？你怎么处理？",
        "这个项目里 hello_agents 具体承担了哪些能力？",
    ],
    "impact": [
        "这个项目目前能稳定生成哪些内容？请列出可演示的结果。",
        "有没有可以量化或验证的效果？比如生成耗时、问答轮数、输出字段完整度。",
        "如果没有真实数据，你准备如何在简历里诚实表达项目效果？",
        "这个项目下一步最值得补强的功能是什么？",
    ],
}


@dataclass(frozen=True)
class StageDecision:
    question: str
    question_source: QuestionSource
    stage_complete: bool
    reason: str
    answer_intent: AnswerIntent = "unknown"
    contains_useful_info: bool = False
    useful_facts: list[str] = field(default_factory=list)
    unknown_parts: list[str] = field(default_factory=list)


class DiscoveryAgent(BaseWorkflowAgent):
    name = "项目追问Agent"
    system_prompt = (
        "你是简历项目挖掘专家。你通过短问题追问用户，目标是把一个普通项目挖掘成"
        "真实、具体、能被面试展开的简历项目。不要一次问很多问题。"
        "你还要判断当前阶段的信息是否已经足够写入简历。"
    )

    def next_question(self, session: SessionState, stage: Stage) -> str:
        return self.decide_stage(session, stage, answered_count=0, max_rounds=4, min_rounds=2).question

    def next_question_with_source(self, session: SessionState, stage: Stage) -> tuple[str, QuestionSource]:
        decision = self.decide_stage(session, stage, answered_count=0, max_rounds=4, min_rounds=2)
        return decision.question, decision.question_source

    def decide_stage(
        self,
        session: SessionState,
        stage: Stage,
        answered_count: int,
        max_rounds: int,
        min_rounds: int,
    ) -> StageDecision:
        fallback = self._fallback_question(stage, answered_count, session)
        current_answers = self._format_stage_rounds(session, stage)
        latest_record = self._latest_stage_record(session, stage)
        latest_answer_block = self._format_latest_answer(latest_record)
        prompt = f"""
请一次性完成两件事：
1. 理解用户最近一次回答的意图和有效信息；
2. 判断当前阶段的信息是否足够写简历，并决定是否继续追问。

项目名称：{session.project_name}
目标岗位：{session.target_role}
技术栈：{session.tech_stack or "未填写"}
原始描述：{session.rough_description}

当前阶段：{STAGE_LABELS[stage]}
本阶段目标：{", ".join(STAGE_GOALS.get(stage, []))}
本阶段已回答轮数：{answered_count}
本阶段最少追问轮数：{min_rounds}
本阶段最多追问轮数：{max_rounds}

最近一轮问答：
{latest_answer_block}

本阶段问答：
{current_answers}

全部历史问答：
{self._format_rounds(session)}

回答意图分类规则：
1. answer_intent 只能是 skip、unknown_only、informative、informative_with_unknown 之一。
2. skip：用户明确表示跳过、换一个、下一个，且没有提供可写入简历的事实；如果只混入无语义数字、符号或乱码，也仍然视为没有有效信息。
3. unknown_only：用户只表达不知道、不清楚、没有记录、暂时没有，且没有提供可写入简历的事实。
4. informative：用户提供了可以写入简历或面试回答的事实，并且没有明显未知部分。
5. informative_with_unknown：用户既提供了有效事实，又说明某些部分不知道、不确定或没有数据。
6. 不要因为回答里出现“不知道、跳过、不清楚”这些词，就直接判为 skip 或 unknown_only；必须看回答里是否还有具体事实。

追问决策规则：
1. 如果已回答轮数少于最少追问轮数，stage_complete 必须是 false，除非当前阶段完全无法继续。
2. 如果 answer_intent 是 skip 或 unknown_only，不要重复刚刚被用户跳过或答不上来的问题；要么换一个角度问，要么在信息已足够时结束当前阶段。
3. 如果 answer_intent 是 informative_with_unknown，下一问应该围绕已有有效事实继续挖证据，或询问其他缺失点，不要反复追问用户已经说不清楚的部分。
4. 如果信息还缺关键点，stage_complete 为 false，并提出一个具体、短、方便回答的问题。
5. 如果信息已经足够，stage_complete 为 true，question 输出空字符串。
6. 不要重复“本阶段问答”里已经问过的问题。
7. 只输出 JSON，不要输出解释。

输出格式：
{{
  "answer_intent": "informative",
  "contains_useful_info": true,
  "useful_facts": ["只写用户回答中明确出现的事实，不要推断"],
  "unknown_parts": ["用户明确说不清楚或缺数据的部分；没有则为空数组"],
  "stage_complete": false,
  "question": "还需要继续追问的问题；如果阶段完成则为空字符串",
  "reason": "为什么继续追问或为什么阶段完成"
}}
"""
        data = self.run_json(prompt, max_tool_iterations=1)
        if data:
            answer_intent = self._coerce_answer_intent(data.get("answer_intent"))
            useful_facts = as_list(data.get("useful_facts"))
            unknown_parts = as_list(data.get("unknown_parts"))
            contains_useful_info = bool(data.get("contains_useful_info")) or bool(useful_facts)
            if answer_intent in ("skip", "unknown_only") and contains_useful_info:
                answer_intent = "informative_with_unknown" if unknown_parts else "informative"

            stage_complete = bool(data.get("stage_complete"))
            if answered_count < min_rounds:
                stage_complete = False
            question = str(data.get("question") or "").strip()
            reason = str(data.get("reason") or "").strip()
            if stage_complete:
                return StageDecision(
                    "",
                    "llm",
                    True,
                    reason or "当前阶段信息已经足够。",
                    answer_intent=answer_intent,
                    contains_useful_info=contains_useful_info,
                    useful_facts=useful_facts,
                    unknown_parts=unknown_parts,
                )
            if question:
                if self._question_already_asked(session, stage, question):
                    return StageDecision(
                        fallback,
                        "fallback",
                        False,
                        (reason or "模型认为还需要继续追问。") + " 模型给出了已问过的问题，已改为同阶段的其他角度。",
                        answer_intent=answer_intent,
                        contains_useful_info=contains_useful_info,
                        useful_facts=useful_facts,
                        unknown_parts=unknown_parts,
                    )
                return StageDecision(
                    question,
                    "llm",
                    False,
                    reason or "模型认为还需要继续追问。",
                    answer_intent=answer_intent,
                    contains_useful_info=contains_useful_info,
                    useful_facts=useful_facts,
                    unknown_parts=unknown_parts,
                )

        return StageDecision(fallback, "fallback", False, "模型未返回有效决策，使用本地兜底问题。")

    def _fallback_question(self, stage: Stage, answered_count: int, session: SessionState | None = None) -> str:
        questions = FALLBACK_QUESTIONS.get(stage) or ["请补充这个项目最能体现你能力的一点。"]
        if session:
            asked = {
                self._normalize_question(record.question)
                for record in session.rounds
                if record.stage == stage and record.question
            }
            for question in questions:
                if self._normalize_question(question) not in asked:
                    return question
        index = min(answered_count, len(questions) - 1)
        return questions[index]

    def _format_stage_rounds(self, session: SessionState, stage: Stage) -> str:
        records = [record for record in session.rounds if record.stage == stage]
        if not records:
            return "暂无"
        return "\n".join(f"- Q: {record.question}\n  A: {record.answer}" for record in records)

    def _format_rounds(self, session: SessionState) -> str:
        if not session.rounds:
            return "暂无"
        return "\n".join(
            f"- [{STAGE_LABELS.get(record.stage, record.stage)}] Q: {record.question}\n"
            f"  A: {record.answer}\n"
            f"  answer_intent: {record.answer_intent}"
            for record in session.rounds
        )

    def _latest_stage_record(self, session: SessionState, stage: Stage) -> RoundRecord | None:
        for record in reversed(session.rounds):
            if record.stage == stage:
                return record
        return None

    def _format_latest_answer(self, record: RoundRecord | None) -> str:
        if not record:
            return "暂无。当前是在生成本阶段第一个问题。"
        return f"Q: {record.question}\nA: {record.answer}"

    def _question_already_asked(self, session: SessionState, stage: Stage, question: str) -> bool:
        normalized = self._normalize_question(question)
        if not normalized:
            return False
        return any(
            self._normalize_question(record.question) == normalized
            for record in session.rounds
            if record.stage == stage
        )

    def _normalize_question(self, question: str) -> str:
        normalized = "".join(str(question).split())
        return normalized.rstrip("？?。.!！")

    def _coerce_answer_intent(self, value: object) -> AnswerIntent:
        normalized = str(value or "").strip().lower().replace("-", "_")
        aliases = {
            "skip": "skip",
            "unknown_only": "unknown_only",
            "unknown": "unknown_only",
            "dont_know": "unknown_only",
            "do_not_know": "unknown_only",
            "informative": "informative",
            "useful": "informative",
            "informative_with_unknown": "informative_with_unknown",
            "partial": "informative_with_unknown",
            "partial_info": "informative_with_unknown",
        }
        coerced = aliases.get(normalized, "unknown")
        if coerced in {"skip", "unknown_only", "informative", "informative_with_unknown"}:
            return coerced  # type: ignore[return-value]
        return "unknown"
