#!/usr/bin/env python3
"""CLI query tool for the Coaction Binding Authority Bot.

Usage:
  python query.py "your question here"
  python query.py "follow-up question" --session-id <sid>
  python query.py "question" --role agent
  python query.py --interactive

This runs the agent directly (no FastAPI server needed).
Supports session persistence + AgentCore Memory integration.
"""
import asyncio
import sys
import os
import uuid
import argparse
from dotenv import load_dotenv

load_dotenv()


## ── Memory helpers (Native Integration) ──────────────────────────────────────

def _get_memory_session_manager(session_id: str, user_id: str):
    """Build native AgentCoreMemorySessionManager for Strands."""
    from app.dependencies.settings import get_settings
    settings = get_settings()

    if not settings.agentcore_memory_enabled or not settings.agentcore_memory_id:
        return None

    try:
        import boto3
        from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
        from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

        session = boto3.Session(
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )

        config = AgentCoreMemoryConfig(
            memory_id=settings.agentcore_memory_id,
            session_id=session_id,
            actor_id=user_id,
        )
        
        return AgentCoreMemorySessionManager(
            agentcore_memory_config=config,
            region_name=settings.aws_region,
            boto_session=session
        )
    except Exception as e:
        print(f"  [WARN] Failed to init native memory session manager: {e}")
        return None


# ── Agent invocation ─────────────────────────────────────────────────────────

async def invoke_agent(query: str, session_id: str, role: str, user_id: str) -> dict:
    """Invoke the agent with native memory integration."""
    from app.dependencies.settings import get_settings
    from services.retrieval import search_manuals, get_last_retrieval_sources
    from control_plane.prompt_repository import PromptRepository
    from runtime.strands_agent import _build_model
    from strands import Agent

    settings = get_settings()
    prompt_repo = PromptRepository()
    system_prompt = prompt_repo.get_template("coaction_binding_authority_bot")

    # Use native session manager for automatic memory handling
    session_manager = _get_memory_session_manager(session_id, user_id)

    model = _build_model()
    
    # The session_manager handles both reading long-term memory 
    # and writing short-term events automatically.
    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[search_manuals],
        callback_handler=None,
        session_manager=session_manager,
    )

    # Invoke agent
    response = agent(query)
    answer = str(response)
    
    all_sources = get_last_retrieval_sources()

    # Only keep sources that the agent actually cited in its answer
    cited_sources = [s.get("url", "") for s in all_sources
                     if s.get("url") and s["url"] != "N/A" and s["url"] in answer]

    model_id = (
        settings.bedrock_model_id
        if settings.model_provider.lower() == "bedrock"
        else settings.openai_chat_model
    )

    return {
        "answer": answer,
        "sources": cited_sources,
        "model_id": model_id,
        "session_id": session_id,
    }


async def main():
    parser = argparse.ArgumentParser(description="Coaction Binding Authority Bot - CLI")
    parser.add_argument("query", nargs="*", help="The question to ask")
    parser.add_argument("--session-id", "-s", default=None, help="Session ID for multi-turn (reuse for follow-ups)")
    parser.add_argument("--role", "-r", default="underwriter", choices=["underwriter", "agent", "external"],
                        help="User role (default: underwriter)")
    parser.add_argument("--user-id", "-u", default="cli-user", help="User ID (default: cli-user)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive multi-turn mode")
    args = parser.parse_args()

    from app.dependencies.settings import get_settings
    settings = get_settings()

    # Session ID is managed natively by AgentCoreMemorySessionManager
    session_id = args.session_id or str(uuid.uuid4())

    print(f"\n{'-' * 60}")
    print(f"  Coaction Binding Authority Bot - CLI")
    print(f"{'-' * 60}")
    print(f"  Model:      {settings.model_provider} / {settings.openai_chat_model if settings.model_provider == 'openai' else settings.bedrock_model_id}")
    print(f"  KB ID:      {settings.bedrock_kb_id}")
    print(f"  Role:       {args.role}")
    print(f"  Session:    {session_id}")
    print(f"  User:       {args.user_id}")
    print(f"  Memory:     {'enabled' if settings.agentcore_memory_enabled else 'disabled'}" + (f" ({settings.agentcore_memory_id})" if settings.agentcore_memory_id else ""))
    print(f"{'-' * 60}\n")

    if args.interactive:
        # Interactive multi-turn mode
        print("  Type 'quit' or 'exit' to end. Session is preserved across turns.\n")
        turn = 0
        while True:
            try:
                query = input(f"You [{turn+1}]: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break

            if not query or query.lower() in ("quit", "exit", "q"):
                print(f"\nSession ID for resume: {session_id}")
                break

            turn += 1
            result = await invoke_agent(query, session_id, args.role, args.user_id)

            print(f"\n{'=' * 60}")
            print(result["answer"])
            print(f"{'=' * 60}")

            if result["sources"]:
                print(f"\nSources:")
                for i, url in enumerate(result["sources"][:3], 1):
                    print(f"   {i}. {url}")
            print()

    else:
        # Single query mode
        if not args.query:
            parser.print_help()
            sys.exit(1)

        query = " ".join(args.query)
        print(f"Query: {query}\n")

        result = await invoke_agent(query, session_id, args.role, args.user_id)

        print("=" * 60)
        print("ANSWER")
        print("=" * 60)
        print(result["answer"])
        print()

        if result["sources"]:
            print("=" * 60)
            print("SOURCES")
            print("=" * 60)
            for i, url in enumerate(result["sources"], 1):
                print(f"{i}. {url}")
            print()

        print(f"Session ID (for follow-ups): {session_id}")
        print(f"  > python query.py \"follow-up question\" --session-id {session_id}")
        print()


if __name__ == '__main__':
    asyncio.run(main())
