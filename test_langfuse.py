#!/usr/bin/env python
"""Test Langfuse connection and debug span issues."""

import os

from langfuse import Langfuse


def test_langfuse_connection():
    """Test basic Langfuse connection."""
    print("🧪 Testing Langfuse Connection")
    print("=" * 50)

    # Check environment variables
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    print(f"Host: {host}")
    print(f"Public Key: {public_key[:20]}..." if public_key else "Public Key: NOT SET")
    print(f"Secret Key: {secret_key[:20]}..." if secret_key else "Secret Key: NOT SET")
    print()

    if not secret_key or not public_key:
        print("❌ Langfuse credentials not set")
        return False

    try:
        # Initialize client
        print("Initializing Langfuse client...")
        client = Langfuse(
            secret_key=secret_key,
            public_key=public_key,
            host=host,
            debug=True,  # Enable debug mode
        )

        # Test trace creation
        print("Creating test trace...")
        trace = client.trace(name="test-trace", metadata={"test": True})
        print(f"✓ Trace created: {trace.id}")

        # Test span creation
        print("Creating test span...")
        span = trace.span(name="test-span", metadata={"test": True})
        print(f"✓ Span created: {span.id}")

        # Test observation
        print("Creating test observation...")
        observation = trace.generation(
            name="test-generation",
            model="test-model",
            input={"text": "test"},
            output={"result": "success"},
        )
        print(f"✓ Observation created: {observation.id}")

        # Flush to send to Langfuse
        print("Flushing events to Langfuse...")
        client.flush()
        print("✓ Flush completed")

        print()
        print("✅ Langfuse connection successful!")
        print(f"   View at: {host}")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        print(f"   Type: {type(e).__name__}")
        import traceback

        traceback.print_exc()
        return False


def test_observe_decorator():
    """Test the @observe decorator."""
    from langfuse.decorators import observe

    print()
    print("🧪 Testing @observe Decorator")
    print("=" * 50)

    try:

        @observe(name="test-function")
        def test_function():
            """Test function with observe decorator."""
            return {"result": "success"}

        print("Calling decorated function...")
        result = test_function()
        print(f"✓ Function executed: {result}")

        # Flush
        from langfuse import get_client

        client = get_client()
        client.flush()
        print("✓ Events flushed")

        print("✅ @observe decorator works!")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_langfuse_connection()

    if success:
        test_observe_decorator()

    print()
    print("=" * 50)
    print("To disable Langfuse (if issues persist):")
    print("  unset LANGFUSE_SECRET_KEY")
    print("  unset LANGFUSE_PUBLIC_KEY")
