#!/bin/sh

set -e

echo "Starting entrypoint"

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Celery worker in background..."
celery -A config worker -l info concurrency=2 &
CELERY_PID=$!

# Trap to ensure Celery stops when Gunicorn stops
# cleanup() {
#   echo "Shutting down celery worker..."
#   kill -TERM "$CELERY_PID" 2>/dev/null || true
#   Wait "$CELERY_PID" 2>/dev/null || true
# }
# trap cleanup EXIST TERM INT

echo "Starting Gunicorn..."
PORT=${PORT:-8000}
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:${PORT} \
  --workers 2 \
  --threads 2 \
  --worker-class gthread \
  --timeout 120 \
  --log-level info \
  --access-logfile - \
  --error-logfile -


# # # Wait for DB (basic check)
# # DB_HOST=${DATABASE_HOST:-db}
# # DB_PORT=${DATABASE_PORT:-5432}
# # # echo "Waiting for database ${DB_HOST}:${DB_PORT}..."
# # # until nc -z ${DB_HOST} ${DB_PORT}; do
# # #   sleep 1
# # # done