import os
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from azure.storage.blob import (
    BlobServiceClient,
    BlobClient,
    generate_blob_sas,
    BlobSasPermissions,
)
from azure.core.exceptions import AzureError
from dotenv import load_dotenv

load_dotenv()


class AzureStorageManager:
    """
    Manages file uploads and downloads to Azure Blob Storage for the tutoring system.
    Organizes files by student_id and supports various file types (PDFs, images, documents).
    """

    def __init__(
        self,
        connection_string: Optional[str] = None,
        container_name: str = "student-files",
    ):
        """
        Initialize Azure Storage manager.

        Args:
            connection_string: Azure Storage connection string (or set AZURE_STORAGE_CONNECTION_STRING env var)
            container_name: Name of the blob container to use
        """
        self.connection_string = connection_string or os.getenv(
            "AZURE_STORAGE_CONNECTION_STRING"
        )

        if not self.connection_string:
            raise ValueError(
                "Azure Storage connection string must be provided or set in AZURE_STORAGE_CONNECTION_STRING"
            )

        self.container_name = container_name
        self.blob_service_client = BlobServiceClient.from_connection_string(
            self.connection_string
        )

        # Ensure container exists
        self._ensure_container_exists()

    def _ensure_container_exists(self):
        """Create the container if it doesn't exist."""
        try:
            container_client = self.blob_service_client.get_container_client(
                self.container_name
            )
            if not container_client.exists():
                container_client.create_container()
                print(f"Created container: {self.container_name}")
        except AzureError as e:
            print(f"Error ensuring container exists: {e}")
            raise

    def upload_file(
        self,
        file_content: bytes,
        student_id: str,
        filename: str,
        subject: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Upload a file to Azure Blob Storage.

        Args:
            file_content: File content as bytes
            student_id: Unique student identifier
            filename: Original filename
            subject: Optional subject categorization
            metadata: Optional metadata dictionary

        Returns:
            Dict with upload details including blob_name and url
        """
        try:
            # Create organized blob path: student_id/subject/timestamp_filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            if subject:
                blob_name = f"{student_id}/{subject}/{timestamp}_{filename}"
            else:
                blob_name = f"{student_id}/{timestamp}_{filename}"

            # Prepare metadata
            blob_metadata = {
                "student_id": student_id,
                "original_filename": filename,
                "upload_timestamp": datetime.now().isoformat(),
            }

            if subject:
                blob_metadata["subject"] = subject

            if metadata:
                blob_metadata.update(metadata)

            # Upload blob
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name, blob=blob_name
            )

            blob_client.upload_blob(
                file_content, overwrite=False, metadata=blob_metadata
            )

            # Generate URL
            blob_url = blob_client.url

            return {
                "status": "success",
                "blob_name": blob_name,
                "url": blob_url,
                "container": self.container_name,
                "size_bytes": len(file_content),
                "uploaded_at": datetime.now().isoformat(),
            }

        except AzureError as e:
            return {
                "status": "error",
                "message": f"Failed to upload file: {str(e)}",
            }

    def download_file(self, blob_name: str) -> Optional[bytes]:
        """
        Download a file from Azure Blob Storage.

        Args:
            blob_name: Full blob name/path

        Returns:
            File content as bytes, or None if not found
        """
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name, blob=blob_name
            )

            download_stream = blob_client.download_blob()
            return download_stream.readall()

        except AzureError as e:
            print(f"Error downloading file: {e}")
            return None

    def list_student_files(
        self, student_id: str, subject: Optional[str] = None
    ) -> list[Dict[str, Any]]:
        """
        List all files for a specific student.

        Args:
            student_id: Student identifier
            subject: Optional subject filter

        Returns:
            List of file metadata dictionaries
        """
        try:
            container_client = self.blob_service_client.get_container_client(
                self.container_name
            )

            # Set name prefix for filtering
            if subject:
                name_starts_with = f"{student_id}/{subject}/"
            else:
                name_starts_with = f"{student_id}/"

            blobs = container_client.list_blobs(name_starts_with=name_starts_with)

            files = []
            for blob in blobs:
                files.append(
                    {
                        "blob_name": blob.name,
                        "size_bytes": blob.size,
                        "created_at": blob.creation_time.isoformat()
                        if blob.creation_time
                        else None,
                        "metadata": blob.metadata,
                    }
                )

            return files

        except AzureError as e:
            print(f"Error listing files: {e}")
            return []

    def delete_file(self, blob_name: str) -> bool:
        """
        Delete a file from Azure Blob Storage.

        Args:
            blob_name: Full blob name/path

        Returns:
            True if successful, False otherwise
        """
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name, blob=blob_name
            )
            blob_client.delete_blob()
            return True

        except AzureError as e:
            print(f"Error deleting file: {e}")
            return False

    def generate_download_url(
        self, blob_name: str, expiry_hours: int = 24
    ) -> Optional[str]:
        """
        Generate a temporary SAS URL for downloading a file.

        Args:
            blob_name: Full blob name/path
            expiry_hours: Hours until the URL expires

        Returns:
            Temporary download URL with SAS token
        """
        try:
            # Extract account name and key from connection string
            conn_parts = dict(
                item.split("=", 1)
                for item in self.connection_string.split(";")
                if "=" in item
            )
            account_name = conn_parts.get("AccountName")
            account_key = conn_parts.get("AccountKey")

            if not account_name or not account_key:
                return None

            # Generate SAS token
            sas_token = generate_blob_sas(
                account_name=account_name,
                container_name=self.container_name,
                blob_name=blob_name,
                account_key=account_key,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.utcnow() + timedelta(hours=expiry_hours),
            )

            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name, blob=blob_name
            )

            return f"{blob_client.url}?{sas_token}"

        except Exception as e:
            print(f"Error generating download URL: {e}")
            return None
