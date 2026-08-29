FROM python:3.11-slim AS base

LABEL maintainer="ZentropyLabs"
LABEL description="Flywheel gateway + relay remote MCP server"

WORKDIR /app

# Copy the gateway engine (harness/) and relay submodule
COPY harness/ harness/
COPY relay/src/relay/ relay_src/relay/
COPY pyproject.toml README.md LICENSE ./
COPY site/ site/

# Install flywheel (zero runtime deps) and set up relay on the path
RUN pip install --no-cache-dir -e . \
    && echo "/app/relay_src" > "$(python -c 'import site; print(site.getsitepackages()[0])')/relay.pth"

# Relay reads .env from the working directory by default
ENV RELAY_REMOTE_HOST=0.0.0.0
ENV RELAY_REMOTE_PORT=8787

EXPOSE 8787 8799

# Default: start the gateway. Override with `flywheel remote` for relay.
CMD ["flywheel", "up", "--port", "8799"]
