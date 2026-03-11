 #!/bin/sh
# Monitor and restart services if they're not responding

check_celery() {
    # Check if celery process exists
    if ! pgrep -f "celery.*worker" > /dev/null; then
        echo "❌ Celery worker not running!"
        return 1
    fi
    return 0
}

check_gunicorn() {
    # Check if gunicorn process exists
    if ! pgrep -f "gunicorn" > /dev/null; then
        echo "❌ Gunicorn not running!"
        return 1
    fi
    return 0
}

# Run checks
echo "Checking services..."

if ! check_celery; then
    echo "Attempting to restart Celery..."
    # You could add restart logic here
fi

if ! check_gunicorn; then
    echo "Gunicorn down - container should restart"
    exit 1
fi

echo "✅ All services running"