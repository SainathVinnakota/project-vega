# Coaction Agent Platform

Enterprise backend platform to create, manage, and run multiple AI agents using one reusable runtime foundation.

---

## 1) Executive Overview

This repository is designed as a platform, not a single bot application.

- **Control plane** manages agent definitions (what each agent is allowed to do).
- **Runtime plane** executes agent requests through a standard pipeline (auth, guardrails, memory, retrieval, response, telemetry).
- **Agent teams only configure agent behavior** (prompt, KBs, memory, model, policies) instead of rewriting Bedrock/Memory integration for every agent.

Business outcome: faster onboarding of new agents with lower implementation risk and better consistency.

---

## 2) What This Platform Provides

- Standard FastAPI runtime APIs for invoking agents
- Reusable orchestration layer for all agents
- AgentCore Memory integration for persistent memory
- Bedrock Knowledge Base retrieval support
- Role-based authorization and guardrail hooks
- CloudWatch telemetry and metadata-only audit pattern
- Agent templates (`retrieval_agent`, `readonly_tool_agent`) for quick onboarding

---

## 3) Architecture (Control Plane + Runtime Plane)

### Control plane (configuration and registration)
- `control_plane/agent_registry.py`
- `control_plane/prompt_repository.py`
- `domain/execution_profile.py`
- `agents/templates.py`

Responsibility: define each agent's runtime contract (model, KB IDs, memory ID, guardrails, tools, version).

### Runtime plane (execution engine)
- `runtime/orchestrator.py`
- `runtime/base_agent.py`
- `runtime/strands_agent.py`
- `services/*` (memory, retrieval, guardrails, telemetry, authorization, audit)
- `app/routers/*` (invoke, sessions, feedback, health)

Responsibility: run every request in a consistent, governed flow.

---

## 4) Runtime Request Flow

1. API receives request for `agent_id`
2. Platform loads registered agent + `ExecutionProfile`
3. Authorization and guardrails are applied
4. Memory context is read (if enabled for that agent)
5. Retrieval is executed using configured KB IDs
6. Model generates response
7. Output guardrails are applied
8. Memory event is written (if enabled)
9. Telemetry and audit metadata are emitted

---

## 5) Repository Structure

```text
app/                    FastAPI shell (routers, middleware, dependencies)
agents/                 Reusable agent templates
control_plane/          Agent registry and prompt management
domain/                 Shared contracts (invocation, identity, execution profile)
runtime/                Base agent + orchestrator
services/               Shared integrations (memory, retrieval, auth, etc.)
adapters/aws/           AWS client factory and adapters
entrypoints/            AgentCore runtime entrypoints
query.py                CLI test utility
Dockerfile              Container build for runtime deployment
```

---

## 6) Configuration Model

### Platform-level environment values (shared infra defaults)
Examples:
- `AWS_REGION`
- AWS credentials
- logging and app runtime settings

### Agent-level values (must be per agent)
Stored in each agent's `ExecutionProfile`:
- `model_profile.model_id`
- `retrieval_profile.knowledge_base_ids` (one or many)
- `memory_profile.memory_id`
- `guardrail_profile.guardrail_id`

Important: for multi-agent scale, avoid one global `BEDROCK_KB_ID` or one global `AGENTCORE_MEMORY_ID` for all agents.

---

## 7) Memory and Session Persistence

- Persistent agent memory is handled by **AgentCore Memory** through `services/memory.py`.
- Session metadata API in `services/session_manager.py` is currently **in-memory fallback**.
- The current implementation does **not** persist session history in DynamoDB.

If DynamoDB persistence is required, implement a DynamoDB-backed session repository and wire it through dependency injection.

---

## 8) APIs

- `POST /v1/agents/{agent_id}/invoke`
- `GET /v1/agents`
- `GET /v1/agents/{agent_id}`
- `GET /v1/sessions/{session_id}`
- `DELETE /v1/sessions/{session_id}`
- `GET /health`

---

## 9) Local Development

### Prerequisites
- Python 3.11+
- AWS credentials configured (if using AWS services)

### Install
```powershell
pip install -r requirements.txt
```

### Run API
```powershell
python -m uvicorn app.main:app --reload
```

