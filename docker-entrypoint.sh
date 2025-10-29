#!/bin/bash
set -e

# Check APP_TYPE environment variable to determine which app to run
if [ "$APP_TYPE" = "rag_server" ]; then
    echo "Starting RAG MCP Server..."
    exec python rag_mcp_server.py
elif [ "$APP_TYPE" = "mcp_host" ]; then
    echo "Starting MCP Host..."
    exec ./start_mcp_host.sh
else
    echo "ERROR: APP_TYPE environment variable not set or invalid"
    echo "Please set APP_TYPE to either 'rag_server' or 'mcp_host'"
    exit 1
fi
