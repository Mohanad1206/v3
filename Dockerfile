# Simple Docker image for the scraper
FROM node:20-slim

# Install Playwright deps
RUN apt-get update && apt-get install -y wget gnupg ca-certificates fonts-liberation libasound2 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 libdrm2 libgbm1 libgtk-3-0 libnss3 libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxkbcommon0 libxrandr2 libxshmfence1 xdg-utils && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package.json package.json
RUN npm i && npx playwright install --with-deps chromium
COPY . .

# Default: run with examples file
CMD ["node", "src/scrape.js", "--in", "examples/urls.txt", "--out", "out/results.ndjson"]
