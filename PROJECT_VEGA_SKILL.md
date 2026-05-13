# PROJECT VEGA — ARCHITECTURE KNOWLEDGE BASE
# Coaction Specialty Agentic AI Platform on AWS

---

## Project Overview
AWS-first, governed, headless agentic platform. Control plane separated from runtime plane.
- Language: **Python**
- API layer: **FastAPI**
- Orchestration: **Strands Agents SDK** (`strands` package)
- Model provider: **Amazon Bedrock** via Strands `BedrockModel` — fully AWS-native
- Memory integration: **`bedrock_agentcore`** package (Strands session manager) for short/long-term agent memory
- Session/conversation persistence: **S3SessionManager** (Strands built-in) + **DynamoDB** (thread metadata index for UI)
- AWS SDK: **Boto3** (for services with no Strands-native integration)
- Deployment target: **Amazon Bedrock AgentCore Runtime**

---

## SDK & Library Boundaries — What Uses What

### Via Strands SDK (`strands` package) — direct integration
| Capability | How |
|---|---|
| Agent creation & orchestration | `from strands import Agent` |
| Model invocation (Bedrock) | `from strands.models import BedrockModel` |
| Bedrock Guardrails on model | `BedrockModel(guardrail_config={"guardrailIdentifier": ..., "guardrailVersion": ...})` |
| Knowledge Base retrieval | Built-in `retrieve` tool — `Agent(tools=[retrieve])` |
| Conversation session persistence | `S3SessionManager` or `FileSessionManager` — passed as `Agent(session_manager=...)` |
| Conversation window management | `SlidingWindowConversationManager(window_size=N)` |
| Hook-based policy | `strands.hooks` — `BeforeToolCallEvent` |
| Observability / tracing | Built-in OpenTelemetry (OTEL) — ADOT auto-instrumentation |
| Tool specification | Always explicit list — `Agent(tools=[tool_a, tool_b])` — auto-loading disabled in production |

### BedrockModel — model invocation pattern
```python
from strands import Agent
from strands.models import BedrockModel

model = BedrockModel(
    model_id="us.amazon.nova-premier-v1:0",   # from execution profile — never hardcoded
    temperature=0.0,
    max_tokens=2000,
    guardrail_config={
        "guardrailIdentifier": profile.guardrail_profile.guardrail_id,
        "guardrailVersion": profile.guardrail_profile.guardrail_version,
    }
)
agent = Agent(model=model, tools=[retrieve, ...], session_manager=session_manager)
```

### S3SessionManager — conversation/session persistence (Strands built-in)
Stores full conversation history (messages, agent state) per session in S3. Used for BOTH use cases.

```python
from strands import Agent
from strands.session.s3_session_manager import S3SessionManager
import boto3

boto_session = boto3.Session(region_name="us-east-1")
session_manager = S3SessionManager(
    session_id=session_id,       # passed in from caller
    bucket="coaction-agent-sessions",
    prefix="sessions/",
    boto_session=boto_session
)
agent = Agent(model=model, session_manager=session_manager)
# All messages auto-persisted to S3 on each invocation
```

Required S3 IAM permissions: `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`, `s3:ListBucket`

S3 storage structure per session:
```
sessions/
└── session_<session_id>/
    ├── session.json               # session metadata
    └── agents/
        └── agent_<agent_id>/
            ├── agent.json         # agent state
            └── messages/
                ├── message_0.json
                └── message_1.json
```

### Via `bedrock_agentcore` package — agent memory (short-term + long-term)
This is SEPARATE from session/conversation persistence. AgentCore Memory stores semantic facts, user preferences, and summarized context across sessions — not raw message history.

| Capability | How |
|---|---|
| Short-term memory (STM) | `AgentCoreMemorySessionManager` — conversation persistence within a session |
| Long-term memory (LTM) | Same manager with strategies: SEMANTIC, SUMMARIZATION, USER_PREFERENCE |
| Memory config | `AgentCoreMemoryConfig(memory_id, session_id, actor_id, batch_size)` |
| Memory resource creation (one-time) | `bedrock_agentcore.memory.MemoryClient` |
| AgentCore Runtime wrapper | `from bedrock_agentcore.runtime import BedrockAgentCoreApp` |

