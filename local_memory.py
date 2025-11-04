"""
Local Memory System with Temporal Awareness
Uses ChromaDB for vector storage and Google text-embedding-004 for embeddings
Provides privacy-focused, local-only memory storage with intelligent temporal retrieval
"""

import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path
import numpy as np
import threading

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    print("Warning: chromadb not installed. Install with: pip install chromadb")

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    print("Warning: google-generativeai not installed")


class LocalMemorySystem:
    """
    Local, privacy-focused memory system with temporal awareness.
    Uses ChromaDB for vector storage and Google's text-embedding-004 for high-quality embeddings.
    """

    def __init__(self,
                 api_key: str,
                 user_id: str = "default_user",
                 db_path: str = "local_memory",
                 temporal_decay_days: int = 30):
        """
        Initialize the local memory system.

        Args:
            api_key: Google API key for text embeddings
            user_id: User identifier for memory isolation
            db_path: Directory path for local ChromaDB storage
            temporal_decay_days: Number of days for temporal decay (older memories get lower scores)
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError("ChromaDB is required. Install with: pip install chromadb")

        if not GENAI_AVAILABLE:
            raise ImportError("Google Generative AI is required. Install with: pip install google-generativeai")

        self.api_key = api_key
        self.user_id = user_id
        self.db_path = Path(db_path)
        self.temporal_decay_days = temporal_decay_days

        # Thread safety lock for ChromaDB operations
        self._db_lock = threading.RLock()

        # Configure Google AI for embeddings
        genai.configure(api_key='AIzaSyBY6rQz-TCRenrrdXv2uKbE4GTbgHQbLuk')

        # Initialize ChromaDB with persistent storage
        self.db_path.mkdir(exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(
                anonymized_telemetry=False,  # Privacy: disable telemetry
                allow_reset=True
            )
        )

        # Create or get collection for this user
        collection_name = f"memories_{self._sanitize_user_id(user_id)}"
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"user_id": user_id, "description": "Screen context memories with temporal awareness"}
        )

        print(f"✓ Local memory system initialized for user: {user_id}")
        print(f"✓ Storage location: {self.db_path.absolute()}")
        print(f"✓ Using Google text-embedding-004 for embeddings")
        print(f"✓ Temporal decay period: {temporal_decay_days} days")

    def _sanitize_user_id(self, user_id: str) -> str:
        """Sanitize user_id for use in collection names."""
        return user_id.replace("@", "_at_").replace(".", "_").replace("-", "_")

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding using Google's text-embedding-004 model.
        This model provides high-quality embeddings (768 dimensions) optimized for retrieval.

        Args:
            text: Text to embed

        Returns:
            Embedding vector or None if generation fails
        """
        try:
            print(f"   🔍 [LocalMemory] Calling genai.embed_content API...")
            # Use text-embedding-004 for high-quality retrieval embeddings
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=text,
                task_type="retrieval_document"  # Optimized for document storage
            )
            print(f"   ✅ [LocalMemory] Embedding API call completed")
            return result['embedding']
        except Exception as e:
            print(f"   ⚠️ [LocalMemory] Failed to generate embedding: {e}")
            import traceback
            traceback.print_exc()
            return None

    def add_memory(self,
                   content: str,
                   metadata: Optional[Dict[str, Any]] = None,
                   memory_id: Optional[str] = None) -> str:
        """
        Store a memory with embedding and metadata.

        Args:
            content: The memory content to store
            metadata: Additional metadata (timestamp, context, etc.)
            memory_id: Optional custom ID (auto-generated if not provided)

        Returns:
            The ID of the stored memory
        """
        with self._db_lock:  # Thread-safe ChromaDB access
            try:
                # Generate embedding
                embedding = self.generate_embedding(content)
                if not embedding:
                    raise ValueError("Failed to generate embedding")

                # Generate ID if not provided
                if not memory_id:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    memory_id = f"mem_{timestamp}"

                # Prepare metadata
                if metadata is None:
                    metadata = {}

                # Add temporal metadata
                metadata["user_id"] = self.user_id
                metadata["created_at"] = datetime.now().isoformat()
                metadata["content_preview"] = content[:200]  # Store preview for debugging

                # Store in ChromaDB
                self.collection.add(
                    ids=[memory_id],
                    embeddings=[embedding],
                    documents=[content],
                    metadatas=[metadata]
                )

                return memory_id

            except Exception as e:
                print(f"⚠️ Error storing memory: {e}")
                raise

    def _calculate_temporal_score(self, created_at: str, base_similarity: float) -> float:
        """
        Calculate temporal decay score for memory retrieval.
        More recent memories get higher scores.

        Args:
            created_at: ISO format timestamp of memory creation
            base_similarity: Base cosine similarity score (0-1)

        Returns:
            Adjusted score with temporal decay applied
        """
        try:
            memory_time = datetime.fromisoformat(created_at)
            current_time = datetime.now()
            days_old = (current_time - memory_time).total_seconds() / 86400  # Convert to days

            # Temporal decay: exponential decay over temporal_decay_days
            # Recent memories (0 days): multiplier = 1.0
            # Half-life at temporal_decay_days/2: multiplier = 0.5
            # Old memories (temporal_decay_days): multiplier = 0.25
            decay_rate = 2.0 / self.temporal_decay_days  # Decay rate constant
            temporal_multiplier = np.exp(-decay_rate * days_old)

            # Combine semantic similarity with temporal relevance
            # Weight: 70% semantic, 30% temporal
            adjusted_score = (0.7 * base_similarity) + (0.3 * temporal_multiplier)

            return adjusted_score

        except Exception as e:
            print(f"⚠️ Error calculating temporal score: {e}")
            return base_similarity  # Fallback to base similarity

    def search_memories(self,
                       query: str,
                       top_k: int = 10,
                       filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Search for relevant memories using semantic similarity and temporal awareness.

        Args:
            query: Query text to search for
            top_k: Number of results to return
            filter_metadata: Optional metadata filters (e.g., {"user_id": "xyz"})

        Returns:
            List of memory dictionaries with content, metadata, and scores
        """
        with self._db_lock:  # Thread-safe ChromaDB access
            try:
                print(f"   🔍 [LocalMemory] Starting search_memories for query: '{query[:50]}...'")

                # Generate query embedding
                print(f"   🔍 [LocalMemory] Generating query embedding...")
                query_embedding = self.generate_embedding(query)
                if not query_embedding:
                    print("   ⚠️ [LocalMemory] Failed to generate query embedding")
                    return []
                print(f"   ✅ [LocalMemory] Query embedding generated")

                # Prepare filters
                where_filter = {"user_id": self.user_id}
                if filter_metadata:
                    where_filter.update(filter_metadata)
                print(f"   🔍 [LocalMemory] Using filter: {where_filter}")

                # Search ChromaDB (get more results for temporal re-ranking)
                search_k = min(top_k * 3, 100)  # Get 3x results for re-ranking
                print(f"   🔍 [LocalMemory] Querying ChromaDB collection for {search_k} results...")

                try:
                    # Direct query with expectation it might hang
                    # The lock prevents concurrent access which should help
                    results = self.collection.query(
                        query_embeddings=[query_embedding],
                        n_results=search_k,
                        where=where_filter,
                        include=["documents", "metadatas", "distances"]
                    )
                    print(f"   ✅ [LocalMemory] ChromaDB query completed")
                except Exception as query_error:
                    print(f"   ❌ [LocalMemory] ChromaDB query failed: {query_error}")
                    import traceback
                    traceback.print_exc()
                    return []

                # Process and re-rank results with temporal awareness
                processed_results = []

                if results and results['ids'] and len(results['ids'][0]) > 0:
                    for i in range(len(results['ids'][0])):
                        memory_id = results['ids'][0][i]
                        content = results['documents'][0][i]
                        metadata = results['metadatas'][0][i]
                        distance = results['distances'][0][i]

                        # Convert distance to similarity (ChromaDB uses L2 distance)
                        # For normalized embeddings, L2 distance relates to cosine similarity
                        base_similarity = 1.0 / (1.0 + distance)

                        # Apply temporal decay
                        created_at = metadata.get('created_at', datetime.now().isoformat())
                        final_score = self._calculate_temporal_score(created_at, base_similarity)

                        processed_results.append({
                            'id': memory_id,
                            'content': content,
                            'metadata': metadata,
                            'base_similarity': base_similarity,
                            'temporal_score': final_score,
                            'created_at': created_at
                        })

                # Sort by temporal score and return top_k
                processed_results.sort(key=lambda x: x['temporal_score'], reverse=True)
                final_results = processed_results[:top_k]

                print(f"✓ Retrieved {len(final_results)} memories (semantic + temporal ranking)")
                return final_results

            except Exception as e:
                print(f"⚠️ Error searching memories: {e}")
                import traceback
                traceback.print_exc()
                return []

    def get_recent_memories(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get most recent memories without semantic search.

        Args:
            limit: Number of recent memories to retrieve

        Returns:
            List of recent memory dictionaries
        """
        try:
            # Get all memories for this user
            results = self.collection.get(
                where={"user_id": self.user_id},
                include=["documents", "metadatas"],
                limit=limit
            )

            if not results or not results['ids']:
                return []

            # Convert to consistent format
            memories = []
            for i in range(len(results['ids'])):
                memories.append({
                    'id': results['ids'][i],
                    'content': results['documents'][i],
                    'metadata': results['metadatas'][i],
                    'created_at': results['metadatas'][i].get('created_at', 'Unknown')
                })

            # Sort by creation time (most recent first)
            memories.sort(key=lambda x: x['created_at'], reverse=True)

            return memories[:limit]

        except Exception as e:
            print(f"⚠️ Error getting recent memories: {e}")
            return []

    def delete_memory(self, memory_id: str) -> bool:
        """
        Delete a specific memory.

        Args:
            memory_id: ID of the memory to delete

        Returns:
            True if deleted successfully
        """
        try:
            self.collection.delete(ids=[memory_id])
            return True
        except Exception as e:
            print(f"⚠️ Error deleting memory: {e}")
            return False

    def clear_all_memories(self) -> bool:
        """
        Clear all memories for this user.

        Returns:
            True if cleared successfully
        """
        try:
            # Delete collection and recreate
            collection_name = f"memories_{self._sanitize_user_id(self.user_id)}"
            self.chroma_client.delete_collection(name=collection_name)

            self.collection = self.chroma_client.get_or_create_collection(
                name=collection_name,
                metadata={"user_id": self.user_id, "description": "Screen context memories with temporal awareness"}
            )

            print(f"✓ All memories cleared for user: {self.user_id}")
            return True

        except Exception as e:
            print(f"⚠️ Error clearing memories: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about stored memories.

        Returns:
            Dictionary with memory statistics
        """
        with self._db_lock:  # Thread-safe ChromaDB access
            try:
                count = self.collection.count()

                return {
                    'total_memories': count,
                    'user_id': self.user_id,
                    'storage_path': str(self.db_path.absolute()),
                    'temporal_decay_days': self.temporal_decay_days
                }

            except Exception as e:
                print(f"⚠️ Error getting stats: {e}")
                return {}


if __name__ == "__main__":
    # Test the local memory system
    print("Testing Local Memory System with Temporal Awareness\n")

    # Initialize (replace with your API key)
    api_key = "AIzaSyBY6rQz-TCRenrrdXv2uKbE4GTbgHQbLuk"
    if not api_key:
        print("Please set GEMINI_API_KEY environment variable")
        exit(1)

    memory = LocalMemorySystem(
        api_key=api_key,
        user_id="test_user",
        db_path="test_memory_db",
        temporal_decay_days=30
    )

    # Add some test memories
    print("\n1. Adding test memories...")
    memory.add_memory(
        "User was working on Python code for a machine learning project",
        metadata={"context": "coding", "app": "VSCode"}
    )

    memory.add_memory(
        "User was reading documentation about neural networks",
        metadata={"context": "research", "app": "Chrome"}
    )

    memory.add_memory(
        "User was writing a report in Microsoft Word",
        metadata={"context": "writing", "app": "Word"}
    )

    # Search memories
    print("\n2. Searching memories...")
    results = memory.search_memories("what was I coding?", top_k=5)

    for i, result in enumerate(results, 1):
        print(f"\nResult {i}:")
        print(f"  Content: {result['content'][:100]}")
        print(f"  Temporal Score: {result['temporal_score']:.3f}")
        print(f"  Created: {result['created_at']}")

    # Get stats
    print("\n3. Memory statistics:")
    stats = memory.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n✓ Test completed!")
