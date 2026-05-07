"""Session management router."""
from fastapi import APIRouter, Depends
from app.dependencies.services import get_session_manager
from services.session_manager import SessionManager

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])


@router.post("")
async def create_session(sm: SessionManager = Depends(get_session_manager)):
    session_id = sm.create_session()
    return {"session_id": session_id}


@router.get("/{session_id}")
async def get_session(session_id: str, sm: SessionManager = Depends(get_session_manager)):
    session = sm.get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    return session


@router.get("/{session_id}/messages")
async def get_messages(session_id: str, sm: SessionManager = Depends(get_session_manager)):
    return sm.get_messages(session_id)


@router.delete("/{session_id}")
async def delete_session(session_id: str, sm: SessionManager = Depends(get_session_manager)):
    sm.clear_session(session_id)
    return {"session_id": session_id, "status": "deleted"}