```python
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

config = AgentCoreMemoryConfig(
    memory_id=MEM_ID,        # from execution profile
    session_id=session_id,
    actor_id=user_id         # scopes memory per user
)
with AgentCoreMemorySessionManager(config, region_name="us-east-1") as memory_session_manager:
    agent = Agent(model=model, session_manager=memory_session_manager)
    agent("user input")
# Always use context manager — guarantees flush on exit
# Only ONE agent per session is supported per AgentCoreMemorySessionManager instance
```

**Note**: `AgentCoreMemorySessionManager` acts as both conversation persistence AND semantic memory. If you need full raw message history in S3 (for thread listing), use `S3SessionManager` for conversation persistence and `AgentCoreMemorySessionManager` separately for memory injection into the agent context.

### Via raw Boto3 — no Strands-native abstraction
| Capability | Boto3 client |
|---|---|
| AgentCore Gateway (tool gateway) | `boto3.client("bedrock-agentcore")` |
| AgentCore Runtime invocation | `boto3.client("bedrock-agentcore")` — `invoke_agent_runtime()` |
| AgentCore Runtime create/manage | `boto3.client("bedrock-agentcore-control")` — `create_agent_runtime()` |
| DynamoDB (thread metadata index, config store) | `boto3.client("dynamodb")` |
| S3 (session storage, config, audit archive) | `boto3.client("s3")` |
| Secrets Manager | `boto3.client("secretsmanager")` |
| CloudWatch (metrics, logs) | `boto3.client("cloudwatch")` / `logs` |
| CloudTrail | `boto3.client("cloudtrail")` |
| EventBridge / SQS / SNS | respective boto3 clients |
| SSM Parameter Store | `boto3.client("ssm")` |

---

## Memory & Session Architecture — Two Use Cases

This is a critical design decision. There are two distinct concepts that must not be confused:

| Concept | What it stores | Technology |
|---|---|---|
| **Conversation session** | Raw message history (user + assistant turns) for context continuity | S3SessionManager (Strands) |
| **Thread metadata index** | Thread title, timestamp, user_id, session_id — for listing in UI | DynamoDB |
| **Agent memory (STM)** | Active conversation context within a session | AgentCore Memory (STM strategy) |
| **Agent memory (LTM)** | Semantic facts, preferences, summaries across sessions | AgentCore Memory (LTM strategies) |

---

### Use Case 1 — Headless API (no thread UI, session continuation only)

**Requirement**: Caller passes a `session_id` to continue a conversation. No UI thread listing needed. API consumer manages session IDs externally.

**Approach**: `S3SessionManager` only. No DynamoDB thread index needed.

**Flow**:
1. First call: caller omits `session_id` → platform generates a new UUID → returns it in response
2. Subsequent calls: caller passes same `session_id` → `S3SessionManager` restores full message history → agent continues with full context
3. No thread metadata stored — caller owns the session ID lifecycle

```python
# Headless API — session continuation
import uuid
from strands.session.s3_session_manager import S3SessionManager

def get_or_create_session_id(request: AgentInvocationRequest) -> str:
    return request.session_id or str(uuid.uuid4())

session_id = get_or_create_session_id(request)
session_manager = S3SessionManager(
    session_id=session_id,
    bucket="coaction-agent-sessions",
    prefix="headless/",
    boto_session=boto_session
)
agent = Agent(model=model, session_manager=session_manager, tools=[...])
result = agent(request.input_text)

# Return session_id in response so caller can use it on next call
return AgentInvocationResponse(session_id=session_id, answer=result.message, ...)
```

**What NOT to do**: Do not store thread metadata in DynamoDB for this use case — unnecessary overhead.

---

### Use Case 2 — UI with Thread List (list conversations, select, continue)

**Requirement**: UI shows a list of all threads for a user. User selects a thread, sees full chat history, and can continue the conversation.

**Approach**: `S3SessionManager` for raw message storage + **DynamoDB** as a thread metadata index.

