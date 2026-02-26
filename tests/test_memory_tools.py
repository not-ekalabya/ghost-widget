#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for memory tool calls in ghost-widget
"""

import sys
import os
import json

# Fix Unicode encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from backend import BackgroundCompanion

def test_memory_tools():
    print("=" * 60)
    print("Testing Memory Tool Call System")
    print("=" * 60)

    # Initialize BackgroundCompanion
    # You'll need to set your API key here or in environment
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if not api_key:
        print("Please set GOOGLE_API_KEY or GEMINI_API_KEY environment variable")
        # You might want to exit here or handle it
        return

    print("\n1. Initializing BackgroundCompanion...")
    companion = BackgroundCompanion(
        api_key=api_key,
        user_id="test_user_memory",
        capture_interval=10
    )
    print("✓ Initialized")

    # Test 1: Store a memory
    print("\n2. Testing store_memory...")
    result = companion.store_memory(
        content="User was working on a Python machine learning project using TensorFlow and pandas for data analysis",
        summary="Working on ML project with TensorFlow",
        importance="high",
        tags=["python", "machine-learning", "tensorflow"]
    )
    print(f"Result: {result}")
    result_data = json.loads(result)
    if result_data.get("success"):
        print("✓ Memory stored successfully")
    else:
        print("✗ Failed to store memory")
        return False

    # Test 2: Store another memory
    print("\n3. Storing second memory...")
    result = companion.store_memory(
        content="User was reading documentation about React hooks and useState for frontend development",
        summary="Learning React hooks",
        importance="medium",
        tags=["javascript", "react", "frontend"]
    )
    result_data = json.loads(result)
    if result_data.get("success"):
        print("✓ Second memory stored")
    else:
        print("✗ Failed to store second memory")

    # Test 3: Get memory stats
    print("\n4. Testing get_memory_stats...")
    result = companion.get_memory_stats()
    print(f"Stats: {result}")
    result_data = json.loads(result)
    if result_data.get("success"):
        stats = result_data.get("stats", {})
        print(f"✓ Total memories: {stats.get('total_memories', 0)}")
    else:
        print("✗ Failed to get stats")

    # Test 4: Search memories
    print("\n5. Testing search_memories...")
    result = companion.search_memories(
        query="machine learning Python",
        top_k=3
    )
    print(f"Search result preview: {result[:500]}...")
    result_data = json.loads(result)
    if result_data.get("success"):
        memories = result_data.get("memories", [])
        print(f"✓ Found {len(memories)} memories")
        for i, mem in enumerate(memories[:2], 1):
            print(f"\n  Memory {i}:")
            print(f"    Summary: {mem.get('summary', 'N/A')}")
            print(f"    Importance: {mem.get('importance', 'N/A')}")
            print(f"    Tags: {mem.get('tags', [])}")
            print(f"    Temporal Score: {mem.get('temporal_score', 0.0):.3f}")
    else:
        print("✗ Failed to search memories")

    # Test 5: Get recent memories
    print("\n6. Testing get_recent_memories...")
    result = companion.get_recent_memories(limit=5)
    result_data = json.loads(result)
    if result_data.get("success"):
        memories = result_data.get("memories", [])
        print(f"✓ Retrieved {len(memories)} recent memories")
        for i, mem in enumerate(memories, 1):
            print(f"  {i}. {mem.get('summary', 'N/A')}")
    else:
        print("✗ Failed to get recent memories")

    print("\n" + "=" * 60)
    print("Memory Tool Tests Completed!")
    print("=" * 60)

    # Cleanup option (commented out by default)
    # print("\n7. Testing clear_memories (skipped - uncomment to test)...")
    # result = companion.clear_memories(confirm=True)
    # print(f"Clear result: {result}")

    return True

if __name__ == "__main__":
    try:
        success = test_memory_tools()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
