# Project Vega: Comprehensive Codebase & Flow Manual

This document serves as the authoritative, module-by-module architectural reference mapping out the exact file responsibilities, runtime data pipelines, local developer environments, and dual-target deployment mechanics of the **Coaction Multi-Agent Core Platform**.

---

## 🧭 1. High-Level Ingress Matrix: What File Does What

The architecture leverages a hybrid runtime envelope to maximize code reuse while serving highly divergent caller classes.

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL API CONSUMERS                          │
│        (REST UI Client / Enterprise ESB Portals / API Gateway)         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / REST Protocols
┌───────────────────────────────────▼────────────────────────────────────┐
│                        FASTAPI INGRESS SHELL                           │
│                                                                        │
│   ├── app/main.py               (Uvicorn HTTP Lifecycle / Lifespan)    │
│   ├── app/dependencies/identity.py  (Header Extractor & Scope Maps)    │
│   ├── app/routers/invoke.py     (POST /v1/agents/{id}/invoke Map)      │
│   └── app/routers/threads.py    (UI Application Thread Metadata APIs)  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Shared Execution Call
┌───────────────────────────────────▼────────────────────────────────────┐
│                      UNIVERSAL ORCHESTRATION PLANE                     │
│                                                                        │
│   ├── runtime/orchestrator.py   (Master 15-Step Logic Pipeline)        │
│   ├── control_plane/registry.py (Dynamic Profile Auto-Loader)          │
│   ├── services/retrieval.py     (Strands Knowledge Base Driver)        │
│   ├── services/memory.py        (AgentCore Short/Long-Term LTM)        │
│   └── adapters/aws/dynamodb_session.py (Stateless Compute Snapshotter) │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ Direct Context Invoke
┌───────────────────────────────────┴────────────────────────────────────┐
│                 AWS INTERNAL MICROVM CLOUD TRIGGERS                    │
│      (Step Functions / EventBridge / Direct Runtime SDK Invokes)       │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ Cloud Invocations
┌───────────────────────────────────┴────────────────────────────────────┐
│                   AGENTCORE LEAN LISTENER TARGET                       │
│                                                                        │
│   └── entrypoints/agent_gateway.py  (Pure BedrockAgentCoreApp SDK Wrapper)│
└────────────────────────────────────────────────────────────────────────┘
```

---

## 📂 2. File-by-File Directory Reference

### `app/` — The External REST Framework Interface
* **`app/main.py`**: Initializes the primary FastAPI server application. Configures CORS rules, instantiates standard middleware layers, verifies local Database schemas on application lifespan triggers, and auto-loads agent profile inventories.
* **`app/dependencies/settings.py`**: Validates base string configs (`MODEL_PROVIDER`, local paths, regional constraints) via `pydantic_settings`. Reads fallback values directly from cached local `.env` structures.
* **`app/dependencies/identity.py`**: Decodes runtime context identifiers (`X-User-Id`, `X-Roles`, `X-Correlation-Id`) coming out of verified incoming request headers.
* **`app/dependencies/services.py`**: The central **Dependency Injection (DI)** factory mapping module. Natively binds singleton instance caches (`lru_cache`) for all high-level runtime services, preventing independent unmanaged service worker threads.
* **`app/routers/invoke.py`**: Maps standard multi-turn conversation payloads to target agents. Translates JSON input texts and optional Postman override tags into typed invocation schemas.
* **`app/routers/threads.py`**: Powers specific client UI interfaces. Interrogates the dedicated `agent_threads` DynamoDB GSI table for thread listings, delegates direct full-text chat file deserialization calls to backend S3 adapters, and handles hard cascade row removals.
* **`app/routers/sessions.py`**: Provides diagnostic REST read endpoints targeting active in-memory session mapping blocks.

### `domain/` — Authoritative Type Safety Contracts
* Contains strictly defined **Pydantic** models mapping structural inputs and outputs: `AgentInvocationRequest`, `IdentityContext`, `SourceCitation`, and `AgentInvocationResponse`. Enforces rigorous payload boundaries to guarantee zero unhandled serialization layer exceptions.

### `runtime/` — The Core Multi-Agent Logic Platform
* **`runtime/orchestrator.py`**: The definitive computational engine driving every single agent call across both runtime targets. Implements the strict, sequential **15-Step Request Pipeline** directly.
* **`runtime/strands_agent.py`**: Wraps external `strands.Agent` framework integrations. Manages dynamic instantiation of secure first-party Amazon model classes (`BedrockModel`) using AWS IAM identity credentials natively.
* **`runtime/response_composer.py`**: Formats valid framework outputs, extracted tool payloads, and generation timestamps into fully structured response JSON representations.

### `control_plane/` — Dynamic Configuration Auto-Loaders
* **`control_plane/agent_registry.py`**: Maps and returns operational runtime profiles (`ExecutionProfile`). Enables highly complex parameter definitions (e.g., specific target model string fallbacks, KB list scopes, long-term memory constraints) per agent entity.
* **`control_plane/prompt_repository.py`**: The centralized system prompt instructions repository. Maps specialized role-driven behavioral contexts dynamically based on active agent lookup keys.

### `services/` — Decoupled External Resource Drivers
* **`services/retrieval.py`**: Interrogates dedicated Amazon Bedrock Knowledge Bases using optimized embedded vectors to resolve runtime source citations.
* **`services/memory.py`**: Coordinates long-term and short-term semantic memory logic via high-performance AgentCore session adapters.
* **`services/telemetry.py` & `services/audit.py`**: Emits operational trace speed statistics and metadata records directly to structured CloudWatch log stream outputs while strictly preventing raw prompt persistence.

### `adapters/aws/` — Secure Cloud Connection Adapters
* **`adapters/aws/boto3_factory.py`**: The single authorized provider of verified AWS client and high-level resource objects, standardizing timeout windows and network retries globally.
* **`adapters/aws/dynamodb_session.py`**: Implements the `DynamoDBSessionRepository` interface. Snapshots serial session state variables into the specialized `vega-agent-sessions` table as a permanent container-recovery failover structure.

### `entrypoints/` — Specialized Cloud Hosting Environments
* **`entrypoints/agent_gateway.py`**: The lean serverless runtime entry loop executed natively inside sandboxed AWS MicroVM task clusters using the `BedrockAgentCoreApp` SDK. Completely omits web server layer overhead and REST auth frameworks.

---

## 🔄 3. Master Sequential Request Execution Pipeline

Regardless of whether a caller queries `app/main.py` via HTTP REST or triggers `entrypoints/agent_gateway.py` via an internal AWS event stream, the shared `RuntimeOrchestrator` executes the exact same sequence:

```text
 1. Agent Registry Validation    ──► Load agent profile parameters and execution constraints.
 2. Profile Hydration            ──► Extract target model ID, specific KB arrays, and Memory configurations.
 3. Identity Authorization       ──► Ensure request context roles align with the profile's access policy.
 4. Input Guardrails Check       ──► Run prompt validation rules to filter dangerous structural text parameters.
 5. Long-Term Memory (LTM) Read  ──► Retrieve factual insights, semantic context, and cross-session user summaries.
 6. Vector Knowledge Retrieval   ──► Execute Bedrock Knowledge Base searches for context citations.
 7. Direct Model Gate Invoke     ──► Send generation context array to target Bedrock LLMs (amazon.nova-pro-v1:0).
 8. Tool Adapter Gateways        ──► Fire read-only integrations securely to resolve domain logic lookups.
 9. Raw Response Composition     ──► Structure model texts and source objects into standardized payloads.