**Why two stores**:
- S3SessionManager handles the actual message persistence automatically
- DynamoDB stores only the metadata needed to list and display threads: `user_id`, `session_id`, `thread_title`, `created_at`, `updated_at`, `agent_id`
- DynamoDB allows efficient queries like "give me all threads for user X, sorted by last updated"

**DynamoDB Thread Index Table**:
```
Table: agent_threads
PK: user_id         (partition key — query all threads for a user)
SK: session_id      (sort key — unique per thread)
Attributes:
  thread_title      (string — first user message truncated, or generated)
  agent_id          (string)
  created_at        (ISO timestamp)
  updated_at        (ISO timestamp — updated on every new message)
  channel           (string — "ui" | "api")
  message_count     (number)
GSI: user_id + updated_at  (for sorting threads by recency in the UI list)
```

**API endpoints needed for UI thread flow**:
```
POST /v1/agents/{agent_id}/invoke           — send message (creates thread on first call)
GET  /v1/users/{user_id}/threads            — list all threads for user (queries DynamoDB)
GET  /v1/threads/{session_id}/messages      — load full chat history for a thread (reads S3)
DELETE /v1/threads/{session_id}             — delete a thread (removes S3 data + DynamoDB record)
```

**Thread creation flow** (first message in a new thread):
```python
import uuid
from strands.session.s3_session_manager import S3SessionManager

# 1. Generate new session_id for new thread
session_id = str(uuid.uuid4())

# 2. Create S3SessionManager — message history auto-persisted
session_manager = S3SessionManager(
    session_id=session_id,
    bucket="coaction-agent-sessions",
    prefix="ui-threads/",
    boto_session=boto_session
)

# 3. Run agent
agent = Agent(model=model, session_manager=session_manager, tools=[...])
result = agent(request.input_text)

# 4. Write thread metadata to DynamoDB (only on thread creation or message count update)
dynamodb.put_item(
    TableName="agent_threads",
    Item={
        "user_id": {"S": identity.user_id},
        "session_id": {"S": session_id},
        "thread_title": {"S": request.input_text[:80]},
        "agent_id": {"S": request.agent_id},
        "created_at": {"S": now_iso()},
        "updated_at": {"S": now_iso()},
        "channel": {"S": "ui"},
        "message_count": {"N": "1"}
    }
)
```

**Thread continuation flow** (user selects existing thread and sends new message):
```python
# session_id passed by UI from the thread list
session_manager = S3SessionManager(
    session_id=request.session_id,    # existing thread session_id
    bucket="coaction-agent-sessions",
    prefix="ui-threads/",
    boto_session=boto_session
)
# S3SessionManager automatically restores full message history
agent = Agent(model=model, session_manager=session_manager, tools=[...])
result = agent(request.input_text)

# Update thread metadata in DynamoDB
dynamodb.update_item(
    TableName="agent_threads",
    Key={"user_id": ..., "session_id": ...},
    UpdateExpression="SET updated_at = :u, message_count = message_count + :c",
    ExpressionAttributeValues={":u": {"S": now_iso()}, ":c": {"N": "1"}}
)
```

**Load chat history for display** (before user sends new message):
```python
# Read raw messages from S3 for display in UI
# S3 path: coaction-agent-sessions/ui-threads/session_<session_id>/agents/agent_<id>/messages/
# OR: re-initialize agent with session_manager and read agent.messages
session_manager = S3SessionManager(session_id=session_id, bucket=..., prefix=...)
agent = Agent(model=model, session_manager=session_manager)
await agent.initialize_session()   # restores messages without invoking
return agent.messages              # return to UI for display
```

---

### Agent Memory (Short + Long Term) — AgentCore Memory

This is separate from conversation history. AgentCore Memory gives the agent semantic intelligence across sessions — it knows who the user is, their preferences, past facts — not just raw chat turns.

**When to use each**:
| Memory Type | What it does | Example |
|---|---|---|
| Short-term (STM) | Stores active conversation context within a session | Keeps track of what was said in current session |
| Long-term SEMANTIC | Extracts and stores factual knowledge from conversations | "User works in underwriting department" |
| Long-term SUMMARIZATION | Generates session summaries for efficient future retrieval | "Last session: reviewed policy XYZ, flagged claim ABC" |
| Long-term USER_PREFERENCE | Learns and stores user behavior patterns | "User prefers bullet-point summaries" |

