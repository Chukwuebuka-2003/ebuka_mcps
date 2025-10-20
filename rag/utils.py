import json
from typing import Dict, Any


def sanitize_pinecone_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Remove None values and serialize complex types for Pinecone."""
    clean = {}
    for k, v in metadata.items():
        if v is None:
            continue
        if isinstance(v, (list, dict)):
            v = json.dumps(v)
        elif not isinstance(v, (str, int, float, bool)):
            v = str(v)
        clean[k] = v
    return clean
