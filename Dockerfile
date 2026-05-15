FROM public.ecr.aws/docker/library/python:3.11-slim AS base

# Install system dependencies required for vector databases and ORM compiling
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install layer securely
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy platform source arrays
COPY . .

EXPOSE 8080


# ── Target A: ECS / Fargate REST API Layer ───────────────────────────
FROM base AS api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]


# ── Target B: Native Serverless AgentCore Runtime Listener ───────────
FROM base AS runtime
CMD ["python", "entrypoints/agent_gateway.py"]