**Combined pattern** — use both S3SessionManager (raw history) AND AgentCore Memory (semantic memory) together:

```python
from strands.session.s3_session_manager import S3SessionManager
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

# Option A: Use S3 for raw history, inject retrieved long-term memory into system prompt
s3_session = S3SessionManager(session_id=session_id, bucket=..., prefix=...)
# Retrieve relevant LTM facts separately and inject into system_prompt
ltm_context = retrieve_long_term_memory(user_id, query=request.input_text)
agent = Agent(
    model=model,
    system_prompt=f"{base_prompt}\n\nUser context: {ltm_context}",
    session_manager=s3_session,
    tools=[...]
)

# Option B: Use AgentCoreMemorySessionManager as the sole session manager
# (handles both STM conversation persistence + LTM extraction automatically)
config = AgentCoreMemoryConfig(memory_id=MEM_ID, session_id=session_id, actor_id=user_id)
with AgentCoreMemorySessionManager(config, region_name="us-east-1") as mem_session:
    agent = Agent(model=model, session_manager=mem_session, tools=[...])
    agent(request.input_text)
```

**Memory governance rules** (must be defined per agent in execution profile):
- `enabled`: whether memory is active
- `memory_scope`: `agent_user` | `agent_session` | `agent_task`
- `retention_days`: e.g. 90 days
- `read_enabled` / `write_enabled`
- Restricted data categories (no PII in LTM without explicit approval)
- Deletion rules (user can request memory deletion)

---

## Platform Architecture Layers

| Layer | AWS Services |
|---|---|
| Channel & Access | Amazon API Gateway (REST/HTTP/WebSocket), AWS WAF |
| Identity & Policy | Amazon Cognito / Coaction enterprise IdP, AWS IAM |
| Control Plane | Agent Registry (DynamoDB/S3), Config Store, Policy/Guardrail Assignment |
| Runtime Plane | Strands `Agent` + `BedrockModel`, AgentCore Runtime (hosting) |
| Conversation Session | S3SessionManager (Strands) — raw message history per session |
| Thread Metadata Index | DynamoDB — `agent_threads` table (UI use case only) |
| Agent Memory | AgentCore Memory via `bedrock_agentcore` session manager (STM + LTM) |
| Model Services | Bedrock Runtime via `BedrockModel`, Titan Text Embeddings V2, Cohere Rerank 3.5 |
| Knowledge | Bedrock Knowledge Bases — via Strands `retrieve` tool |
| Guardrails | Bedrock Guardrails — attached to `BedrockModel(guardrail_config=...)` |
| Tool Gateway | AgentCore Gateway — raw boto3 |
| Observability | CloudWatch + AgentCore Observability + Strands OTEL + ADOT |
| Audit | CloudTrail + platform audit store (boto3) |
| Secrets | AWS Secrets Manager + KMS (boto3) |

---

## Core Design Principle
Every agent is **configuration-driven**. The runtime loads an approved execution profile. Individual agent code must NOT hardcode: model IDs, guardrail IDs, knowledge base IDs, tool permissions, memory IDs, S3 bucket names, retention rules, or prompt behavior.

---

## Control Plane

### Responsibilities
- Agent registration (inventory of approved agents)
- Configuration management — externalized, versioned: prompts, model profiles, retrieval/memory/response settings
- Policy assignment: input/output/domain/data sensitivity/retrieval/tool/memory/escalation policies
- Knowledge binding: permitted KBs, metadata filters, citation requirements
- Tool & action binding: allowed tools, action classes, role/channel constraints
- Version management + promotion: dev → test → UAT → prod

### Data Objects
**Agent Record**: agentID, owner, status, risk tier, approved channels/KBs/tools, model/memory profile, release state

**Execution Profile**: agent version, prompt/model/retrieval/memory/tool-permission/response/logging/fallback profile

**Version Package**: config snapshot, release metadata, env target, approval record, deployment trace

---

