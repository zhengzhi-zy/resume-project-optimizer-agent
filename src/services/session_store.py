from __future__ import annotations

from pathlib import Path

from src.config import SESSIONS_DIR, ensure_data_dirs
from src.models import SessionState
from src.utils.json_utils import read_json, write_json


class SessionStore:
    def __init__(self, sessions_dir: Path = SESSIONS_DIR):
        ensure_data_dirs()
        self.sessions_dir = sessions_dir

    def create(self, session: SessionState) -> SessionState:
        self.save(session)
        return session

    def save(self, session: SessionState) -> None:
        session.touch()
        write_json(self._path(session.session_id), session.model_dump())

    def get(self, session_id: str) -> SessionState | None:
        data = read_json(self._path(session_id))
        if not data:
            return None
        return SessionState.model_validate(data)

    def delete(self, session_id: str) -> bool:
        path = self._path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def delete_all(self) -> int:
        count = 0
        for path in self.sessions_dir.glob("*.json"):
            path.unlink()
            count += 1
        return count

    def list(self) -> list[dict]:
        sessions = []
        for path in self.sessions_dir.glob("*.json"):
            data = read_json(path, {})
            sessions.append(
                {
                    "session_id": path.stem,
                    "project_name": data.get("project_name", ""),
                    "target_role": data.get("target_role", ""),
                    "stage": data.get("current_stage", ""),
                    "updated_at": data.get("updated_at", ""),
                }
            )
        return sorted(sessions, key=lambda item: item["updated_at"], reverse=True)

    def _path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"
