from __future__ import annotations

import json
from pathlib import Path

from src.config import NOTES_DIR, ensure_data_dirs
from src.models import ProjectAnalysis, ResumePackage, RoundRecord, SessionState


class MemoryStore:
    """Project memory backed by hello_agents NoteTool."""

    def __init__(self, notes_dir: Path = NOTES_DIR):
        ensure_data_dirs()
        from hello_agents.tools.builtin.note_tool import NoteTool

        self.note_tool = NoteTool(workspace=str(notes_dir))

    def remember_session_start(self, session: SessionState) -> None:
        self.note_tool.run(
            {
                "action": "create",
                "title": f"{session.project_name} - 初始项目材料",
                "content": json.dumps(
                    {
                        "session_id": session.session_id,
                        "project_name": session.project_name,
                        "target_role": session.target_role,
                        "tech_stack": session.tech_stack,
                        "rough_description": session.rough_description,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "note_type": "task_state",
                "tags": ["resume-agent", session.session_id, "start"],
            }
        )

    def remember_answer(self, session: SessionState, record: RoundRecord) -> None:
        self.note_tool.run(
            {
                "action": "create",
                "title": f"{session.project_name} - {record.stage} 回答",
                "content": json.dumps(
                    {
                        "stage": record.stage,
                        "question": record.question,
                        "question_source": record.question_source,
                        "raw_answer": record.answer,
                        "answer_intent": record.answer_intent,
                        "contains_useful_info": record.contains_useful_info,
                        "useful_facts": record.useful_facts,
                        "unknown_parts": record.unknown_parts,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "note_type": "reference",
                "tags": ["resume-agent", session.session_id, record.stage, record.answer_intent],
            }
        )

    def remember_analysis(self, session: SessionState, analysis: ProjectAnalysis) -> None:
        self.note_tool.run(
            {
                "action": "create",
                "title": f"{session.project_name} - 项目分析 JSON",
                "content": json.dumps(analysis.model_dump(), ensure_ascii=False, indent=2),
                "note_type": "conclusion",
                "tags": ["resume-agent", session.session_id, "analysis"],
            }
        )

    def remember_package(self, package: ResumePackage, session_id: str = "") -> None:
        self.note_tool.run(
            {
                "action": "create",
                "title": f"{package.project_name} - 最终简历优化包",
                "content": json.dumps(package.model_dump(), ensure_ascii=False, indent=2),
                "note_type": "conclusion",
                "tags": ["resume-agent", session_id, "final"],
            }
        )

    def delete_session_notes(self, session_id: str) -> int:
        if not session_id:
            return 0
        notes = list(self.note_tool.notes_index.get("notes", []))
        deleted = 0
        for note in notes:
            tags = note.get("tags", [])
            if session_id in tags:
                self.note_tool.run({"action": "delete", "note_id": note["id"]})
                deleted += 1
        return deleted

    def summary(self) -> str:
        return self.note_tool.run({"action": "summary"})

    def search(self, query: str, limit: int = 5) -> str:
        return self.note_tool.run({"action": "search", "query": query, "limit": limit})
