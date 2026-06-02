FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

# Install Node.js for channel bridge sidecar
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install sidecar Node.js dependencies
COPY sidecar/package.json sidecar/package-lock.json* sidecar/
RUN cd sidecar && npm install --production

COPY . .

EXPOSE 8080

CMD ["python", "app.py"]
