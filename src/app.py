from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.config import BASE_DIR, STATIC_DIR, ensure_data_dirs, get_settings
from src.llm import HelloAgentRuntime
from src.models import AgentResponse, ResumePackage, StartRequest, SubmitRequest
from src.services.memory_store import MemoryStore
from src.services.session_store import SessionStore
from src.services.workflow import ResumeWorkflow


settings = get_settings()
ensure_data_dirs()

runtime = HelloAgentRuntime(settings.llm)
workflow = ResumeWorkflow(
    runtime=runtime,
    session_store=SessionStore(),
    memory_store=MemoryStore(),
)

app = FastAPI(title=settings.app_name, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_enabled": runtime.available,
        "provider": runtime.provider_label,
        "hello_agents_load_error": runtime.load_error,
    }


@app.post("/api/session/start", response_model=AgentResponse)
def start_session(request: StartRequest) -> AgentResponse:
    return workflow.start(request)


@app.post("/api/session/submit", response_model=AgentResponse)
def submit_answer(request: SubmitRequest) -> AgentResponse:
    try:
        return workflow.submit(request.session_id, request.answer)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/session/{session_id}/finalize", response_model=ResumePackage)
def finalize(session_id: str) -> ResumePackage:
    try:
        return workflow.finalize(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/session/{session_id}/finalize/stream")
def finalize_stream(session_id: str) -> StreamingResponse:
    return StreamingResponse(
        workflow.finalize_stream(session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/session/list")
def list_sessions() -> dict:
    return {"sessions": workflow.list_sessions()}


@app.delete("/api/session/all")
def delete_all_sessions() -> dict:
    count = workflow.delete_all_sessions()
    return {"deleted": count}


@app.get("/api/session/{session_id}")
def get_session(session_id: str) -> dict:
    try:
        return workflow.get_session(session_id).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/session/{session_id}")
def delete_session(session_id: str) -> dict:
    deleted = workflow.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return {"deleted": True, "session_id": session_id}


@app.get("/api/notes/summary")
def notes_summary() -> dict:
    return {"summary": workflow.get_notes_summary()}


app.mount("/", StaticFiles(directory=STATIC_DIR or BASE_DIR / "static", html=True), name="static")
