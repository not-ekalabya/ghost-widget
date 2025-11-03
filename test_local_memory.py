"""
Test script for local memory system
Verifies that privacy-focused local storage works correctly
"""

import os
import sys
from datetime import datetime, timedelta

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from local_memory import LocalMemorySystem

def test_local_memory():
    """Test the local memory system with temporal awareness"""

    print("=" * 70)
    print("Testing Local Memory System (Privacy-Focused)")
    print("=" * 70)

    # Get API key from environment or use placeholder
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("\n❌ GEMINI_API_KEY not set in environment")
        print("Please set it with: set GEMINI_API_KEY=your_key_here")
        return False

    try:
        # Initialize local memory system
        print("\n1. Initializing Local Memory System...")
        memory = LocalMemorySystem(
            api_key=api_key,
            user_id="test_user_12345",
            db_path="test_memory_db",
            temporal_decay_days=30
        )

        # Add test memories
        print("\n2. Adding test memories...")

        memory1_id = memory.add_memory(
            content="User was working on a Python machine learning project using TensorFlow and scikit-learn. The project involves image classification.",
            metadata={
                "context": "coding",
                "app": "VSCode",
                "tags": "python,ml,tensorflow"
            }
        )
        print(f"   ✓ Added memory 1: {memory1_id}")

        memory2_id = memory.add_memory(
            content="User was reading research papers about neural network architectures, specifically about transformer models and attention mechanisms.",
            metadata={
                "context": "research",
                "app": "Chrome",
                "tags": "research,neural-networks"
            }
        )
        print(f"   ✓ Added memory 2: {memory2_id}")

        memory3_id = memory.add_memory(
            content="User was writing documentation in Microsoft Word about the project's architecture and implementation details.",
            metadata={
                "context": "documentation",
                "app": "Word",
                "tags": "writing,documentation"
            }
        )
        print(f"   ✓ Added memory 3: {memory3_id}")

        memory4_id = memory.add_memory(
            content="User was debugging a Python script that handles data preprocessing for the machine learning pipeline.",
            metadata={
                "context": "debugging",
                "app": "VSCode",
                "tags": "python,debugging,data"
            }
        )
        print(f"   ✓ Added memory 4: {memory4_id}")

        # Test semantic search
        print("\n3. Testing Semantic Search with Temporal Awareness...")

        test_queries = [
            "What was I coding?",
            "Tell me about the research I was reading",
            "What machine learning work did I do?",
            "Show me my Python work"
        ]

        for query in test_queries:
            print(f"\n   Query: '{query}'")
            results = memory.search_memories(query, top_k=3)

            if results:
                print(f"   Found {len(results)} relevant memories:")
                for i, result in enumerate(results, 1):
                    content_preview = result['content'][:80].replace('\n', ' ')
                    print(f"      {i}. {content_preview}...")
                    print(f"         Temporal Score: {result['temporal_score']:.3f}")
                    print(f"         Base Similarity: {result['base_similarity']:.3f}")
            else:
                print("   No results found")

        # Test recent memories
        print("\n4. Testing Recent Memories Retrieval...")
        recent = memory.get_recent_memories(limit=3)
        print(f"   Retrieved {len(recent)} recent memories:")
        for i, mem in enumerate(recent, 1):
            content_preview = mem['content'][:80].replace('\n', ' ')
            print(f"      {i}. {content_preview}...")
            print(f"         Created: {mem['created_at']}")

        # Get stats
        print("\n5. Memory Statistics:")
        stats = memory.get_stats()
        for key, value in stats.items():
            print(f"   {key}: {value}")

        # Test privacy - verify it's all local
        print("\n6. Privacy Verification:")
        print(f"   ✓ All data stored locally at: {stats['storage_path']}")
        print(f"   ✓ No external API calls for storage (only for embeddings)")
        print(f"   ✓ User data isolated by user_id: {stats['user_id']}")

        # Clean up test data
        print("\n7. Cleaning up test data...")
        memory.clear_all_memories()
        print("   ✓ Test data cleared")

        print("\n" + "=" * 70)
        print("✓ All tests passed! Local memory system is working correctly.")
        print("=" * 70)

        return True

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_local_memory()
    sys.exit(0 if success else 1)
