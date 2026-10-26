FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gcc gnupg libpq-dev fonts-dejavu-core libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
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
