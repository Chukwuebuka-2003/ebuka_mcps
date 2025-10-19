# ai-tutor
# AI Tutoring RAG System - Setup & Testing Guide

## 📋 Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Services](#running-the-services)
- [Testing the System](#testing-the-system)
- [API Endpoints](#api-endpoints)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

This is an AI-powered tutoring system that uses RAG (Retrieval-Augmented Generation) to provide personalized learning experiences. The system consists of two main components:

1. **RAG MCP Server** (Port 9000) - Provides RAG tools via MCP protocol
2. **MCP Host** (Port 8000) - Agent orchestration layer with FastAPI

**Key Features:**
- Personalized knowledge base for each student
- PDF and DOCX file processing and indexing
- Semantic search across student's learning materials
- Intent analysis and risk detection
- Azure Blob Storage integration
- OpenAI GPT-4 powered responses

---

## 🔧 Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.13+** 
- **uv** package manager ([Installation guide](https://github.com/astral-sh/uv))
- **Git**

### Install uv

```bash
# On macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Verify installation
uv --version
```

### Required API Keys

You'll need accounts and API keys for:
- **OpenAI** - [Get API Key](https://platform.openai.com/api-keys)
- **Pinecone** - [Get API Key](https://www.pinecone.io/)
- **Azure Storage** - [Get Connection String](https://portal.azure.com/)

---

## 💿 Installation


### 1. Create Virtual Environment

```bash
# Create a virtual environment using uv
uv venv

# Activate the virtual environment
# On macOS/Linux:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate
```

### 2. Install Dependencies

```bash
# Install all dependencies using uv
uv pip install -r pyproject.toml

# Or install directly from pyproject.toml
uv pip install -e .
```

---

## ⚙️ Configuration

### 1. Create Environment File

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

### 2. Configure Environment Variables

Edit `.env` and add your credentials:

```bash
# OpenAI Configuration
OPENAI_API_KEY=sk-your-openai-api-key-here

# Pinecone Configuration
PINECONE_API_KEY=your-pinecone-api-key-here
PINECONE_ENVIRONMENT=us-east-1

# Azure Storage Configuration
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
```

### 3. Generate Authentication Token

Generate a JWT token for MCP server authentication:

```bash
python get_auth_token.py
```

Copy the generated token and update it in `mcp_host/app.py`:

```python
MCP_TOOLS = [
    {
        "name": "turtor_rag",
        "transport_type": "streamable_http",
        "url": "http://0.0.0.0:9000/mcp",
        "headers": {
            "Authorization": "Bearer YOUR_GENERATED_TOKEN_HERE"
        },
    }
]
```

---

## 🚀 Running the Services

You need to run both services in separate terminal windows.

### Terminal 1: Start RAG MCP Server

```bash
# Activate virtual environment
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Run the RAG MCP server
python rag_mcp_server.py
```

**Expected Output:**
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:9000
```

### Terminal 2: Start MCP Host

```bash
# Activate virtual environment (in new terminal)
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Run the MCP host
python -m uvicorn mcp_host.app:app --host 0.0.0.0 --port 8000 --reload
```

**Expected Output:**
```
INFO:     Will watch for changes in these directories: ['/path/to/ed_mcp']
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
Initializing TutoringRagAgent server...
TutoringRagAgent server initialized successfully
INFO:     Application startup complete.
```

### Verify Services are Running

Open your browser and check:
- **MCP Host API Docs**: http://localhost:8000/docs
- **RAG MCP Server**: http://localhost:9000/

---

## 🧪 Testing the System

### Test 1: Create Sample PDF

First, create a sample PDF for testing:

```bash
python create_sample_pdf.py
```

This creates `sample.pdf` with calculus study content.

### Test 2: Upload a File

Use curl to upload a file:

```bash
curl -X POST "http://localhost:8000/upload-student-file" \
  -F "file=@sample.pdf" \
  -F "student_id=test_student_001" \
  -F "subject=Mathematics" \
  -F "topic=Calculus" \
  -F "difficulty_level=7"
```

**Expected Response:**
```json
{
  "status": "success",
  "message": "Your file has been received and is being processed. You'll be able to interact with its content shortly!"
}
```

### Test 3: Chat with the Tutor

Send a chat message to query the uploaded content:

```bash
curl -X POST "http://localhost:8000/chats/tutor-rag-agent" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": "What did I learn about derivatives?"
      }
    ],
    "session_id": "test_session_001"
  }'
```

**Expected Response:**
The system should retrieve relevant content from the uploaded PDF and provide a personalized response about derivatives.

### Test 4: Query Knowledge Base Directly

Test the RAG retrieval directly:

```bash
curl -X POST "http://localhost:9000/mcp" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "knowledge_base_retrieval",
      "arguments": {
        "user_id": "test_student_001",
        "query": "What is the chain rule?",
        "subject": "Mathematics",
        "topic": "Calculus",
        "top_k": 3
      }
    },
    "id": 1
  }'
```

### Test 5: View Session History

Get the conversation history:

```bash
curl -X GET "http://localhost:8000/session/test_session_001/history"
```

### Test 6: Run Complete Test Workflow

Run the automated test suite:

```bash
# Make sure both servers are running first!
python test_workflow.py
```

This will:
1. Upload a file to Azure
2. Process and index the file
3. Query the indexed content
4. List uploaded files

### Test 7: Test File Processing

Test PDF and DOCX processing:

```bash
python test_file_processor.py
```

---

## 📡 API Endpoints

### MCP Host (Port 8000)

#### POST `/chats/tutor-rag-agent`
Start a chat session with the AI tutor.

**Request:**
```json
{
  "messages": [
    {
      "role": "user",
      "content": "Explain quadratic equations"
    }
  ],
  "session_id": "session_123"
}
```

**Response:** Streaming text response

#### POST `/upload-student-file`
Upload a PDF or DOCX file for processing.

**Form Data:**
- `file`: The file to upload
- `student_id`: Student identifier
- `subject`: Subject category
- `topic`: Specific topic
- `difficulty_level`: 1-10

#### GET `/session/{session_id}/history`
Get conversation history for a session.

#### DELETE `/session/{session_id}/memory`
Clear memory for a specific session.

#### GET `/agent/info`
Get information about the agent configuration.

### RAG MCP Server (Port 9000)

#### POST `/mcp`
MCP protocol endpoint for tool calls.

**Available Tools:**
- `knowledge_base_retrieval` - Search user's knowledge base
- `upload_student_file` - Process and index uploaded files

---

## 🔍 Testing with Python

### Interactive Testing

Create a Python script `test_interactive.py`:

```python
import requests
import json

# Base URLs
MCP_HOST = "http://localhost:8000"
RAG_SERVER = "http://localhost:9000"

# Test chat
def test_chat(message, session_id="test_001"):
    response = requests.post(
        f"{MCP_HOST}/chats/tutor-rag-agent",
        json={
            "messages": [{"role": "user", "content": message}],
            "session_id": session_id
        },
        stream=True
    )
    
    print("Response:")
    for line in response.iter_lines():
        if line:
            print(line.decode('utf-8'))

# Test file upload
def test_upload(file_path, student_id, subject, topic):
    with open(file_path, 'rb') as f:
        files = {'file': f}
        data = {
            'student_id': student_id,
            'subject': subject,
            'topic': topic,
            'difficulty_level': 5
        }
        response = requests.post(
            f"{MCP_HOST}/upload-student-file",
            files=files,
            data=data
        )
    
    print(json.dumps(response.json(), indent=2))

# Run tests
if __name__ == "__main__":
    print("Testing file upload...")
    test_upload("sample.pdf", "student_123", "Mathematics", "Calculus")
    
    print("\nTesting chat...")
    test_chat("What did I learn about calculus?")
```

Run it:
```bash
python test_interactive.py
```

---

## 🐛 Troubleshooting

### Port Already in Use

**Error:** `Address already in use`

**Solution:**
```bash
# Find and kill the process using the port
# On macOS/Linux:
lsof -ti:8000 | xargs kill -9
lsof -ti:9000 | xargs kill -9

# On Windows:
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### Pinecone Connection Error

**Error:** `Failed to connect to Pinecone`

**Solutions:**
- Verify your `PINECONE_API_KEY` is correct
- Check your Pinecone index exists
- Ensure `PINECONE_ENVIRONMENT` matches your Pinecone region

### OpenAI API Error

**Error:** `Incorrect API key provided`

**Solutions:**
- Verify your `OPENAI_API_KEY` is correct
- Check you have credits in your OpenAI account
- Ensure the key has the required permissions

### Azure Storage Error

**Error:** `Azure Storage connection failed`

**Solutions:**
- Verify your `AZURE_STORAGE_CONNECTION_STRING` is correct
- Check the storage account exists and is accessible
- Ensure the container name matches in `azure_storage.py`

### MCP Authentication Error

**Error:** `Unauthorized: token verification failed`

**Solutions:**
1. Generate a new token: `python get_auth_token.py`
2. Update the token in `mcp_host/app.py`
3. Restart both servers

### Dependencies Not Found

**Error:** `ModuleNotFoundError: No module named 'X'`

**Solution:**
```bash
# Reinstall dependencies
uv pip install -r pyproject.toml --force-reinstall

# Or install specific package
uv pip install <package-name>
```

### File Processing Fails

**Error:** `Failed to extract text from PDF`

**Solutions:**
- Ensure PDF is not password-protected
- Check file is not corrupted
- Verify PyMuPDF is installed: `uv pip install pymupdf`

---

## 📊 Monitoring and Logs

### View Detailed Logs

Both servers print detailed logs. To save logs:

```bash
# RAG MCP Server
python rag_mcp_server.py > rag_server.log 2>&1

# MCP Host
python -m uvicorn mcp_host.app:app --host 0.0.0.0 --port 8000 > mcp_host.log 2>&1
```

### Check System Health

```bash
# Check MCP Host
curl http://localhost:8000/agent/info

# Check if services respond
curl -I http://localhost:8000/docs
curl -I http://localhost:9000/
```

---

## 🎓 Example Workflows

### Workflow 1: Complete Student Onboarding

```bash
# 1. Create sample study materials
python create_sample_pdf.py

# 2. Upload student's notes
curl -X POST "http://localhost:8000/upload-student-file" \
  -F "file=@sample.pdf" \
  -F "student_id=student_123" \
  -F "subject=Mathematics" \
  -F "topic=Calculus" \
  -F "difficulty_level=7"

# 3. Wait a few seconds for processing
sleep 5

# 4. Start tutoring session
curl -X POST "http://localhost:8000/chats/tutor-rag-agent" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Help me understand derivatives"}],
    "session_id": "session_123"
  }'
```

### Workflow 2: Multi-Subject Learning

```bash
# Upload multiple files for different subjects
curl -X POST "http://localhost:8000/upload-student-file" \
  -F "file=@math_notes.pdf" \
  -F "student_id=student_123" \
  -F "subject=Mathematics" \
  -F "topic=Algebra" \
  -F "difficulty_level=6"

curl -X POST "http://localhost:8000/upload-student-file" \
  -F "file=@history_notes.pdf" \
  -F "student_id=student_123" \
  -F "subject=History" \
  -F "topic=World War II" \
  -F "difficulty_level=5"

# Query across subjects
curl -X POST "http://localhost:8000/chats/tutor-rag-agent" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "What have I been studying?"}],
    "session_id": "session_123"
  }'
```

---

## 📚 Additional Resources

- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [OmniCoreAgent Documentation](https://github.com/chigwell/omnicoreagent)
- [LlamaIndex Documentation](https://docs.llamaindex.ai/)
- [Pinecone Documentation](https://docs.pinecone.io/)
- [OpenAI API Documentation](https://platform.openai.com/docs/)

---

## 🤝 Support

If you encounter issues:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review logs from both servers
3. Ensure all environment variables are set correctly
4. Verify all prerequisites are installed

---

## 📝 Notes

- The system uses JWT authentication between services
- Files are stored in Azure Blob Storage and indexed in Pinecone
- Each student has an isolated knowledge base
- Sessions maintain conversation history
- The agent autonomously decides when to use RAG tools

---
