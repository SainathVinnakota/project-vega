FROM public.ecr.aws/docker/library/python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Ensure entrypoint is executable
RUN chmod +x entrypoints/underwriting_agent.py

# Expose port 8080 (AgentCore default)
EXPOSE 8080

# Command to run the agent
CMD ["python", "entrypoints/underwriting_agent.py"]