### Test invoke
```powershell
curl -X POST "http://localhost:8000/v1/agents/coaction_binding_authority_bot/invoke" `
  -H "Content-Type: application/json" `
  -d "{\"input_text\":\"What is class code 10040?\",\"user_id\":\"u1\",\"role\":\"underwriter\"}"
```

---

## 10) Deployment to Amazon Bedrock AgentCore Runtime

This section is written as an operational runbook from zero to deployment.

### Step 1: Prepare AWS resources
Create/identify:
- Bedrock model access
- Bedrock Knowledge Base(s)
- AgentCore Memory resource(s) (one per agent recommended)
- Optional guardrails
- IAM role/policies required for runtime access

### Step 2: Configure environment
Set runtime environment values for the target environment (dev/stage/prod), for example:
- `AWS_REGION`
- `MODEL_PROVIDER`
- `BEDROCK_MODEL_ID` or OpenAI model settings
- agent-specific memory and KB values (recommended through profile configuration)

### Step 3: Select runtime entrypoint
Choose the entrypoint to deploy:
- `entrypoints/underwriting_agent.py`
- `entrypoints/claims_agent.py`

Update `Dockerfile` `CMD` if deploying a different entrypoint.

### Step 4: Build and validate container locally
```powershell
docker build -t coaction-agent-platform:latest .
docker run --rm -p 8080:8080 --env-file .env coaction-agent-platform:latest
```

### Step 5: Deploy with AgentCore CLI
Use your AgentCore deployment configuration and run:
```powershell
agentcore deploy
```

Notes:
- Use container deployment mode for Windows environments.
- Ensure your deployment manifest references the correct runtime entrypoint/container settings.
- Validate logs in CloudWatch after deployment.

### Step 6: Post-deployment validation
- Invoke deployed endpoint with a test prompt
- Verify retrieval citations and memory behavior
- Confirm telemetry/audit events
- Validate role-based behavior and guardrails

---

## 11) How to Create a New Agent (Non-Technical + Technical)

### Plain-English view
To create a new agent, you provide four things:
1. Agent name and purpose
2. Prompt template (how the agent should behave)
3. Data sources (which KB IDs it can read)
4. Memory and policy settings (which memory ID, guardrails, tools)

The platform then runs this agent using the same shared backend services.

### Technical checklist
1. Add prompt template in `control_plane/prompt_repository.py`.
2. Create/register agent instance in `app/dependencies/services.py` (use `RetrievalAgent` or `ReadOnlyToolAgent`).
3. Define `ExecutionProfile` for that `agent_id` with:
   - model profile
   - retrieval KB IDs
   - memory ID
   - guardrails and observability
4. Register using `registry.register(agent, profile)`.
5. Start app and validate:
   - `GET /v1/agents`
   - `GET /v1/agents/{agent_id}`
   - invoke endpoint test
6. If deploying separately, ensure corresponding entrypoint under `entrypoints/` and Docker `CMD` are aligned.

### Minimal example (registration pattern)
```python
claims_bot = RetrievalAgent(
    agent_id="claims_assistant_bot",
    prompt_template_id="claims_assistant_v1",
)

claims_profile = ExecutionProfile(
    agent_id="claims_assistant_bot",
    version="v1",
    prompt_template_id="claims_assistant_v1",
    model_profile=ModelProfile(model_id="anthropic.claude-3-5-sonnet-20241022-v2:0"),
    retrieval_profile=RetrievalProfile(knowledge_base_ids=["kb-claims-primary"]),
    memory_profile=MemoryProfile(enabled=True, memory_id="mem-claims-prod"),
    guardrail_profile=GuardrailProfile(guardrail_id="gr-claims", guardrail_version="1"),
    observability_profile=ObservabilityProfile(),
)

registry.register(claims_bot, claims_profile)
```

---

## 12) Governance and Security Notes

- Authentication is expected upstream (API Gateway/authorizer pattern).
- Runtime uses identity context (`user_id`, `roles`, `channel`, `correlation_id`).
- First-release tool scope is intended to be read-only.
- Raw prompt/response logging should remain disabled by policy unless explicitly approved.

---

## 13) Recommended Next Improvement

Externalize agent profiles from code to a control-plane data store (JSON/YAML/DB/Parameter Store), so new agents can be onboarded with configuration only and no code change in `app/dependencies/services.py`.
