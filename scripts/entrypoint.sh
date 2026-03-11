# #!/bin/sh
set -e

echo "Starting entrypoint"

# # # Wait for DB (basic check)
# # DB_HOST=${DATABASE_HOST:-db}
# # DB_PORT=${DATABASE_PORT:-5432}
# # # echo "Waiting for database ${DB_HOST}:${DB_PORT}..."
# # # until nc -z ${DB_HOST} ${DB_PORT}; do
# # #   sleep 1
# # # done

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Celery worker..."
celery -A config worker -l info &

echo "Starting Gunicorn..."
PORT=${PORT:-8000}
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:${PORT} \
  --workers ${GUNICORN_WORKERS:-3} \
  --log-level info

