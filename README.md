# Coaction Agent Platform — Enterprise Multi-Agent Core

An enterprise-grade, high-performance serverless multi-agent architecture built on AWS native runtime infrastructure. The platform decouples **Agent Orchestration Logic** from standalone microservices, providing a single universal control and runtime environment where new agents are provisioned dynamically via **JSON Execution Profiles** with **Zero Container Pushes**.

---

## 🏗️ 1. Master Systems Architecture

The platform operates on a strictly bifurcated paradigm: **Control Plane** (Governance & Definitions) and **Runtime Plane** (Execution & Orchestration).

```text
┌────────────────────────────────────────────────────────────────────────┐
│                             CONTROL PLANE                              │
│                                                                        │
│  ┌───────────────────────┐   ┌──────────────────────────────────────┐  │
│  │   JSON Agent Profiles │   │   PromptRepository (System Prompts)  │  │
│  └───────────┬───────────┘   └──────────────────┬───────────────────┘  │
└──────────────┼──────────────────────────────────┼──────────────────────┘
               │ Dynamic Parsing                  │ Constructor Injection
┌──────────────▼──────────────────────────────────▼──────────────────────┐
│                             RUNTIME PLANE                              │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                     Universal RuntimeOrchestrator                │  │
│  └─────┬──────────────────┬─────────────────────┬─────────────┬─────┘  │
│        │                  │                     │             │        │
│  ┌─────▼─────┐      ┌─────▼─────┐         ┌─────▼─────┐ ┌─────▼─────┐  │
│  │ Pydantic  │      │  Bedrock  │         │ AgentCore │ │ CloudWatch│  │
│  │ Guardrails│      │ Knowledge │         │ Persistent│ │ Observab. │  │
│  │ Validation│      │ Base KBs  │         │ Memory LTM│ │ Telemetry │  │
│  └───────────┘      └───────────┘         └───────────┘ └───────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

### Core Design Principles
1. **Decoupled Execution Paths**: Dual ingress patterns routing cleanly to the exact same shared orchestrator pipeline:
   - **Pathway A (REST/FastAPI)**: Intended for headless portals, web UI frontends, and external client systems requiring JWT verification, header parsing, correlation tracking, and full REST wrappers.
   - **Pathway B (Serverless MicroVM)**: Native lean Python event listeners deployed straight to AWS Bedrock AgentCore MicroVM clusters, eliminating Uvicorn layer overhead for step functions, event triggers, and internal automation.
2. **Zero Code Onboarding**: To deploy a new agent, teams drop a clean JSON document into `profiles/<agent_id>.json` containing model parameters, specific KB bindings, memory IDs, and role restrictions. The platform dynamically auto-discovers and registers the execution contract on the fly.
3. **Idempotent Deployments**: The cloud engine wrapper detects active runtime collision states (`ConflictException`), automatically pivoting from resource allocation to rolling configuration parameter synchronizations without service interruption.

---

## 🔒 2. Enterprise Governance & Security Envelope

To guarantee secure execution within strict corporate perimeters, the platform relies on granular cloud boundary constraints.

### The IAM Security Sandbox
Every AgentCore MicroVM task container executes using an assigned IAM execution role (`VegaPlatformExecutionRole`). For end-to-end functionality, the trust policy and inline operational scopes must enforce minimal privilege rules:

* **Trust Policy**: Authorizes both `bedrock.amazonaws.com` and local task workers to securely assume identity tokens.
* **Bedrock Knowledge Base Access**: Explicit policies granting `bedrock:Retrieve` and `bedrock:RetrieveAndGenerate` against targeted KB Amazon Resource Names (ARNs).
* **Model Inference Routing**: Grants `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` against configured local intra-region IDs (e.g., `amazon.nova-pro-v1:0` or `anthropic.claude-3-haiku-20240307-v1:0`) or regional Cross-Region Inference Profiles (`us.anthropic...`).
* **Storage and Session Management**: Requires `s3:GetObject` and `s3:PutObject` for raw persistence buckets, alongside basic DB network credentials for internal indexing read targets.

### Service Control Policy (SCP) Compliance
When targeting multi-tenant accounts, enterprise boundary layers frequently enforce explicit **SCP regional deny policies** blocking network access outside primary designated groups (e.g., restricted entirely to `us-east-1`). The runtime natively mitigates SCP triggers by utilizing authoritative local foundation model ID mappings, completely bypassing inter-region routing endpoints.

---

## 🚀 3. Onboarding Lifecycle: The "Zero-Push" Pattern

Gone are the days of rebuilding and publishing container base layers every time a new system prompt, retrieval filter, or model iteration is required.

### 1. Provisioning a New Agent
To onboard a new business entity (e.g., a custom Underwriter Audit Bot):
1. Create a simple JSON metadata block inside `profiles/underwriter_audit_bot.json`.
2. Populate its specific configuration profile constraints:
```json
{
  "agent_id": "underwriter_audit_bot",
  "version": "1.0",
  "orchestration_framework": "strands",
  "prompt_template_id": "underwriter_audit_bot",
  "model_profile": {
    "provider": "bedrock",
    "model_id": "amazon.nova-pro-v1:0",
    "temperature": 0.0,
    "max_tokens": 2048
  },
  "retrieval_profile": {
    "provider": "bedrock_knowledge_base",
    "enabled": true,
    "knowledge_base_ids": ["KB99XAUT01"],
    "reranking_enabled": true,
    "citations_required": true
  },
  "memory_profile": {
    "provider": "agentcore_memory",
    "enabled": true,
    "memory_id": "mem_audit_underwriter_prod",
    "memory_scope": "agent_user",
    "retention_days": 180,
    "ltm_strategies": ["SEMANTIC", "SUMMARIZATION"]
  },
  "session_profile": {
    "provider": "s3",
    "bucket": "vega-binding-authority",
    "prefix": "sessions/"
  }
}
```
3. Map the matching instruction block inside `control_plane/prompt_repository.py`.

### 2. Live Cloud Hydration
Trigger your single automated synchronization interface:
```powershell
python scripts/platform_bootstrap.py underwriter_audit_bot vega-binding-authority arn:aws:iam::513847850768:role/VegaPlatformExecutionRole
```
**Outcome**: The script loads the targeted profile parameters, dynamically aggregates connection paths, queries live cloud resources, and performs a live rolling refresh of the active AWS container parameters. **The new agent is fully operational instantly.**

---

## 📋 4. Repository Code Map

```text
├── app/
│   ├── core/           # Logging engines and context definitions
│   ├── dependencies/   # DI container mappings, static fallbacks, environment config
│   └── routers/        # External pathway REST execution routes (FastAPI)
├── agents/             # Reusable Agent Core behavioral blocks
├── control_plane/      # Enterprise AgentRegistry auto-loader and dynamic prompt database
├── domain/             # Authoritative schema contracts (Pydantic validation layers)
├── entrypoints/        # Specialized microVM serverless listener interfaces
├── profiles/           # Definitive configuration JSON payloads for dynamic auto-discovery
├── runtime/            # Shared Universal RuntimeOrchestrator and framework execution models
├── scripts/            # Fully automated AWS resource bootstrap and cloud orchestration drivers
└── services/           # Decoupled external adapter tools (retrieval, LTM memory persistence)
```

---

## 🛠️ 5. Operational Health & Telemetry

The platform mandates strict separation of runtime metrics from proprietary user datastreams.
* **Metadata-Only Audit Logs**: Emits pure structural metadata (execution speed, retrieval duration, session ID strings, confidence intervals) straight to centralized CloudWatch log groups without persisting sensitive prompt content.
* **Pydantic Validation Guardrails**: Validates input scopes, execution contexts, and egress objects at runtime to ensure zero unhandled container process exceptions.

For comprehensive end-to-end setup rules, database migrations, security group assignments, and step-by-step infrastructure provisioning instructions, refer directly to the dedicated operations runbook:
👉 **[Agent Platform Architecture & Operations Runbook](file:///c:/users/sainath.vinnakota/project-vega/agent_platform_runbook.md)**.

---

## ✅ 6. Local Pre-Push CI Verification Verifiers

To prevent breaking automated builds in remote GitHub Actions workflows (`.github/workflows/ci.yml`), developers must run code formatting, static lint analysis, and unit test suites locally before pushing commits.

### Automated Cross-Platform Check Utility
A pure Python verifier is available to automatically run **Ruff linting**, **Ruff layout formatting**, and the **Pytest regression framework** natively on Windows shells or Linux containers:

```powershell
# Run read-only conformance check
python scripts/pre_push_check.py

# Auto-fix lint infractions and format code layout in-place
python scripts/pre_push_check.py --fix
```

### Direct Makefile Targets
For standard bash shells or local dev systems with the `make` utility configured, trigger validation loops via explicit make targets:
```bash
make check    # Equivalent to check-only mode
make fix      # Equivalent to auto-fix mode
make test     # Standalone pytest suite runner
```
