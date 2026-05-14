FROM python:3.11-slim

# Installer system dependencies til Playwright/Chromium
RUN apt-get update && apt-get install -y \
    libatk1.0-0t64 \
    libatk-bridge2.0-0t64 \
    libcups2t64 \
    libatspi2.0-0t64 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2t64 \
    libnss3 \
    libnspr4 \
    libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installér Playwright og Chromium
RUN playwright install chromium
RUN playwright install-deps chromium || true

COPY crawler.py .

CMD ["python", "crawler.py"]
