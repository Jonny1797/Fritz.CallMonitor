FROM node:22-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y \
  git \
  curl \
  jq \
  libgl1 \
  libegl1 \
  libxkbcommon0 \
  libfontconfig1 \
  libdbus-1-3 \
  libglib2.0-0 \
  libpulse0 \
  && rm -rf /var/lib/apt/lists/*

# Forgejo needs no CLI: the prompt talks to its REST API with curl + jq.

# uv runs the feedback loops (pytest, ruff) and installs the Python the project
# needs (>=3.12; bookworm ships 3.11). The Qt libs above let PySide6 run the GUI
# tests headless (QT_QPA_PLATFORM=offscreen, set in tests/conftest.py);
# libpulse0 is needed by QtMultimedia (voicemail playback).
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /usr/local/bin/

# Build-args for UID/GID alignment: sandcastle docker build-image
# defaults these to the host user's UID/GID so image-built files
# and bind-mounted files share an owner without runtime chown.
ARG AGENT_UID=1000
ARG AGENT_GID=1000

# Rename the base image's "node" user to "agent" and align UID/GID.
RUN groupmod -o -g $AGENT_GID node && usermod -o -u $AGENT_UID -g $AGENT_GID -d /home/agent -m -l agent node
USER ${AGENT_UID}:${AGENT_GID}

# Install Claude Code CLI
RUN curl -fsSL https://claude.ai/install.sh | bash

# Add Claude to PATH
ENV PATH="/home/agent/.local/bin:$PATH"

WORKDIR /home/agent

# In worktree sandbox mode, Sandcastle bind-mounts the git worktree at /home/agent/workspace
# and overrides the working directory to /home/agent/workspace at container start.
# Structure your Dockerfile so that /home/agent/workspace can serve as the project root.
ENTRYPOINT ["sleep", "infinity"]
