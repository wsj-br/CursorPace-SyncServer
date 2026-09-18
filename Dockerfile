FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ARG BUILD_TIMESTAMP=
RUN ts="${BUILD_TIMESTAMP}"; \
    if [ -z "$ts" ]; then ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"; fi; \
    printf '%s\n' "$ts" > /app/app/BUILD_TIMESTAMP
EXPOSE 7050
VOLUME /data
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import os,urllib.request; p=os.environ.get('PORT','7050'); urllib.request.urlopen(f'http://127.0.0.1:{p}/healthz')"
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7050}"]
