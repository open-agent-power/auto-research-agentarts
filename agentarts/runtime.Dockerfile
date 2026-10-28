# Build this context for linux/arm64. A successful local HTTP test is not an image test.
FROM python:3.12-slim
WORKDIR /app
COPY requirements-runtime.lock ./
RUN python -m pip install --no-cache-dir -r requirements-runtime.lock
COPY pyproject.toml ./
COPY src ./src
RUN python -m pip install --no-cache-dir --no-deps . \
    && useradd --uid 10001 --create-home research \
    && mkdir -p /var/lib/autoresearch \
    && chown research:research /var/lib/autoresearch
USER research
ENV AUTORESEARCH_WORKSPACE=/var/lib/autoresearch \
    AUTORESEARCH_BIND_HOST=0.0.0.0 \
    AGENT_RUN_PORT=8080 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "-m", "autoresearch.runtime"]
