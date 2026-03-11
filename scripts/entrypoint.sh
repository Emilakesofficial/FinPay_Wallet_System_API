# #!/bin/sh
# set -e

# echo "Starting entrypoint"

# # # Wait for DB (basic check)
# # DB_HOST=${DATABASE_HOST:-db}
# # DB_PORT=${DATABASE_PORT:-5432}
# # # echo "Waiting for database ${DB_HOST}:${DB_PORT}..."
# # # until nc -z ${DB_HOST} ${DB_PORT}; do
# # #   sleep 1
# # # done

# echo "Running migrations..."
# python manage.py migrate --noinput

# echo "Collecting static files..."
# python manage.py collectstatic --noinput

# echo "Starting Celery worker..."
# celery -A config worker -l info &

# echo "Starting Gunicorn..."
# PORT=${PORT:-8000}
# exec gunicorn config.wsgi:application \
#   --bind 0.0.0.0:${PORT} \
#   --workers ${GUNICORN_WORKERS:-3} \
#   --log-level info

#!/bin/sh
set -e

echo "========================================="
echo "Starting Wallet System"
echo "========================================="

# Run migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Clean up stuck reconciliation reports
echo "Cleaning up stuck reconciliation reports..."
python manage.py shell << 'CLEANUP_EOF'
from django.utils import timezone
from datetime import timedelta

try:
    from apps.reconciliation.models import ReconciliationReport, ReconciliationStatus
    
    cutoff = timezone.now() - timedelta(minutes=10)
    stuck = ReconciliationReport.objects.filter(
        status__in=[ReconciliationStatus.RUNNING, ReconciliationStatus.PENDING],
        started_at__lt=cutoff
    )
    
    count = stuck.count()
    if count > 0:
        stuck.update(
            status=ReconciliationStatus.FAILED,
            completed_at=timezone.now()
        )
        print(f'✅ Cleaned up {count} stuck reports')
    else:
        print('✅ No stuck reports found')
        
except Exception as e:
    print(f'⚠️ Cleanup skipped: {e}')
    
exit()
CLEANUP_EOF

echo "========================================="
echo "Starting Celery worker in background..."
echo "========================================="
celery -A config worker \
    --loglevel=info \
    --concurrency=2 \
    --max-tasks-per-child=100 \
    --pool=solo &
CELERY_PID=$!

echo "Celery worker started with PID: $CELERY_PID"

# Trap signals to gracefully shutdown Celery
cleanup() {
    echo ""
    echo "========================================="
    echo "Shutting down gracefully..."
    echo "========================================="
    
    if [ ! -z "$CELERY_PID" ]; then
        echo "Stopping Celery worker (PID: $CELERY_PID)..."
        kill -TERM $CELERY_PID 2>/dev/null || true
        
        # Wait up to 30 seconds for graceful shutdown
        for i in $(seq 1 30); do
            if ! kill -0 $CELERY_PID 2>/dev/null; then
                echo "Celery worker stopped gracefully"
                break
            fi
            sleep 1
        done
        
        # Force kill if still running
        if kill -0 $CELERY_PID 2>/dev/null; then
            echo "Force stopping Celery worker..."
            kill -9 $CELERY_PID 2>/dev/null || true
        fi
    fi
    
    echo "Cleanup complete"
}

# Register cleanup function
trap cleanup EXIT INT TERM

# Give Celery a moment to start
echo "Waiting for Celery to initialize..."
sleep 3

# Verify Celery is running
if ! kill -0 $CELERY_PID 2>/dev/null; then
    echo "❌ ERROR: Celery worker failed to start!"
    exit 1
fi

echo "✅ Celery worker is running"

echo "========================================="
echo "Starting Gunicorn web server..."
echo "========================================="

PORT=${PORT:-8000}
WORKERS=${GUNICORN_WORKERS:-2}

# Use exec to replace shell with gunicorn (important for signal handling)
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT} \
    --workers ${WORKERS} \
    --threads 2 \
    --worker-class sync \
    --worker-tmp-dir /dev/shm \
    --log-level info \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    --enable-stdio-inheritance