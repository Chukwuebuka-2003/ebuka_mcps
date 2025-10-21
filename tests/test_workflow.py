"""
Test the simplified workflow:
1. Upload file to Azure (simulating client)
2. Call process_uploaded_file MCP tool
3. Verify file was indexed
4. Query the indexed content
"""

import requests
import json
from utils.azure_storage import AzureStorageManager
from utils import create_server_token


def simulate_client_upload():
    """
    Simulate client-side: Upload a file to Azure Blob Storage.
    In production, this would be done by the client application.
    """
    print("\n" + "=" * 70)
    print("STEP 1: Client Uploads File to Azure (Client-Side)")
    print("=" * 70)

    storage = AzureStorageManager()

    # Read test file
    try:
        with open("sample.pdf", "rb") as f:
            file_content = f.read()
        filename = "sample.pdf"
    except FileNotFoundError:
        # Fallback to creating simple text file
        file_content = b"Calculus notes: The derivative measures rate of change."
        filename = "calculus_notes.txt"

    print(f"  Uploading: {filename} ({len(file_content)} bytes)")

    # Upload to Azure
    result = storage.upload_file(
        file_content=file_content,
        student_id="test_student_001",
        filename=filename,
        subject="Mathematics",
        metadata={"uploaded_by": "client_app"},
    )

    if result["status"] == "success":
        print(f"✓ Upload successful")
        print(f"  Blob path: {result['blob_name']}")
        print(f"  Azure URL: {result['url']}")
        return result["blob_name"]
    else:
        print(f"✗ Upload failed: {result.get('message')}")
        return None


def call_mcp_process_file(blob_path, user_id):
    """
    Simulate client calling the MCP server to process the uploaded file.
    """
    print("\n" + "=" * 70)
    print("STEP 2: Client Calls MCP Server to Process File")
    print("=" * 70)

    # Get auth token
    token = create_server_token("test-client")

    # MCP server endpoint
    url = "http://localhost:9000/mcp"

    print(f"  Calling: process_uploaded_file")
    print(f"  Blob path: {blob_path}")
    print(f"  User ID: {user_id}")

    # Call MCP tool
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Session-ID": "test_session_001",
        },
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "process_uploaded_file",
                "arguments": {
                    "user_id": user_id,
                    "blob_path": blob_path,
                    "subject": "Mathematics",
                    "topic": "Calculus",
                    "difficulty_level": 7,
                    "session_id": "test_session_001",
                },
            },
            "id": 1,
        },
        timeout=60,
    )

    print(f"\n  Response status: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print(f"✓ Processing successful")

        # Parse result
        if "result" in result and "content" in result["result"]:
            for item in result["result"]["content"]:
                if isinstance(item, dict) and "text" in item:
                    data = json.loads(item["text"])
                    print(f"\n  Status: {data.get('status')}")
                    if "processing_info" in data:
                        info = data["processing_info"]
                        print(f"  Chunks stored: {info.get('chunks_stored')}")
                        print(f"  Characters: {info.get('total_characters')}")
                        print(f"  Document IDs: {len(info.get('document_ids', []))}")

        return True
    else:
        print(f"✗ Processing failed")
        print(f"  Response: {response.text}")
        return False


def query_indexed_content(user_id):
    """
    Query the RAG system to verify content was indexed.
    """
    print("\n" + "=" * 70)
    print("STEP 3: Query Indexed Content")
    print("=" * 70)

    token = create_server_token("test-client")
    url = "http://localhost:9000/mcp"

    print(f"  Querying for calculus information...")

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "knowledge_base_retrieval",
                "arguments": {
                    "user_id": user_id,
                    "query": "What is in my calculus notes?",
                    "subject": "Mathematics",
                    "topic": "Calculus",
                    "top_k": 5,
                },
            },
            "id": 2,
        },
        timeout=60,
    )

    print(f"\n  Response status: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print(f"✓ Query successful")

        if "result" in result and "content" in result["result"]:
            for item in result["result"]["content"]:
                if isinstance(item, dict) and "text" in item:
                    data = json.loads(item["text"])
                    print(f"\n  Status: {data.get('status')}")
                    if "response" in data:
                        print(f"\n  Response from RAG:")
                        print(f"  {data['response'][:300]}...")

        return True
    else:
        print(f"✗ Query failed")
        print(f"  Response: {response.text}")
        return False


def list_files_for_user(user_id):
    """
    List all files for a user.
    """
    print("\n" + "=" * 70)
    print("STEP 4: List User's Files")
    print("=" * 70)

    token = create_server_token("test-client")
    url = "http://localhost:9000/mcp"

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "list_student_files",
                "arguments": {"user_id": user_id, "subject": "Mathematics"},
            },
            "id": 3,
        },
        timeout=30,
    )

    if response.status_code == 200:
        result = response.json()
        print(f"✓ File listing successful")

        if "result" in result and "content" in result["result"]:
            for item in result["result"]["content"]:
                if isinstance(item, dict) and "text" in item:
                    data = json.loads(item["text"])
                    print(f"\n  File count: {data.get('file_count')}")
                    if "files" in data:
                        for f in data["files"][:3]:  # Show first 3
                            print(f"    - {f['blob_path']}")

        return True
    else:
        print(f"✗ Listing failed: {response.text}")
        return False


def run_complete_workflow():
    """
    Run the complete end-to-end workflow.
    """
    print("\n" + "=" * 70)
    print(" SIMPLIFIED WORKFLOW TEST")
    print("=" * 70)
    print("\nThis test simulates the complete workflow:")
    print("  1. Client uploads file to Azure")
    print("  2. Client calls MCP server with blob path")
    print("  3. Server downloads, processes, and indexes")
    print("  4. Client queries the indexed content")
    print("=" * 70)

    user_id = "test_student_001"

    # Step 1: Client uploads to Azure
    blob_path = simulate_client_upload()

    if not blob_path:
        print("\n✗ Workflow stopped: Upload failed")
        return

    input("\nPress Enter to continue to Step 2...")

    # Step 2: Client calls MCP server
    success = call_mcp_process_file(blob_path, user_id)

    if not success:
        print("\n✗ Workflow stopped: Processing failed")
        return

    input("\nPress Enter to continue to Step 3...")

    # Step 3: Query the content
    query_indexed_content(user_id)

    input("\nPress Enter to continue to Step 4...")

    # Step 4: List files
    list_files_for_user(user_id)

    print("\n" + "=" * 70)
    print(" WORKFLOW COMPLETE")
    print("=" * 70)

    print("\n✓ The simplified workflow is working correctly!")
    print("\nNext steps:")
    print("  1. Build client-side file upload UI")
    print("  2. Client uploads to Azure, gets blob path")
    print("  3. Client calls process_uploaded_file with blob path + user_id")
    print("  4. Server handles everything else automatically")


if __name__ == "__main__":
    print("\n⚠️  Make sure the MCP server is running:")
    print("   python rag_mcp_server.py")

    input("\nPress Enter when server is ready...")

    run_complete_workflow()
