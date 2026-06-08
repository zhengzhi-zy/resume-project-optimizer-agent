from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


Stage = Literal["overview", "role", "technical", "impact", "finalizing", "done"]
QuestionSource = Literal["llm", "fallback", "unknown"]
AnswerIntent = Literal["skip", "unknown_only", "informative", "informative_with_unknown", "unknown"]


class StartRequest(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=80)
    rough_description: str = Field(..., min_length=5)
    target_role: str = Field("后端开发 / AI Agent 相关岗位", max_length=80)
    tech_stack: str = Field("", max_length=300)


class SubmitRequest(BaseModel):
    session_id: str
    answer: str = Field(..., min_length=1)


class RoundRecord(BaseModel):
    stage: Stage
    question: str
    question_source: QuestionSource = "unknown"
    answer: str
    answer_intent: AnswerIntent = "unknown"
    contains_useful_info: bool = False
    useful_facts: list[str] = Field(default_factory=list)
    unknown_parts: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class ProjectAnalysis(BaseModel):
    problem: str
    scenario: str
    personal_role: list[str] = Field(default_factory=list)
    technical_stack: list[str] = Field(default_factory=list)
    technical_challenges: list[str] = Field(default_factory=list)
    solutions: list[str] = Field(default_factory=list)
    results: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    honesty_notes: list[str] = Field(default_factory=list)


class ResumeBullet(BaseModel):
    text: str
    focus: str
    why_it_works: str


class InterviewQuestion(BaseModel):
    question: str
    answer_strategy: str


class ScoreCard(BaseModel):
    clarity: int = Field(ge=0, le=10)
    technical_depth: int = Field(ge=0, le=10)
    business_impact: int = Field(ge=0, le=10)
    interview_readiness: int = Field(ge=0, le=10)
    notes: list[str] = Field(default_factory=list)


class ResumePackage(BaseModel):
    project_name: str
    target_role: str
    positioning: str
    resume_summary: str
    resume_bullets: list[ResumeBullet]
    technical_highlights: list[str]
    architecture_points: list[str]
    quantified_results: list[str]
    interview_questions: list[InterviewQuestion]
    missing_info: list[str]
    score_card: ScoreCard
    next_actions: list[str]
    reflection_notes: list[str] = Field(default_factory=list)


class SessionState(BaseModel):
    session_id: str = Field(default_factory=lambda: uuid4().hex[:10])
    project_name: str
    rough_description: str
    target_role: str
    tech_stack: str = ""
    current_stage: Stage = "overview"
    current_question: str = ""
    current_question_source: QuestionSource = "unknown"
    rounds: list[RoundRecord] = Field(default_factory=list)
    analysis: ProjectAnalysis | None = None
    final_package: ResumePackage | None = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def touch(self) -> None:
        self.updated_at = datetime.now().isoformat(timespec="seconds")


class AgentResponse(BaseModel):
    session_id: str
    stage: Stage
    question: str | None = None
    question_source: QuestionSource = "unknown"
    answer_intent: AnswerIntent = "unknown"
    useful_facts: list[str] = Field(default_factory=list)
    unknown_parts: list[str] = Field(default_factory=list)
    stage_round: int = 0
    max_stage_rounds: int = 4
    stage_complete: bool = False
    stage_complete_reason: str = ""
    message: str
    ready_to_finalize: bool = False
    is_done: bool = False
    final_package: ResumePackage | None = None


class StreamEvent(BaseModel):
    type: Literal["progress", "chunk", "done", "error"]
    data: dict[str, Any]
