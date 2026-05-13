from typing import List, Dict, Any
from domain.execution_profile import ExecutionProfile

class ResponseComposer:
    """
    Composes the final response payload for the agent invocation.
    Ensures consistent structure and applies any profile-specific formatting.
    """
    def compose(
        self, 
        agent_id: str,
        answer: str, 
        session_id: str,
        citations: List[Dict[str, Any]] = None,
        tool_results: List[Dict[str, Any]] = None,
        model_id: str = None
    ) -> Dict[str, Any]:
        response = {
            "status": "success",
            "answer": answer,
            "session_id": session_id,
            "agent_id": agent_id,
            "citations": citations or [],
            "tool_results": tool_results or [],
            "model_id": model_id,
            "metadata": {
                "version": "v1"
            }
        }
        return response