## Runtime Orchestration Sequence (must follow this exact order)
```
1.  agent_registry.get_active_agent(agent_id)
2.  profile_repo.get_profile(agent_id, version)
3.  authorization.authorize_invocation(identity, agent, profile)
4.  guardrails.check_input(request, profile)           ← input guardrail (also on BedrockModel)
5.  memory.read(request, identity, profile)             ← retrieve LTM context if applicable
6.  retriever.retrieve(request, identity, profile)      ← Strands retrieve tool
7.  model_gateway.invoke(...)                           ← Strands Agent + BedrockModel
8.  tool_gateway.execute_readonly_tools(...)            ← AgentCore Gateway via boto3
9.  response_composer.compose(...)
10. guardrails.check_output(response, profile)          ← output guardrail (also on BedrockModel)
11. memory.write(request, response, identity, profile)  ← flush LTM via session manager
12. session.update_thread_metadata(...)                 ← update DynamoDB thread record (UI only)
13. telemetry.emit_invocation(...)                      ← CloudWatch + Strands OTEL
14. audit.record_invocation(...)                        ← metadata only, no raw payload
15. return response (with session_id)
```

---

## Python Package Structure
```
coaction_agent_platform/
├── app/
│   ├── main.py
│   ├── routers/
│   │   ├── invoke.py          # POST /v1/agents/{agent_id}/invoke
│   │   ├── threads.py         # GET /v1/users/{user_id}/threads
│   │   │                      # GET /v1/threads/{session_id}/messages
│   │   │                      # DELETE /v1/threads/{session_id}
│   │   ├── sessions.py        # GET/DELETE /v1/sessions/{session_id}
│   │   ├── feedback.py
│   │   └── health.py
│   ├── dependencies/          # identity.py, services.py, settings.py
│   └── middleware/            # correlation.py, telemetry.py, errors.py
├── domain/                    # invocation.py, identity.py, execution_profile.py,
│                              # retrieval.py, memory.py, tools.py, response.py, audit.py
├── runtime/                   # base_agent.py, strands_agent.py, orchestrator.py,
│                              # context_builder.py, response_composer.py, host_adapter.py
├── control_plane/             # agent_registry.py, execution_profile_repository.py,
│                              # prompt_repository.py, policy_repository.py, tool_registry.py
├── services/                  # authorization.py, guardrails.py, retrieval.py, memory.py,
│                              # model_gateway.py, tool_gateway.py, telemetry.py, audit.py,
│                              # thread_service.py   ← manages DynamoDB thread metadata
├── adapters/
│   ├── aws/                   # boto3_factory.py, dynamodb.py, s3.py, secrets_manager.py,
│   │                          # bedrock_model.py, bedrock_kb.py, bedrock_guardrails.py,
│   │                          # agentcore_gateway.py, agentcore_memory.py,
│   │                          # cloudwatch.py, eventbridge.py
│   └── enterprise/            # readonly_api_adapter.py
├── agents/                    # readonly_agent.py, retrieval_agent.py, templates.py
└── tests/                     # unit/, integration/, regression/
```

---

## Core Domain Models (Pydantic)

```python
class AgentInvocationRequest(BaseModel):
    agent_id: str
    input_text: str
    session_id: str | None = None   # None = new session, value = continue existing
    channel: Literal["api", "ui"] = "api"
    request_metadata: dict[str, Any] = Field(default_factory=dict)

class IdentityContext(BaseModel):
    user_id: str
    roles: list[str] = Field(default_factory=list)
    channel: str
    application_id: str | None = None
    session_id: str | None = None
    correlation_id: str
    claims: dict[str, Any] = Field(default_factory=dict)

class SourceCitation(BaseModel):
    source_id: str
    title: str | None = None
    uri: str | None = None
    chunk_id: str | None = None
    score: float | None = None

class ToolResult(BaseModel):
    tool_id: str
    action_class: Literal["read"]
    status: Literal["success", "failed", "blocked"]
    result_summary: str | None = None
    error_code: str | None = None

class AgentInvocationResponse(BaseModel):
    status: Literal["success", "clarification_required", "blocked", "escalated", "error"]
    answer: str
    citations: list[SourceCitation] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    session_id: str         # always returned — new UUID if this was a new session
    correlation_id: str
    model_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class ThreadSummary(BaseModel):
    session_id: str
    thread_title: str
    agent_id: str
    created_at: str
    updated_at: str
    message_count: int

class ThreadMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: str
```

