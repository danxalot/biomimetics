# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install system dependencies required for building Python packages
RUN apt-get update && apt-get install -y gcc python3-dev curl && rm -rf /var/lib/apt/lists/*

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
# Hotfix for persistence dependency
RUN pip install 'langgraph-checkpoint-sqlite<3.0.0'

# Copy the application code into the container at /app
COPY "main.py" "."
COPY "langgraph_agent.py" "."

COPY "memory_system.py" "."
COPY "user_interaction_agent.py" "."
COPY "google_model_limits.json" "."
COPY "mcp_client.py" "."
COPY "redis_blackboard.py" "."
COPY "blackboard_tools.py" "."
COPY "prompt_templates.py" "."
COPY "state_schemas.py" "."
COPY "litellm_integration.py" "."
COPY "langchain_tools.py" "."
COPY "granite_agents.py" "."
COPY "rabbitmq_consumer.py" "."
COPY "rabbitmq_client.py" "."
COPY "serena_integration.py" "."
COPY "arca_logging.py" "."
COPY "job_logger.py" "."
COPY "job_generator.py" "."
COPY "llm_gateway_client.py" "."
COPY "observer_agent.py" "."
COPY "holistic_auditor.py" "."

# Make port available to the world outside this container (default 8088)
EXPOSE 8088

# Set default port (can be overridden by PORT environment variable)
ENV PORT=8088
ENV REDIS_HOST=redis

# Run observer agent in background, then main app
CMD ["sh", "-c", "python observer_agent.py & uvicorn main:app --host 0.0.0.0 --port ${PORT}"]