FROM python:3.12-slim

WORKDIR /app

# Build tooling for the wheels that do not ship one for slim, and nothing else:
# this image serves a static-ish site, it has no media pipeline to feed.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Firefox for Playwright, plus the libraries it needs on Debian Trixie.
# Firefox rather than Chromium because the Playwright Chromium build crashes the
# renderer on complex pages on Trixie ARM64, and `playwright install-deps` fails
# there (Ubuntu package names differ), so the equivalents are named directly.
RUN python3 -m playwright install firefox
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxcb-shm0 libx11-xcb1 libx11-6 libxcb1 libxext6 libxrandr2 \
    libxcomposite1 libxcursor1 libxdamage1 libxfixes3 libxi6 \
    libgtk-3-0 libpangocairo-1.0-0 libpango-1.0-0 libatk1.0-0 \
    libcairo-gobject2 libcairo2 libgdk-pixbuf-xlib-2.0-0 libglib2.0-0 \
    libxrender1 libasound2 libfreetype6 libfontconfig1 libdbus-1-3 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY . .

ENV FLASK_APP=run.py
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /app/instance

EXPOSE 7003

CMD ["gunicorn", "--bind", "0.0.0.0:7003", "--timeout", "120", "--workers", "2", "run:app"]
