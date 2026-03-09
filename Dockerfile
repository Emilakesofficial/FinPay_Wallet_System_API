FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev gcc netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps (copy whole requirements dir so -r references work)
COPY requirements/ ./requirements/
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements/prod.txt

# Copy project
COPY . /app

# Entrypoint: copy and make executable while still root
COPY ./scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN groupadd -r app && useradd -r -g app app || true
RUN chown -R app:app /app /entrypoint.sh || true
USER app

ENV PATH="/home/app/.local/bin:${PATH}"

CMD ["/entrypoint.sh"]
