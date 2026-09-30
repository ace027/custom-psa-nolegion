ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
# Runtime deps only (no dev extras), read from pyproject.toml so there is one list to maintain
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/req.txt \
 && pip install --no-cache-dir -r /tmp/req.txt
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN useradd --system --uid 10001 psa \
 && mkdir -p /data/attachments && chown -R psa /app /data
ENV ATTACHMENTS_DIR=/data/attachments
USER psa
EXPOSE 8000
# --proxy-headers so audit-log IPs are the real client IPs as forwarded by Caddy
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
