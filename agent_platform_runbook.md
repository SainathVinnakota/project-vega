# Enterprise Multi-Agent Core: Architecture & Operations Runbook

This comprehensive guide serves as the authoritative operational manual for deploying, running, and scaling multi-agent architectures on the **Coaction Agent Platform**. It covers the end-to-end process for building out a completely clean cloud environment from scratch, configuring enterprise network boundaries, and leveraging the **Zero-Code Onboarding** loop to deploy new agents dynamically without container repushes.

---

## 📑 Table of Contents
1. **[Operational Paradigm & Architecture Overview](#1-operational-paradigm--architecture-overview)**
2. **[Phase 1: Ground-Up Environment Provisioning (New Account/Region)](#2-phase-1-ground-up-environment-provisioning-new-accountregion)**
   - [A. S3 Storage Persistence Setup](#a-s3-storage-persistence-setup)
   - [B. Aurora PostgreSQL Vector Database Cluster](#b-aurora-postgresql-vector-database-cluster)
   - [C. Enterprise IAM Execution Role & Policies](#c-enterprise-iam-execution-role--policies)
   - [D. Amazon Bedrock Knowledge Base (KB) Integration](#d-amazon-bedrock-knowledge-base-kb-integration)
3. **[Phase 2: One-File Deployment Automation](#3-phase-2-one-file-deployment-automation)**
   - [The Universal Bootstrap Driver (`platform_bootstrap.py`)](#the-universal-bootstrap-driver-platform_bootstrappy)
4. **[Phase 3: The "Zero-Push" Onboarding Loop (Existing Environments)](#4-phase-3-the-zero-push-onboarding-loop-existing-environments)**
   - [Step-by-Step New Agent Deployment Guide](#step-by-step-new-agent-deployment-guide)
5. **[Phase 4: Verification, Auditing, and Troubleshooting](#5-phase-4-verification-auditing-and-troubleshooting)**
   - [CloudWatch Logs and Trace Patterns](#cloudwatch-logs-and-trace-patterns)

---

## 1. Operational Paradigm & Architecture Overview

To eliminate the operational friction of updating container registries (e.g., executing 30+ manual repushes to ECS/AgentCore to tune system prompts or tweak hyper-parameters), this platform centralizes **Agent Execution Logic** into a single shared, highly optimized runtime container base layer.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                    ENTERPRISE AWS CLOUD BOUNDARY                        │
│                                                                         │
│  ┌───────────────────────┐   ┌───────────────────────────────────────┐  │
│  │  S3 Persistence Layer │   │ Aurora PostgreSQL Vector DB (RDS)     │  │
│  │  (Session Histories)  │   │ (Knowledge Base Index Embeddings)     │  │
│  └───────────▲───────────┘   └───────────────────▲───────────────────┘  │
│              │ s3:PutObject                      │ PostgreSQL Protocol  │
│              │ s3:GetObject                      │ (Security Groups)    │
│  ┌───────────┴───────────────────────────────────┴───────────────────┐  │
│  │             Shared AgentCore Runtime Container Target             │  │
│  │             (Executes via VegaPlatformExecutionRole)              │  │
│  └───────────┬───────────────────────────────────┬───────────────────┘  │
│              │ bedrock:InvokeModel               │ bedrock:Retrieve     │
│  ┌───────────▼───────────────────────────────────▼───────────────────┐  │
│  │  Amazon Bedrock Native Models                 │ Amazon Bedrock KBs│  │
│  │  (amazon.nova-pro-v1:0 / claude-3-haiku)      │ (Vector Retrieval)│  │
│  └───────────────────────────────────────────────┴───────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### The Ingress Split
* **FastAPI Target**: Serves frontends and API consumers over REST protocols, terminating client JWT authorizations, mapping tracing IDs, and maintaining strict OpenAPI documentation schemas.
* **AgentCore Wrapper**: Subscribes directly to cloud events inside sandboxed MicroVM tasks. It initializes identical framework instances directly from the environment without spawning background threads or web sockets.

---

## 2. Phase 1: Ground-Up Environment Provisioning (New Account/Region)

When initializing the platform in a completely empty AWS organization footprint, execute the infrastructure deployment sequence in the following exact order.

### A. S3 Storage Persistence Setup
Create a private, encrypted S3 bucket to persist raw conversation data files, session metadata history objects, and offline audit streams.
1. **Creation**: Provision bucket `vega-binding-authority` (or region-specific equivalent) with **Block All Public Access** completely enabled.
2. **Encryption**: Enforce Server-Side Encryption using Amazon S3-managed keys (SSE-S3) or customer-managed KMS keys.
3. **Bucket Policy Envelope**: Apply explicit bucket-level isolation rules:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "RequireEncryptedTransport",
            "Effect": "Deny",
            "Principal": "*",
            "Action": "s3:*",
            "Resource": [
                "arn:aws:s3:::vega-binding-authority",
                "arn:aws:s3:::vega-binding-authority/*"
            ],
            "Condition": {
                "Bool": {
                    "aws:SecureTransport": "false"
                }
            }
        }
    ]
}
```

### B. Aurora PostgreSQL Vector Database Cluster
Provision a highly resilient serverless database tier to maintain vector document embedding maps for dynamic Knowledge Base execution loops.
1. **Engine Selection**: Launch an **Amazon Aurora PostgreSQL-Compatible Edition** cluster (Serverless v2 recommended to optimize cost allocation during low-traffic periods).
2. **Network Security Group**: Restrict inbound port `5432` access completely. Permit network traffic ingress *only* from the explicit VPC subnet class hosting your AWS Lambda/MicroVM agent worker tasks.
3. **Database Preparation**: Authenticate against the primary instance endpoint and compile active vector engine extensions:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE SCHEMA IF NOT EXISTS bedrock_integration;

CREATE TABLE IF NOT EXISTS bedrock_integration.bedrock_kb (
    id uuid DEFAULT uuid_generate_v4() PRIMARY KEY,
    embedding vector(1536),
    chunks text,
    metadata jsonb
);

CREATE INDEX ON bedrock_integration.bedrock_kb USING hnsw (embedding vector_cosine_ops);
```

### C. Enterprise IAM Execution Role & Policies
The operational anchor of your multi-agent infrastructure is the specialized runtime role (`VegaPlatformExecutionRole`). Provision this principal with granular inline capabilities.

#### 1. Trust Relationship Policy
Permit the Bedrock cloud runtime and custom worker targets to securely request execution credentials:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "bedrock.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    },
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

#### 2. Definitive Operational Permissions JSON
Attach an inline IAM policy granting precise task capabilities across targeted AWS resources:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowBedrockModelInference",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": [
        "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0",
        "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
      ]
    },
    {
      "Sid": "AllowBedrockKnowledgeBaseRetrieval",
      "Effect": "Allow",
      "Action": [
        "bedrock:Retrieve",
        "bedrock:RetrieveAndGenerate"
      ],
      "Resource": "arn:aws:bedrock:us-east-1:513847850768:knowledge-base/*"
    },
    {
      "Sid": "AllowS3PersistenceStorage",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::vega-binding-authority",
        "arn:aws:s3:::vega-binding-authority/*"
      ]
    },
    {
      "Sid": "AllowCloudWatchObservabilityEmissions",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:us-east-1:513847850768:log-group:/aws/bedrock-agentcore/*"
    }
  ]
}
```
> [!WARNING]
> **Service Control Policy (SCP) Overrides**: If your enterprise enforces multi-region SCP blocks containing explicit regional deny conditions, avoid configuring regional cross-region IDs (`us.anthropic...`). Natively leverage specific local IDs like `amazon.nova-pro-v1:0` to guarantee pure intra-region routing compliance.

### D. Amazon Bedrock Knowledge Base (KB) Integration
1. Access the **Amazon Bedrock Console** -> **Knowledge Bases** -> **Create Knowledge Base**.
2. Assign the previously configured IAM execution role (`VegaPlatformExecutionRole`).
3. Connect your target S3 document storage bucket as the definitive data input source.
4. Select the target **Embedding Model** (e.g., `amazon.titan-embed-text-v2:0` or equivalent matching vector schema lengths).
5. Configure Vector Storage settings to target your Aurora PostgreSQL database cluster exactly, mapping schema credentials via AWS Secrets Manager securely.
6. Synchronize the Data Source to index parsed vector strings straight into Postgres tables. Note the generated authoritative **Knowledge Base ID string** (e.g., `2KMBSFAGGS`).

---

## 3. Phase 2: One-File Deployment Automation

Once base cloud resources are fully allocated, deploy the multi-agent control logic instantly using the centralized cloud bootstrap engine.

### The Universal Bootstrap Driver (`platform_bootstrap.py`)
This script securely queries running environment resources, aggregates connection topologies, verifies agent mappings, and natively issues rolling microVM Task synchronizations.

#### Execution Command
```powershell
python scripts/platform_bootstrap.py <agent_id> <s3_bucket> <iam_role_arn>
```

#### What It Does Under the Hood:
1. Parses string fields from local `.env` cache envelopes dynamically.
2. Auto-resolves Aurora PostgreSQL cluster topologies by querying `rds.describe_db_clusters()`, substituting real DNS reader host strings to completely prevent `localhost` socket connection drops inside remote MicroVM network contexts.
3. Injects authoritative model profiles (`MODEL_PROVIDER=bedrock` and `BEDROCK_MODEL_ID=amazon.nova-pro-v1:0`) directly into microVM task settings.
4. intercepts resource creation collisions (`ConflictException`) smoothly, executing an idempotent parameter update mapping across running clusters without causing service downtimes.

---

## 4. Phase 3: The "Zero-Push" Onboarding Loop (Existing Environments)

To scale operations, add new agents dynamically without modifying the container layer or repushing image files.

```text
┌────────────────────────────────────────────────────────┐
│            ZERO-CODE ONBOARDING WORKFLOW               │
│                                                        │
│  1. Create JSON Profile  ──►  2. Define System Prompt  │
│     (profiles/<id>.json)         (prompt_repository.py)│
│               │                         │              │
│               └────────────┬────────────┘              │
│                            ▼                           │
│                 3. Execute One-Line Sync               │
│                    (platform_bootstrap.py)             │
│                            │                           │
│                            ▼                           │
│                 Agent Instantly Active                 │
└────────────────────────────────────────────────────────┘
```

### Step-by-Step New Agent Deployment Guide

#### Step 1: Create the Definitive Configuration Profile JSON
Drop a dedicated metadata block into `profiles/<agent_id>.json`. For example, to instantiate a new specialized **Claims Compliance Bot**:
```json
{
  "agent_id": "claims_compliance_bot",
  "version": "1.0",
  "orchestration_framework": "strands",
  "prompt_template_id": "claims_compliance_bot",
  "model_profile": {
    "provider": "bedrock",
    "model_id": "amazon.nova-pro-v1:0",
    "temperature": 0.0,
    "max_tokens": 2048
  },
  "retrieval_profile": {
    "provider": "bedrock_knowledge_base",
    "enabled": true,
    "knowledge_base_ids": ["KBCLAIMS99"],
    "reranking_enabled": true,
    "citations_required": true
  },
  "memory_profile": {
    "provider": "agentcore_memory",
    "enabled": true,
    "memory_id": "mem_claims_compliance_v1",
    "memory_scope": "agent_session",
    "retention_days": 90,
    "ltm_strategies": ["SEMANTIC"]
  },
  "session_profile": {
    "provider": "s3",
    "bucket": "vega-binding-authority",
    "prefix": "sessions/"
  }
}
```

#### Step 2: Register System Prompt Behavior
Open `control_plane/prompt_repository.py` and populate its mapped system configuration block:
```python
self._templates["claims_compliance_bot"] = (
    "You are an expert internal claims compliance auditor. Your sole task is to verify "
    "submitted processing requests against active carrier documentation files. Ensure all "
    "determinations are accompanied by explicit manual citations."
)
```

#### Step 3: Trigger Live Environment Synchronization
Execute your single operational driver interface directly:
```powershell
python scripts/platform_bootstrap.py claims_compliance_bot vega-binding-authority arn:aws:iam::513847850768:role/VegaPlatformExecutionRole
```
**Done!** The platform runtime parses the JSON document during container execution, auto-discovers configured parameters, initializes the target foundation model using intra-region network credentials, maps targeted vector data layers, and processes live inbound execution calls cleanly. **No new Docker files required.**

---

## 5. Phase 4: Verification, Auditing, and Troubleshooting

### CloudWatch Logs and Trace Patterns
When diagnosing serverless microVM behaviors, access targeted log stream footprints via the **Amazon CloudWatch Console** under the following authoritative Log Group paths:
```text
/aws/bedrock-agentcore/runtimes/<agent_id>-<runtime_hash>-DEFAULT
```

#### Standard Audit Trace Egress
Successful invocations emit clean structured metadata streams detailing processing speeds and source mapping counts:
```json
{
  "timestamp": "2026-05-12T15:36:47Z",
  "level": "INFO",
  "logger": "audit_telemetry",
  "event": "agent_invocation_complete",
  "metadata": {
    "agent_id": "vega_binding_authority_bot",
    "session_id": "68514a2b-717d-4be6-9a1c-774a52af1a4a",
    "model_id": "amazon.nova-pro-v1:0",
    "retrieval_citations_count": 3,
    "execution_duration_ms": 1420
  }
}
```

#### Common Runtime Error Classifications & Remedies
| Observed Log Stream Signature | Root Architectural Cause | Complete Corrective Action |
| :--- | :--- | :--- |
| `psycopg2.OperationalError: connection to server at "localhost" failed` | Serverless microVM lacks proper cloud network configuration variables. | Ensure `scripts/platform_bootstrap.py` executes correctly to dynamically discover real DB endpoints and propagate string config. |
| `ValidationError: 1 validation error for IdentityContext correlation_id` | Universal entrypoint adapter omits tracking arguments. | Ensure container runtime uses fully aligned Pydantic dependency mappings as implemented in checkouts. |
| `AccessDeniedException: explicit deny in a service control policy` | Requested foundation model enforces routing calls via cross-region inference profiles (`us.anthropic...`). | Switch runtime baseline model configuration mapping to local intra-region string IDs (e.g., `amazon.nova-pro-v1:0` or `claude-3-haiku`). |

---
**Maintained by**: Coaction Advanced Multi-Agent Platform Engineering Taskforce.
👉 **[Return to Main Project README](file:///c:/users/sainath.vinnakota/project-vega/README.md)**.
