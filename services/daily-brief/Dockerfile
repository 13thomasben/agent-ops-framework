FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# migrations are idempotent and forward-only; safe on every boot
CMD ["sh", "-c", "python db/migrate.py && uvicorn brief.app:app --host 0.0.0.0 --port 8000"]