---

## Execution Profile Models (Pydantic)

```python
class ModelProfile(BaseModel):
    provider: Literal["bedrock"] = "bedrock"
    model_id: str                              # e.g. "us.amazon.nova-premier-v1:0"
    temperature: float = 0.0
    max_tokens: int | None = None
    fallback_model_id: str | None = None

class RetrievalProfile(BaseModel):
    provider: Literal["bedrock_knowledge_base"] = "bedrock_knowledge_base"
    enabled: bool = True
    knowledge_base_ids: list[str]
    metadata_filters: dict[str, Any] = Field(default_factory=dict)
    reranking_enabled: bool = True
    min_confidence: float | None = None
    citations_required: bool = True

class MemoryProfile(BaseModel):
    provider: Literal["agentcore_memory"] = "agentcore_memory"
    enabled: bool = True
    memory_id: str                             # AgentCore Memory resource ID
    memory_scope: Literal["agent_user", "agent_session", "agent_task"] = "agent_user"
    retention_days: int = 90
    ltm_strategies: list[Literal["SEMANTIC", "SUMMARIZATION", "USER_PREFERENCE"]] = []
    read_enabled: bool = True
    write_enabled: bool = True

class SessionProfile(BaseModel):
    provider: Literal["s3"] = "s3"
    bucket: str                                # from config — never hardcoded
    prefix: str = "sessions/"
    conversation_window_size: int = 10         # SlidingWindowConversationManager size

class ToolPermission(BaseModel):
    tool_id: str
    action_class: Literal["read"] = "read"
    allowed_roles: list[str] = Field(default_factory=list)
    requires_approval: bool = False

class GuardrailProfile(BaseModel):
    guardrail_id: str | None = None
    guardrail_version: str | None = None
    input_check_enabled: bool = True
    output_check_enabled: bool = True

class ObservabilityProfile(BaseModel):
    provider: Literal["cloudwatch"] = "cloudwatch"
    emit_metrics: bool = True
    emit_traces: bool = True
    log_raw_prompt: bool = False      # MUST always be False
    log_raw_response: bool = False    # MUST always be False

class ExecutionProfile(BaseModel):
    agent_id: str
    version: str
    orchestration_framework: Literal["strands"] = "strands"
    prompt_template_id: str
    model_profile: ModelProfile
    retrieval_profile: RetrievalProfile
    memory_profile: MemoryProfile
    session_profile: SessionProfile
    tool_permissions: list[ToolPermission] = Field(default_factory=list)
    guardrail_profile: GuardrailProfile
    observability_profile: ObservabilityProfile = ObservabilityProfile()
    response_contract_version: str = "v1"
```

---

## Strands Agent Production Configuration
```python
from strands import Agent
from strands.models import BedrockModel
from strands.session.s3_session_manager import S3SessionManager
from strands.agent.conversation_manager import SlidingWindowConversationManager

model = BedrockModel(
    model_id=profile.model_profile.model_id,
    temperature=profile.model_profile.temperature,
    max_tokens=profile.model_profile.max_tokens,
    guardrail_config={
        "guardrailIdentifier": profile.guardrail_profile.guardrail_id,
        "guardrailVersion": profile.guardrail_profile.guardrail_version,
    }
)
session_manager = S3SessionManager(
    session_id=session_id,
    bucket=profile.session_profile.bucket,
    prefix=profile.session_profile.prefix,
    boto_session=boto_session
)
conversation_manager = SlidingWindowConversationManager(
    window_size=profile.session_profile.conversation_window_size
)
agent = Agent(
    model=model,
    system_prompt=prompt_template,          # from control plane
    tools=[retrieve, *approved_tools],      # explicit list only
    session_manager=session_manager,
    conversation_manager=conversation_manager
)
```

---

