#!/usr/bin/env python
"""Quick validation test for streaming implementation"""

import sys
from pathlib import Path


def test_imports():
    """Test all imports work"""
    print("1. Testing imports...")
    try:
        from lovdata_pipeline.definitions import defs

        print("   ✓ All imports successful")
        print(f"   ✓ Loaded {len(defs.assets)} assets")
        return True
    except Exception as e:
        print(f"   ✗ Import failed: {e}")
        return False


def test_chromadb_resource():
    """Test ChromaDB resource is properly configured"""
    print("\n2. Testing ChromaDB resource...")
    try:
        from lovdata_pipeline.resources import ChromaDBResource

        resource = ChromaDBResource(
            persist_directory="./test_chromadb",
            collection_name="test_collection",
        )
        print("   ✓ ChromaDB resource instantiated")
        print(f"   ✓ Persist dir: {resource.persist_directory}")
        print(f"   ✓ Collection: {resource.collection_name}")
        return True
    except Exception as e:
        print(f"   ✗ ChromaDB resource test failed: {e}")
        return False


def test_checkpoint_structure():
    """Test checkpoint file structure"""
    print("\n3. Testing checkpoint structure...")
    try:
        import json

        checkpoint_data = {
            "last_batch": 10,
            "processed_chunk_ids": [f"chunk-{i}" for i in range(100)],
            "timestamp": "2025-11-18T12:00:00",
            "total_embedded": 100,
        }

        checkpoint_file = Path("data/checkpoints/test_checkpoint.json")
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)

        with open(checkpoint_file, "w") as f:
            json.dump(checkpoint_data, f)

        size_bytes = checkpoint_file.stat().st_size
        size_kb = size_bytes / 1024

        print(f"   ✓ Checkpoint created: {size_kb:.2f} KB")

        # Cleanup
        checkpoint_file.unlink()

        if size_kb > 10:
            print(f"   ⚠ Warning: Checkpoint larger than expected ({size_kb:.2f} KB)")
            return False

        print("   ✓ Checkpoint size is good (< 10 KB)")
        return True
    except Exception as e:
        print(f"   ✗ Checkpoint test failed: {e}")
        return False


def test_definitions_valid():
    """Test Dagster definitions are valid"""
    print("\n4. Testing Dagster definitions...")
    try:
        from lovdata_pipeline.definitions import defs

        # Check all expected assets exist
        asset_names = {asset.key.to_user_string() for asset in defs.assets}
        expected_assets = {
            "lovdata_sync",
            "changed_legal_documents",
            "parsed_legal_chunks",
            "cleanup_changed_documents",
            "document_embeddings",
            "vector_database",
            "handle_deleted_documents",
        }

        if asset_names == expected_assets:
            print(f"   ✓ All {len(asset_names)} expected assets present")
        else:
            missing = expected_assets - asset_names
            extra = asset_names - expected_assets
            if missing:
                print(f"   ✗ Missing assets: {missing}")
            if extra:
                print(f"   ⚠ Extra assets: {extra}")
            return False

        # Check resources
        resources = defs.resources
        expected_resources = {"lovlig", "openai", "chromadb"}

        if set(resources.keys()) == expected_resources:
            print(f"   ✓ All {len(resources)} expected resources configured")
        else:
            missing = expected_resources - set(resources.keys())
            if missing:
                print(f"   ✗ Missing resources: {missing}")
                return False

        return True
    except Exception as e:
        print(f"   ✗ Definitions validation failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("Streaming Implementation Validation")
    print("=" * 60)

    tests = [
        test_imports,
        test_chromadb_resource,
        test_checkpoint_structure,
        test_definitions_valid,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n✗ Test crashed: {e}")
            import traceback

            traceback.print_exc()
            results.append(False)

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)

    if all(results):
        print(f"✅ All {total} tests passed!")
        print("\n✨ Ready to test with Dagster:")
        print("   1. Set test mode: export MAX_FILES=5")
        print("   2. Run: dagster dev")
        print("   3. Materialize document_embeddings in the UI")
        return 0
    else:
        print(f"❌ {total - passed}/{total} tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
