import os
from .system import TutoringRAGSystem


def initialize_tutoring_rag() -> TutoringRAGSystem:
    return TutoringRAGSystem(
        pinecone_api_key=os.getenv("PINECONE_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        pinecone_environment=os.getenv("PINECONE_ENVIRONMENT", "us-east-1"),
    )