## RuntimeHostAdapter (hosting-neutral — open decision)
```python
from abc import ABC, abstractmethod

class RuntimeHostAdapter(ABC):
    @abstractmethod
    async def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

class LocalFastApiRuntimeHost(RuntimeHostAdapter):
    async def invoke(self, payload): ...

class AgentCoreRuntimeHost(RuntimeHostAdapter):
    async def invoke(self, payload):
        client = boto3_factory.client("bedrock-agentcore")
        response = client.invoke_agent_runtime(
            agentRuntimeArn=self.agent_runtime_arn,
            runtimeSessionId=payload["session_id"],
            payload=json.dumps(payload).encode()
        )
        return json.loads(response["response"].read())
```

---

## Deployment — Amazon Bedrock AgentCore Runtime

### Mandatory Requirements
- Platform: `linux/arm64`
- Required endpoints: `POST /invocations` + `GET /ping`
- Port: `8080`
- Container pushed to Amazon ECR before deployment

### Custom FastAPI Approach (project approach)
```python
from fastapi import FastAPI
app = FastAPI()

@app.post("/invocations")
async def invoke_agent(request: AgentInvocationRequest, ...):
    return await orchestrator.execute(request, identity)

@app.get("/ping")
async def ping():
    return {"status": "healthy"}
```

### Dockerfile (ARM64)
```dockerfile
FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.11-bookworm-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache
COPY . ./
EXPOSE 8080
CMD ["opentelemetry-instrument", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Deploy via boto3
```python
client = boto3.client("bedrock-agentcore-control", region_name="us-east-1")
response = client.create_agent_runtime(
    agentRuntimeName="coaction-agent",
    agentRuntimeArtifact={
        "containerConfiguration": {
            "containerUri": "<account>.dkr.ecr.<region>.amazonaws.com/<repo>:latest"
        }
    },
    networkConfiguration={"networkMode": "PUBLIC"},
    roleArn="arn:aws:iam::<account>:role/AgentRuntimeRole"
)
```

### Invoke via boto3
```python
client = boto3.client("bedrock-agentcore", region_name="us-east-1")
response = client.invoke_agent_runtime(
    agentRuntimeArn=agent_runtime_arn,
    runtimeSessionId=session_id,     # 33+ characters
    payload=json.dumps({"prompt": user_input}).encode(),
    qualifier="DEFAULT"
)
```

### Observability Setup
```
# requirements.txt
aws-opentelemetry-distro>=0.10.1

