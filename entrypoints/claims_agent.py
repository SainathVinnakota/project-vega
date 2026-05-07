"""
Claims Agent entrypoint.
Demonstrates how to add another agent to the same project.
"""
import os
import sys
import uuid
from dotenv import load_dotenv
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from services.retrieval import search_manuals
from runtime.strands_agent import _build_model
from control_plane.prompt_repository import PromptRepository
import boto3
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

app = BedrockAgentCoreApp()
model = _build_model()
prompt_repo = PromptRepository()

def _get_memory_session_manager(session_id: str, user_id: str):
    """Build native AgentCoreMemorySessionManager for Strands."""
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID")
    if not memory_id:
        return None

    try:
        session = boto3.Session(region_name=os.environ.get("AWS_REGION", "us-east-1"))
        config = AgentCoreMemoryConfig(
            memory_id=memory_id,
            session_id=session_id,
            actor_id=user_id,
        )
        return AgentCoreMemorySessionManager(
            agentcore_memory_config=config,
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            boto_session=session
        )
    except Exception:
        return None

@app.entrypoint
def invoke(payload: dict) -> dict:
    user_message = payload.get("prompt", "")
    session_id = payload.get("session_id", str(uuid.uuid4()))
    user_id = payload.get("user_id", "anonymous")
    
    # Use native session manager for automatic memory handling
    session_manager = _get_memory_session_manager(session_id, user_id)
    
    # Use a different prompt template for the Claims agent
    system_prompt = prompt_repo.get_template("claims_bot") 
    
    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[search_manuals],
        session_manager=session_manager,
    )
    
    result = agent(user_message)
    return {
        "status": "success",
        "answer": str(result),
        "session_id": session_id,
        "agent": "claims_agent"
    }

if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 8081)))
