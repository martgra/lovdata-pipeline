"""Examples of using different ChromaDB deployment modes.

This script demonstrates the three ChromaDB modes available:
1. Memory - In-memory ephemeral storage
2. Persistent - Local disk storage
3. Client - Remote server connection
"""

from lovdata_pipeline.infrastructure.chroma_client import ChromaClient

# Example 1: Memory Mode (Fast, Ephemeral)
# -----------------------------------------
# Data is stored in RAM and lost on restart
# Good for: Testing, development, experiments

print("=== Memory Mode ===")
memory_client = ChromaClient(mode="memory", collection_name="test_collection")
print("✓ Created in-memory client")
print(f"  Collection: {memory_client.collection_name}")
print(f"  Mode: {memory_client.mode}")
print()

# Example 2: Persistent Mode (Default, Recommended)
# --------------------------------------------------
# Data is saved to disk and persists across restarts
# Good for: Production on single machine, development with persistence

print("=== Persistent Mode ===")
persistent_client = ChromaClient(
    mode="persistent", persist_directory="./data/chroma", collection_name="legal_docs"
)
print("✓ Created persistent client")
print(f"  Collection: {persistent_client.collection_name}")
print(f"  Mode: {persistent_client.mode}")
print(f"  Directory: {persistent_client.persist_directory}")
print()

# Example 3: Client Mode (Remote Server)
# ---------------------------------------
# Connects to remote ChromaDB server
# Good for: Production with multiple services, distributed systems

print("=== Client Mode ===")
try:
    client_mode = ChromaClient(
        mode="client", host="localhost", port=8000, collection_name="legal_docs"
    )
    print("✓ Connected to ChromaDB server")
    print(f"  Collection: {client_mode.collection_name}")
    print(f"  Mode: {client_mode.mode}")
    server_host = client_mode.client._settings.chroma_server_host
    server_port = client_mode.client._settings.chroma_server_port
    print(f"  Server: {server_host}:{server_port}")
except Exception as e:
    print(f"✗ Could not connect to server: {e}")
    print("  Make sure ChromaDB server is running:")
    print("  docker compose up -d")
print()

# Example 4: Using the Client
# ----------------------------
print("=== Basic Operations ===")

# Upsert example data
sample_ids = ["doc1::v1::0", "doc1::v1::1"]
sample_embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
sample_metadatas = [
    {"document_id": "doc1", "text": "Example chunk 1"},
    {"document_id": "doc1", "text": "Example chunk 2"},
]

# Using persistent client for demonstration
persistent_client.upsert(ids=sample_ids, embeddings=sample_embeddings, metadatas=sample_metadatas)
print(f"✓ Upserted {len(sample_ids)} vectors")

# Get vector IDs for a document
vector_ids = persistent_client.get_vector_ids(where={"document_id": "doc1"})
print(f"✓ Found {len(vector_ids)} vectors for document 'doc1'")

# Get collection info
info = persistent_client.get_collection_info()
print("✓ Collection info:")
print(f"  Name: {info['name']}")
print(f"  Count: {info['count']}")

# Clean up
persistent_client.delete(ids=vector_ids)
print(f"✓ Deleted {len(vector_ids)} vectors")
print()

print("=== Summary ===")
print("Choose your mode based on needs:")
print("  • memory: Fast testing, data not preserved")
print("  • persistent: Simple setup, data on disk")
print("  • client: Scalable, remote access")