10. Output Guardrails Check      ──► Validate generated string objects to ensure no sensitive leakage.
11. LTM Memory Buffer Flush      ──► Write summarized context updates directly back to semantic memory engines.
12. Stateless Compute Snapshot   ──► Serialize session state arrays to the vega-agent-sessions DynamoDB table.
13. Observability Stream Egress  ──► Write processing timing statistics directly to CloudWatch logs.
14. Audit Trace Commitment       ──► Record structural metadata fields securely without logging raw prompts.
15. Response Return              ──► Send full typed JSON object back to original caller transport target.
```

---

## 💻 4. Running Locally in Development Mode

To run, debug, and trace the application natively on your local machine using configuration fallbacks:

### Prerequisites
1. Ensure your current machine working folder contains a valid `.env` configuration mapping. Use `.env.example` as a template guide:
```properties
MODEL_PROVIDER=bedrock
BEDROCK_MODEL_ID=amazon.nova-pro-v1:0
AGENTCORE_MEMORY_ENABLED=true
AGENTCORE_MEMORY_ID=your_development_memory_id
```
2. Verify local development AWS profile access keys are fully initialized in your terminal window credentials environment so `Boto3SessionFactory` can securely query your cloud database clusters and vector engines.

### Execution Command (FastAPI Live REST Shell)
Trigger the Uvicorn web wrapper directly:
```powershell
uvicorn app.main:app --reload --port 8080
```
* **Liveness Verification**: Navigate to `http://localhost:8080/health` or verify documentation interfaces natively via `http://localhost:8080/docs`.

### Testing Local API Target Ingress
Submit a test prompt via `curl` or Postman targeting your primary mapped agent:
```powershell
curl -X POST "http://localhost:8080/v1/agents/coaction_binding_authority_bot/invoke" `
  -H "Content-Type: application/json" `
  -H "X-User-Id: dev_engineer" `
  -H "X-Correlation-Id: test_local_run" `
  -d "{\"input_text\": \"What is class code 10040?\"}"
```
**Outcome**: The FastAPI layer intercepts custom JSON header context mappings, populates its validation schemas, triggers the underlying logic pipeline, and streams back real cloud-generated conversation output.

---

## ⚖️ 5. Dual-Stage Container Footprint Mechanics

The project implements a canonical multi-stage Dockerfile enabling absolute infrastructure independence.

### Image Architecture (`Dockerfile`)
* **Base Layer**: Pulls optimized, minimal Python 3.11 execution foundations. Compiles OS system extensions natively.
* **Target A (`--target runtime`)**: Renders a zero-FastAPI footprint layer. Intended exclusively for lean deployment straight to private Bedrock MicroVM serverless hosting nodes.
* **Target B (`--target api`)**: Renders a complete Uvicorn HTTP wrapper context. Distributed cleanly to ECS/Fargate container groups to host client application UI portals securely.

This architecture ensures zero-downtime scalability, absolute isolation of internal and external execution planes, and highly robust state persistence across dynamic serverless pools.
