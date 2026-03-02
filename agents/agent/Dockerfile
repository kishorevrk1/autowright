FROM python:3.12-slim

# ── System tools ───────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl wget build-essential \
    ca-certificates gnupg lsb-release \
    && rm -rf /var/lib/apt/lists/*

# ── Docker CLI (for OpenHands Docker runtime) ──────────────────────────────────
# Needed when RUNTIME_TYPE=docker (local dev). Not used when RUNTIME_TYPE=local (K8s).
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
       -o /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
       https://download.docker.com/linux/debian bookworm stable" \
       > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# ── Python packages ────────────────────────────────────────────────────────────
# temporalio: Temporal worker SDK
# docker:     Python Docker SDK for workspace copy after Docker-runtime runs
RUN pip install --no-cache-dir temporalio docker

# ── OpenHands from SOURCE (editable install keeps skills/ intact) ──────────────
# pip install openhands-ai omits the skills/ directory OpenHands needs to build
# its sandbox image. Editable install from git keeps the full source tree.
#
# Patch applied inline: Ollama returns max_input_tokens=None for local models,
# which fails TokenUsage Pydantic validation (expects int). Guard with `or 0`.
RUN git clone --depth=1 https://github.com/All-Hands-AI/OpenHands.git /openhands \
    && sed -i \
       "s/context_window = self\.model_info\['max_input_tokens'\]/context_window = self.model_info.get('max_input_tokens') or 0/" \
       /openhands/openhands/llm/llm.py \
    && pip install --no-cache-dir -e /openhands

WORKDIR /app
COPY agents/agent/worker.py .
COPY agents/agent/system-prompt.md .

CMD ["python", "worker.py"]
