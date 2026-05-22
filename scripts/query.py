#!/usr/bin/env python3
"""CLI query tool for the Coaction Binding Authority Bot.

Usage:
  python scripts/query.py "your question here"
  python scripts/query.py "follow-up question" --session-id <sid>
  python scripts/query.py "question" --role agent
  python scripts/query.py --interactive

This runs the agent directly (no FastAPI server needed).
Uses the new UnderwritingAgent from the reference architecture.
"""

import asyncio
import os
import sys
import uuid
import argparse

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Reconfigure stdout/stderr to UTF-8 for Windows compatibility
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

load_dotenv()


async def invoke_agent(query: str, session_id: str, role: str) -> dict:
    """Invoke the underwriting agent directly."""
    import json
    from domain.models import ExecutionProfile
    from agents.underwriting_agent import UnderwritingAgent

    # Load the production profile
    with open("profiles/coaction-underwriting.json", "r", encoding="utf-8") as f:
        profile_data = json.load(f)

    profile = ExecutionProfile.model_validate(profile_data)

    # Allow override from env if present
    region = os.environ.get("AWS_REGION", "us-east-1")
    if os.environ.get("BEDROCK_MODEL_ID"):
        profile.model_profile.model_id = os.environ.get("BEDROCK_MODEL_ID")

    agent = UnderwritingAgent(profile=profile, region=region)
    result = await agent.invoke(query=query, role=role)

    return {
        "answer": result.get("answer", ""),
        "sources": result.get("sources", []),
        "citations": result.get("citations", []),
        "follow_up_questions": result.get("follow_up_questions", []),
        "model_id": profile.model_profile.model_id,
        "session_id": session_id,
    }


async def main():
    parser = argparse.ArgumentParser(description="Coaction Binding Authority Bot - CLI")
    parser.add_argument("query", nargs="*", help="The question to ask")
    parser.add_argument(
        "--session-id", "-s", default=None, help="Session ID for multi-turn (reuse for follow-ups)"
    )
    parser.add_argument(
        "--role",
        "-r",
        default="underwriter",
        choices=["underwriter", "agent", "external"],
        help="User role (default: underwriter)",
    )
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="Interactive multi-turn mode"
    )
    args = parser.parse_args()

    import json

    session_id = args.session_id or str(uuid.uuid4())

    with open("profiles/coaction-underwriting.json", "r", encoding="utf-8") as f:
        profile_data = json.load(f)

    model_id = os.environ.get("BEDROCK_MODEL_ID") or profile_data.get("model_profile", {}).get(
        "model_id", "amazon.nova-pro-v1:0"
    )
    kb_ids = profile_data.get("retrieval_profile", {}).get("knowledge_base_ids", [])
    kb_id = ", ".join(kb_ids) if kb_ids else "None"

    print(f"\n{'-' * 60}")
    print("  Coaction Binding Authority Bot - CLI")
    print(f"{'-' * 60}")
    print(f"  Model:      bedrock / {model_id}")
    print(f"  KB ID:      {kb_id}")
    print(f"  Role:       {args.role}")
    print(f"  Session:    {session_id}")
    print(f"{'-' * 60}\n")

    if args.interactive:
        print("  Type 'quit' or 'exit' to end.\n")
        turn = 0
        while True:
            try:
                query = input(f"You [{turn + 1}]: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break

            if not query or query.lower() in ("quit", "exit", "q"):
                print(f"\nSession ID for resume: {session_id}")
                break

            turn += 1
            result = await invoke_agent(query, session_id, args.role)

            print(f"\n{'=' * 60}")
            print(result["answer"])
            print(f"{'=' * 60}")

            if result["sources"]:
                print("\nSources:")
                for i, url in enumerate(result["sources"][:3], 1):
                    print(f"   {i}. {url}")

            if result["follow_up_questions"]:
                print("\nYou might also want to ask:")
                for i, q in enumerate(result["follow_up_questions"], 1):
                    print(f"   {i}. {q}")
            print()

    else:
        if not args.query:
            parser.print_help()
            sys.exit(1)

        query = " ".join(args.query)
        print(f"Query: {query}\n")

        result = await invoke_agent(query, session_id, args.role)

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
        print(f'  > python scripts/query.py "follow-up question" --session-id {session_id}')
        print()


if __name__ == "__main__":
    asyncio.run(main())
