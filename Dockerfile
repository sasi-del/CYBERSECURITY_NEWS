FROM python:3.12-slim

WORKDIR /app

# System deps for cron
RUN apt-get update && apt-get install -y --no-install-recommends \
        cron \
        tini \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/reports /app/logs

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["tini", "--"]
CMD ["/docker-entrypoint.sh"]
