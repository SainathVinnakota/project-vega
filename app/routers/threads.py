"""
Threads router — GET /v1/users/{user_id}/threads, GET/DELETE /v1/threads/{session_id}.
Supports the UI application use case by indexing thread metadata in DynamoDB and retrieving messages from S3.
"""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from boto3.dynamodb.conditions import Key

from app.dependencies.services import get_boto3_factory, get_session_manager
from adapters.aws.boto3_factory import Boto3SessionFactory
from services.session_manager import SessionManager

router = APIRouter(tags=["threads"])

THREADS_TABLE = "agent_threads"


@router.get("/v1/users/{user_id}/threads")
async def list_user_threads(
    user_id: str,
    boto3_factory: Boto3SessionFactory = Depends(get_boto3_factory),
) -> List[Dict[str, Any]]:
    """List all active conversation threads for a specific user from the DynamoDB index."""
    try:
        table = boto3_factory.resource("dynamodb").Table(THREADS_TABLE)
        # Assuming user_id is the primary/partition key or indexed via GSI
        response = table.query(
            KeyConditionExpression=Key("user_id").eq(user_id)
        )
        items = response.get("Items", [])
        # Sort by updated_at descending to place recent threads at the top
        items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return items
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Could not fetch user threads from DynamoDB: {e}")
        # Return graceful empty list if table isn't fully provisioned yet in local dev
        return []


@router.get("/v1/threads/{session_id}/messages")
async def get_thread_messages(
    session_id: str,
    sm: SessionManager = Depends(get_session_manager),
) -> List[Dict[str, Any]]:
    """Retrieve complete serial message history for a given thread session ID."""
    messages = sm.get_messages(session_id)
    if not messages:
        # Return standard empty list context if no messages exist yet
        return []
    return messages


@router.delete("/v1/threads/{session_id}")
async def delete_thread(
    session_id: str,
    user_id: str | None = None,
    boto3_factory: Boto3SessionFactory = Depends(get_boto3_factory),
    sm: SessionManager = Depends(get_session_manager),
) -> Dict[str, Any]:
    """Delete a conversation thread completely from both DynamoDB index records and S3/memory persistence arrays."""
    # 1. Clear session messages from storage manager
    sm.clear_session(session_id)

    # 2. Delete item from DynamoDB thread index table if user_id partition key is provided
    if user_id:
        try:
            table = boto3_factory.resource("dynamodb").Table(THREADS_TABLE)
            table.delete_item(Key={"user_id": user_id, "session_id": session_id})
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Could not delete thread record from DynamoDB: {e}")

    return {"status": "success", "session_id": session_id, "message": "Thread deleted successfully"}