# Dockerfile CMD — auto-instrumentation
CMD ["opentelemetry-instrument", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```
One-time: Enable CloudWatch Transaction Search via CloudWatch console → Application Signals → Enable.

---

## FastAPI Endpoints
```
POST   /v1/agents/{agent_id}/invoke              — invoke agent (headless + UI)
GET    /v1/users/{user_id}/threads               — list threads for user (UI only, queries DynamoDB)
GET    /v1/threads/{session_id}/messages         — load full chat for thread (UI only, reads S3)
DELETE /v1/threads/{session_id}                  — delete thread (S3 + DynamoDB)
GET    /v1/agents/{agent_id}                     — agent metadata
GET    /v1/sessions/{session_id}                 — session metadata
DELETE /v1/sessions/{session_id}                 — close/clear session
POST   /v1/feedback                              — user feedback
GET    /ping                                     — liveness (AgentCore required)
GET    /ready                                    — dependency readiness
```

---

## Identity & Authentication

Authentication terminates at **API Gateway**. FastAPI only parses validated headers.

```python
async def get_identity_context(
    x_user_id: str = Header(..., alias="X-User-Id"),         # required — 401 if missing
    x_roles: str = Header("", alias="X-Roles"),
    x_channel: str = Header("api", alias="X-Channel"),
    x_correlation_id: str = Header(..., alias="X-Correlation-Id"),  # required
    x_session_id: str | None = Header(None, alias="X-Session-Id"),
) -> IdentityContext: ...
```

---

## Boto3SessionFactory — all boto3 adapters must use this
```python
class Boto3SessionFactory:
    def __init__(self, region_name: str) -> None:
        self.region_name = region_name
        self.config = Config(
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=3,
            read_timeout=30,
        )
    def client(self, service_name: str):
        return boto3.client(service_name, region_name=self.region_name, config=self.config)
```
No adapter may create its own boto3 client independently.

---

## Tool Gateway — First Release Scope
| Action Class | First Release | Behavior |
|---|---|---|
| Read-only lookup | YES | Allowed via AgentCore Gateway when policy permits |
| Document processing | LIMITED | Allowed only if no system mutation |
| Workflow initiation | NO | Blocked |
| Write / update | NO | Blocked |
| External interaction | NO | Blocked |

Non-read actions → `ToolResult(status="blocked", error_code="NON_READ_ACTION_BLOCKED")`

---

## Telemetry & Audit — Metadata Only
```python
audit_event = {
    "correlation_id": identity.correlation_id,
    "agent_id": request.agent_id,
    "agent_version": profile.version,
    "user_id": identity.user_id,
    "channel": identity.channel,
    "session_id": session_id,
    "status": response.status,
    "model_id": response.model_id,
    "citation_count": len(response.citations),
    "tool_count": len(response.tool_results),
    "raw_prompt_logged": False,    # always False
    "raw_response_logged": False,  # always False
}
```

---

## Confirmed Architecture Decisions

| Area | Decision |
|---|---|
| API access | Amazon API Gateway |
| Authentication | Terminates at API Gateway — FastAPI parses headers only |
| Model provider | Amazon Bedrock via Strands `BedrockModel` — fully AWS-native |
| Guardrails | Bedrock Guardrails attached to `BedrockModel(guardrail_config=...)` |
| Knowledge/RAG | Bedrock Knowledge Bases via Strands `retrieve` tool |
| Conversation session (headless) | Strands `S3SessionManager` — raw message history in S3 |
| Conversation session (UI threads) | Strands `S3SessionManager` (messages) + DynamoDB `agent_threads` (metadata index) |
| Agent memory STM + LTM | AgentCore Memory via `bedrock_agentcore` session manager |
| Tool gateway | AgentCore Gateway via raw boto3 |
| Tool scope (first release) | Read-only only |
| Deployment target | Amazon Bedrock AgentCore Runtime (linux/arm64, port 8080) |
| Observability | CloudWatch + Strands OTEL + ADOT auto-instrumentation |
| Payload logging | Never log raw prompt or response |
| Boto3 client creation | Only through `Boto3SessionFactory` |
| Tool list in production | Always explicit — auto-loading disabled |
| Conversation window | `SlidingWindowConversationManager` — prevents context overflow |

## Open Decision
| Area | Status |
|---|---|
| Runtime hosting | AgentCore Runtime (target) vs ECS/Fargate — code hosting-neutral via `RuntimeHostAdapter` ABC |

---

## Developer Build Sequence
1. FastAPI shell + middleware + routers (incl. `/ping`, `/invocations`, thread endpoints)
2. API Gateway identity-context header parsing
3. Domain models + response envelope (incl. `ThreadSummary`, `ThreadMessage`)
4. Boto3SessionFactory
5. Agent registry + execution profile repositories
6. Strands base agent with `BedrockModel`
7. RuntimeOrchestrator (15-step sequence)
8. S3SessionManager integration (conversation persistence)
9. DynamoDB thread service (UI thread metadata — `agent_threads` table)
10. Bedrock KB retriever (Strands `retrieve` tool)
11. AgentCore Memory provider (`bedrock_agentcore` session manager — STM + LTM)
12. AgentCore Gateway read-only tool adapter (raw boto3)
13. CloudWatch telemetry + Strands OTEL + ADOT
14. Metadata-only audit logger
15. RetrievalAgent + ReadOnlyToolAgent templates
16. Regression test harness
17. ARM64 Docker container + ECR push + AgentCore Runtime deployment

---

## Testing Strategy
| Test Type | Scope |
|---|---|
| Unit | AuthorizationService, ExecutionProfileRepository, ResponseComposer, MemoryProvider, ToolGateway, Retriever, ThreadService |
| Contract | Execution profile schema, tool schemas, response envelope, thread metadata schema |
| Integration | Bedrock model, KB retrieval, AgentCore Memory, S3SessionManager, DynamoDB thread index, AgentCore Gateway, CloudWatch |
| Agent regression | Known prompts, citations, blocked prompts, low-confidence, read-only tools, session continuation, thread listing |
| AgentCore local | Test `/invocations` + `/ping` locally before ECR push |
