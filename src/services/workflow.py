from __future__ import annotations

import json
from collections.abc import Generator

from hello_agents.tools.registry import ToolRegistry

from src.agents import DiscoveryAgent, ProjectAnalyzerAgent, ResumeCriticAgent, ResumeWriterAgent
from src.agents.discovery import StageDecision
from src.llm import HelloAgentRuntime
from src.models import AgentResponse, ResumePackage, RoundRecord, SessionState, Stage, StartRequest
from src.services.memory_store import MemoryStore
from src.services.session_store import SessionStore


STAGE_ORDER: list[Stage] = ["overview", "role", "technical", "impact"]
MAX_STAGE_ROUNDS = 4
MIN_STAGE_ROUNDS = 2


class ResumeWorkflow:
    def __init__(self, runtime: HelloAgentRuntime, session_store: SessionStore, memory_store: MemoryStore):
        self.runtime = runtime
        self.session_store = session_store
        self.memory_store = memory_store
        self.tool_registry = ToolRegistry()
        self.tool_registry.register_tool(memory_store.note_tool)

        self.discovery = DiscoveryAgent(runtime, self.tool_registry)
        self.analyzer = ProjectAnalyzerAgent(runtime, self.tool_registry)
        self.writer = ResumeWriterAgent(runtime, self.tool_registry)
        self.critic = ResumeCriticAgent(runtime, self.tool_registry)

    def start(self, request: StartRequest) -> AgentResponse:
        session = SessionState(
            project_name=request.project_name.strip(),
            rough_description=request.rough_description.strip(),
            target_role=request.target_role.strip() or "后端开发 / AI Agent 相关岗位",
            tech_stack=request.tech_stack.strip(),
            current_stage="overview",
        )
        decision = self.discovery.decide_stage(
            session,
            "overview",
            answered_count=0,
            max_rounds=MAX_STAGE_ROUNDS,
            min_rounds=MIN_STAGE_ROUNDS,
        )
        session.current_question = decision.question
        session.current_question_source = decision.question_source
        self.session_store.create(session)
        self.memory_store.remember_session_start(session)
        return AgentResponse(
            session_id=session.session_id,
            stage=session.current_stage,
            question=decision.question,
            question_source=decision.question_source,
            stage_round=1,
            max_stage_rounds=MAX_STAGE_ROUNDS,
            stage_complete=False,
            stage_complete_reason=decision.reason,
            message="项目已创建。先把项目定位讲清楚。",
        )

    def submit(self, session_id: str, answer: str) -> AgentResponse:
        session = self._require_session(session_id)
        if session.current_stage in ("done", "finalizing"):
            return AgentResponse(
                session_id=session.session_id,
                stage=session.current_stage,
                message="这个会话已经进入生成阶段。",
                ready_to_finalize=session.current_stage == "finalizing",
                is_done=session.current_stage == "done",
                final_package=session.final_package,
            )

        record = RoundRecord(
            stage=session.current_stage,
            question=session.current_question,
            question_source=session.current_question_source,
            answer=answer.strip(),
        )
        session.rounds.append(record)

        answered_count = self._stage_round_count(session, session.current_stage)
        decision = self.discovery.decide_stage(
            session,
            session.current_stage,
            answered_count=answered_count,
            max_rounds=MAX_STAGE_ROUNDS,
            min_rounds=MIN_STAGE_ROUNDS,
        )

        record.answer_intent = decision.answer_intent
        record.contains_useful_info = decision.contains_useful_info
        record.useful_facts = decision.useful_facts
        record.unknown_parts = decision.unknown_parts
        self.memory_store.remember_answer(session, record)

        skip_without_useful_info = decision.answer_intent in {"skip", "unknown_only"} and not decision.contains_useful_info
        if skip_without_useful_info and answered_count >= MIN_STAGE_ROUNDS:
            return self._advance_after_stage(
                session,
                reason=decision.reason or "用户本轮没有提供可继续挖掘的信息，进入下一阶段。",
                previous_decision=decision,
            )

        force_advance = answered_count >= MAX_STAGE_ROUNDS
        if force_advance:
            return self._advance_after_stage(
                session,
                reason=f"{session.current_stage} 阶段已达到 {MAX_STAGE_ROUNDS} 轮上限，进入下一阶段。",
                previous_decision=decision,
            )

        if decision.stage_complete:
            return self._advance_after_stage(session, reason=decision.reason, previous_decision=decision)

        session.current_question = decision.question
        session.current_question_source = decision.question_source
        self.session_store.save(session)
        return AgentResponse(
            session_id=session.session_id,
            stage=session.current_stage,
            question=decision.question,
            question_source=decision.question_source,
            **self._answer_payload(decision),
            stage_round=answered_count + 1,
            max_stage_rounds=MAX_STAGE_ROUNDS,
            stage_complete=False,
            stage_complete_reason=decision.reason,
            message=f"已记录。继续追问当前环节（{answered_count + 1}/{MAX_STAGE_ROUNDS}）。",
        )

    def finalize(self, session_id: str) -> ResumePackage:
        session = self._require_session(session_id)
        notes = self.memory_store.search(session.session_id, limit=10)
        analysis = self.analyzer.analyze(session, notes_summary=notes)
        session.analysis = analysis
        self.memory_store.remember_analysis(session, analysis)

        package = self.writer.write_package(session, analysis)
        notes = self.memory_store.search(session.session_id, limit=20)
        package = self.critic.review_and_refine(session, package, notes_summary=notes)

        session.final_package = package
        session.current_stage = "done"
        self.session_store.save(session)
        self.memory_store.remember_package(package, session.session_id)
        return package

    def finalize_stream(self, session_id: str) -> Generator[str, None, None]:
        try:
            yield self._sse("progress", {"message": "项目分析 Agent 正在整理背景、职责和技术难点..."})
            session = self._require_session(session_id)
            notes = self.memory_store.search(session.session_id, limit=10)
            analysis = self.analyzer.analyze(session, notes_summary=notes)
            session.analysis = analysis
            self.memory_store.remember_analysis(session, analysis)

            yield self._sse("progress", {"message": "简历改写 Agent 正在生成项目简介、bullet 和面试追问..."})
            package = self.writer.write_package(session, analysis)

            yield self._sse("progress", {"message": "证据审核Agent 正在结合上下文工程和 NoteTool 记录检查虚构内容..."})
            notes = self.memory_store.search(session.session_id, limit=20)
            package = self.critic.review_and_refine(session, package, notes_summary=notes)

            session.final_package = package
            session.current_stage = "done"
            self.session_store.save(session)
            self.memory_store.remember_package(package, session.session_id)

            markdown = self.package_to_markdown(package)
            for chunk in self._chunk_text(markdown, 180):
                yield self._sse("chunk", {"content": chunk})
            yield self._sse("done", {"final_package": package.model_dump()})
        except Exception as exc:
            yield self._sse("error", {"message": str(exc)})

    def get_session(self, session_id: str) -> SessionState:
        return self._require_session(session_id)

    def list_sessions(self) -> list[dict]:
        return self.session_store.list()

    def delete_session(self, session_id: str) -> bool:
        deleted = self.session_store.delete(session_id)
        self.memory_store.delete_session_notes(session_id)
        return deleted

    def delete_all_sessions(self) -> int:
        sessions = self.session_store.list()
        count = self.session_store.delete_all()
        for item in sessions:
            self.memory_store.delete_session_notes(item["session_id"])
        return count

    def get_notes_summary(self) -> str:
        return self.memory_store.summary()

    def package_to_markdown(self, package: ResumePackage) -> str:
        bullets = "\n".join(f"- {item.text}" for item in package.resume_bullets)
        highlights = "\n".join(f"- {item}" for item in package.technical_highlights)
        architecture = "\n".join(f"- {item}" for item in package.architecture_points)
        results = "\n".join(f"- {item}" for item in package.quantified_results)
        questions = "\n".join(
            f"- {item.question}\n  回答思路：{item.answer_strategy}"
            for item in package.interview_questions
        )
        missing = "\n".join(f"- {item}" for item in package.missing_info) or "- 暂无明显缺失"
        next_actions = "\n".join(f"- {item}" for item in package.next_actions)

        return f"""# {package.project_name}

## 项目定位
{package.positioning}

## 简历项目简介
{package.resume_summary}

## 简历 Bullet
{bullets}

## 技术亮点
{highlights}

## 架构与流程
{architecture}

## 结果与价值
{results}

## 面试追问
{questions}

## 仍需补充
{missing}

## 下一步
{next_actions}
"""

    def _advance_after_stage(
        self,
        session: SessionState,
        reason: str,
        previous_decision: StageDecision | None = None,
    ) -> AgentResponse:
        next_stage = self._next_stage(session.current_stage)
        if next_stage is None:
            session.current_stage = "finalizing"
            session.current_question = ""
            session.current_question_source = "unknown"
            self.session_store.save(session)
            return AgentResponse(
                session_id=session.session_id,
                stage="finalizing",
                question_source="unknown",
                **self._answer_payload(previous_decision),
                stage_complete=True,
                stage_complete_reason=reason,
                message="信息收集完成，可以生成简历优化报告。",
                ready_to_finalize=True,
            )

        session.current_stage = next_stage
        decision = self.discovery.decide_stage(
            session,
            next_stage,
            answered_count=0,
            max_rounds=MAX_STAGE_ROUNDS,
            min_rounds=MIN_STAGE_ROUNDS,
        )
        session.current_question = decision.question
        session.current_question_source = decision.question_source
        self.session_store.save(session)
        return AgentResponse(
            session_id=session.session_id,
            stage=next_stage,
            question=decision.question,
            question_source=decision.question_source,
            **self._answer_payload(previous_decision),
            stage_round=1,
            max_stage_rounds=MAX_STAGE_ROUNDS,
            stage_complete=True,
            stage_complete_reason=reason,
            message=f"{reason} 已进入下一环节。",
        )

    def _stage_round_count(self, session: SessionState, stage: Stage) -> int:
        return sum(1 for record in session.rounds if record.stage == stage)

    def _next_stage(self, stage: Stage) -> Stage | None:
        index = STAGE_ORDER.index(stage)
        if index + 1 >= len(STAGE_ORDER):
            return None
        return STAGE_ORDER[index + 1]

    def _answer_payload(self, decision: StageDecision | None) -> dict:
        if decision is None:
            return {}
        return {
            "answer_intent": decision.answer_intent,
            "useful_facts": decision.useful_facts,
            "unknown_parts": decision.unknown_parts,
        }

    def _require_session(self, session_id: str) -> SessionState:
        session = self.session_store.get(session_id)
        if not session:
            raise KeyError(f"Session not found: {session_id}")
        return session

    def _sse(self, event_type: str, data: dict) -> str:
        return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def _chunk_text(self, text: str, size: int) -> list[str]:
        return [text[i : i + size] for i in range(0, len(text), size)]
