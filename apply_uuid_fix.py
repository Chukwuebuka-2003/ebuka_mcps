import os
from pinecone import Pinecone

from dotenv import load_dotenv

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("INDEX_NAME", "llamarag")  # or hardcode if preferred

if not PINECONE_API_KEY or not INDEX_NAME:
    raise ValueError(
        "Please set PINECONE_API_KEY and INDEX_NAME environment variables."
    )

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(INDEX_NAME)
index.delete(delete_all=True)

print(f"All data in index '{INDEX_NAME}' has been deleted.")
