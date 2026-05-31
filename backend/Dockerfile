FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev postgresql-client fonts-dejavu-core libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --system --gid 10001 bpstracker \
    && useradd --system --uid 10001 --gid bpstracker --home-dir /app --shell /usr/sbin/nologin bpstracker \
    && mkdir -p /app/data /tmp/bpstracker \
    && chown -R bpstracker:bpstracker /app /tmp/bpstracker

COPY --chown=bpstracker:bpstracker app ./app
COPY --chown=bpstracker:bpstracker tests ./tests

USER bpstracker

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
