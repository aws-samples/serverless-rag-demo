FROM --platform=linux/arm64 python:3.12-slim AS builder
WORKDIR /app
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

FROM --platform=linux/arm64 python:3.12-slim
RUN useradd -r -u 1001 appuser
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER appuser
EXPOSE 8080
CMD ["python", "app.py"]
