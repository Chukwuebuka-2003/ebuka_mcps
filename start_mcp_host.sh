#!/bin/sh
set -e

echo "Starting MCP Host..."

# Try to run migrations, if it fails, stamp the database with the latest revision
if ! alembic upgrade head 2>/dev/null; then
    echo "Migration failed, attempting to stamp database..."
    alembic stamp head || echo "Stamp failed, continuing anyway..."
fi

# Start the application
exec uvicorn mcp_host.main:app --host 0.0.0.0 --port ${PORT:-8000}
