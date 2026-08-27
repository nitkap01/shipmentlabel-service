FROM python:3.12-slim

# Build context is the repo root (see docker-compose.yml) so this image can
# also bundle migrations/, which lives outside backend/.
WORKDIR /app

COPY backend/pyproject.toml .
COPY backend/app ./app
RUN pip install --no-cache-dir .

COPY migrations ./migrations
ENV MIGRATIONS_DIR=/app/migrations

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=30s \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
