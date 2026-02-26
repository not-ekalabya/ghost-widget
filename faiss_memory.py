"""
FAISS-based Local Memory System with Temporal Awareness
Uses FAISS for vector storage and Google text-embedding-004 for embeddings
Provides privacy-focused, local-only memory storage with intelligent temporal retrieval
"""

import os
import json
import pickle
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import numpy as np
import threading

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("Warning: faiss-cpu not installed. Install with: pip install faiss-cpu")

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    print("Warning: google-generativeai not installed")


class FAISSMemorySystem:
    """
    Local, privacy-focused memory system with temporal awareness using FAISS.
    Uses FAISS for vector storage and Google's text-embedding-004 for high-quality embeddings.
    """

    def __init__(self,
                 api_key: str,
                 user_id: str = "default_user",
                 db_path: str = "faiss_memory",
                 temporal_decay_days: int = 30):
        """
        Initialize the FAISS memory system.

        Args:
            api_key: Google API key for text embeddings
            user_id: User identifier for memory isolation
            db_path: Directory path for local FAISS storage
            temporal_decay_days: Number of days for temporal decay (older memories get lower scores)
        """
        if not FAISS_AVAILABLE:
            raise ImportError("FAISS is required. Install with: pip install faiss-cpu")

        if not GENAI_AVAILABLE:
            raise ImportError("Google Generative AI is required. Install with: pip install google-generativeai")

        self.api_key = api_key
        self.user_id = user_id
        self.db_path = Path(db_path)
        self.temporal_decay_days = temporal_decay_days

        # Thread safety lock for FAISS operations
        self._db_lock = threading.RLock()

        # Configure Google AI for embeddings
        genai.configure(api_key=api_key)

        # Initialize FAISS index
        self.db_path.mkdir(exist_ok=True)
        self.dimension = 768  # Google text-embedding-004 dimension

        # Use IndexFlatL2 for exact search (can upgrade to IndexIVFFlat for larger datasets)
        self.index = faiss.IndexFlatL2(self.dimension)

        # Storage for metadata (FAISS only stores vectors)
        self.metadata_store = []  # List of {id, content, metadata, created_at}
        self.id_counter = 0

        # Load existing index if available
        self._load_index()

        print(f"✓ FAISS memory system initialized for user: {user_id}")
        print(f"✓ Storage location: {self.db_path.absolute()}")
        print(f"✓ Using Google text-embedding-004 for embeddings")
        print(f"✓ Temporal decay period: {temporal_decay_days} days")
        print(f"✓ Current memories: {len(self.metadata_store)}")

    def _load_index(self):
        """Load FAISS index and metadata from disk"""
        index_path = self.db_path / "faiss.index"
        metadata_path = self.db_path / "metadata.pkl"

        if index_path.exists() and metadata_path.exists():
            try:
                # Load FAISS index
                self.index = faiss.read_index(str(index_path))

                # Load metadata
                with open(metadata_path, 'rb') as f:
                    data = pickle.load(f)
                    self.metadata_store = data['metadata']
                    self.id_counter = data['id_counter']

                print(f"✓ Loaded {len(self.metadata_store)} existing memories from disk")
            except Exception as e:
                print(f"⚠️ Error loading index: {e}")
                # Reset to empty if load fails
                self.index = faiss.IndexFlatL2(self.dimension)
                self.metadata_store = []
                self.id_counter = 0

    def _save_index(self):
        """Save FAISS index and metadata to disk"""
        try:
            index_path = self.db_path / "faiss.index"
            metadata_path = self.db_path / "metadata.pkl"

            # Save FAISS index
            faiss.write_index(self.index, str(index_path))

            # Save metadata
            with open(metadata_path, 'wb') as f:
                pickle.dump({
                    'metadata': self.metadata_store,
                    'id_counter': self.id_counter
                }, f)
        except Exception as e:
            print(f"⚠️ Error saving index: {e}")

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding using Google's text-embedding-004 model.

        Args:
            text: Text to embed

        Returns:
            Embedding vector or None if generation fails
        """
        try:
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=text,
                task_type="retrieval_document"
            )
            return result['embedding']
        except Exception as e:
            print(f"⚠️ Failed to generate embedding: {e}")
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
        with self._db_lock:
            try:
                # Generate embedding
                embedding = self.generate_embedding(content)
                if not embedding:
                    raise ValueError("Failed to generate embedding")

                # Generate ID if not provided
                if not memory_id:
                    memory_id = f"mem_{self.id_counter}"
                    self.id_counter += 1

                # Prepare metadata
                if metadata is None:
                    metadata = {}

                # Add temporal metadata
                metadata["user_id"] = self.user_id
                metadata["created_at"] = datetime.now().isoformat()
                metadata["content_preview"] = content[:200]

                # Add to FAISS index
                embedding_array = np.array([embedding], dtype='float32')
                self.index.add(embedding_array)

                # Store metadata
                self.metadata_store.append({
                    'id': memory_id,
                    'content': content,
                    'metadata': metadata,
                    'created_at': metadata["created_at"]
                })

                # Save to disk
                self._save_index()

                return memory_id

            except Exception as e:
                print(f"⚠️ Error storing memory: {e}")
                raise

    def _calculate_temporal_score(self, created_at: str, base_similarity: float) -> float:
        """
        Calculate temporal decay score for memory retrieval.

        Args:
            created_at: ISO format timestamp when memory was created
            base_similarity: Base similarity score (0.0 to 1.0)

        Returns:
            Final score with temporal decay applied
        """
        try:
            memory_time = datetime.fromisoformat(created_at)
            now = datetime.now()
            age_days = (now - memory_time).days

            # Apply exponential temporal decay
            if age_days <= self.temporal_decay_days:
                # Linear decay from 1.0 to 0.7 over decay period
                temporal_weight = 1.0 - (0.3 * age_days / self.temporal_decay_days)
            else:
                # Exponential decay after decay period
                excess_days = age_days - self.temporal_decay_days
                temporal_weight = 0.7 * np.exp(-excess_days / (self.temporal_decay_days * 2))

            # Combine base similarity (70%) and temporal weight (30%)
            final_score = (0.7 * base_similarity) + (0.3 * temporal_weight)
            return final_score

        except Exception as e:
            print(f"⚠️ Error calculating temporal score: {e}")
            return base_similarity

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
        with self._db_lock:
            try:
                if len(self.metadata_store) == 0:
                    return []

                # Generate query embedding
                query_embedding = self.generate_embedding(query)
                if not query_embedding:
                    print("⚠️ Failed to generate query embedding")
                    return []

                # Search FAISS (get more results for temporal re-ranking)
                search_k = min(top_k * 3, len(self.metadata_store))
                query_array = np.array([query_embedding], dtype='float32')
                distances, indices = self.index.search(query_array, search_k)

                # Process results
                processed_results = []
                for i, idx in enumerate(indices[0]):
                    if idx == -1:  # FAISS returns -1 for empty slots
                        continue

                    memory_data = self.metadata_store[idx]

                    # Apply user_id filter if specified
                    if filter_metadata and 'user_id' in filter_metadata:
                        if memory_data['metadata'].get('user_id') != filter_metadata['user_id']:
                            continue

                    # Convert L2 distance to similarity
                    distance = distances[0][i]
                    base_similarity = 1.0 / (1.0 + distance)

                    # Apply temporal decay
                    created_at = memory_data.get('created_at', datetime.now().isoformat())
                    final_score = self._calculate_temporal_score(created_at, base_similarity)

                    processed_results.append({
                        'id': memory_data['id'],
                        'content': memory_data['content'],
                        'metadata': memory_data['metadata'],
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
        with self._db_lock:
            try:
                # Sort by created_at and return most recent
                sorted_memories = sorted(
                    self.metadata_store,
                    key=lambda x: x['created_at'],
                    reverse=True
                )
                return sorted_memories[:limit]
            except Exception as e:
                print(f"⚠️ Error getting recent memories: {e}")
                return []

    def delete_memory(self, memory_id: str) -> bool:
        """
        Delete a memory by ID.

        Note: FAISS doesn't support deletion, so we rebuild the index without this memory.

        Args:
            memory_id: ID of memory to delete

        Returns:
            True if deleted successfully
        """
        with self._db_lock:
            try:
                # Find and remove from metadata
                idx_to_remove = None
                for i, mem in enumerate(self.metadata_store):
                    if mem['id'] == memory_id:
                        idx_to_remove = i
                        break

                if idx_to_remove is None:
                    return False

                # Remove from metadata
                self.metadata_store.pop(idx_to_remove)

                # Rebuild FAISS index (FAISS doesn't support deletion)
                self.index = faiss.IndexFlatL2(self.dimension)
                for mem in self.metadata_store:
                    embedding = self.generate_embedding(mem['content'])
                    if embedding:
                        embedding_array = np.array([embedding], dtype='float32')
                        self.index.add(embedding_array)

                # Save updated index
                self._save_index()
                return True

            except Exception as e:
                print(f"⚠️ Error deleting memory: {e}")
                return False

    def clear_all_memories(self) -> bool:
        """Clear all memories for this user."""
        with self._db_lock:
            try:
                self.index = faiss.IndexFlatL2(self.dimension)
                self.metadata_store = []
                self.id_counter = 0
                self._save_index()
                print("✓ All memories cleared")
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
        with self._db_lock:
            try:
                return {
                    'total_memories': len(self.metadata_store),
                    'user_id': self.user_id,
                    'storage_path': str(self.db_path.absolute()),
                    'temporal_decay_days': self.temporal_decay_days,
                    'index_size': self.index.ntotal
                }
            except Exception as e:
                print(f"⚠️ Error getting stats: {e}")
                return {}


if __name__ == "__main__":
    # Test the FAISS memory system
    print("Testing FAISS Memory System with Temporal Awareness\n")

    # Initialize
    # Try to load API key from environment
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except ImportError:
        pass
        
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set. Exiting.")
        exit(1)
        exit(1)

    memory = FAISSMemorySystem(
        api_key=api_key,
        user_id="test_user",
        db_path="test_faiss_memory"
    )

    # Test adding memories
    print("\n1. Adding test memories...")
    mem1 = memory.add_memory(
        content="Working on Python backend code for Ghost Widget application",
        metadata={"type": "coding", "project": "ghost-widget"}
    )
    print(f"   Added memory: {mem1}")

    mem2 = memory.add_memory(
        content="Debugging ChromaDB issues with Rust bindings on Windows",
        metadata={"type": "debugging", "issue": "chromadb-crash"}
    )
    print(f"   Added memory: {mem2}")

    # Test searching
    print("\n2. Testing search...")
    results = memory.search_memories("Python coding", top_k=5)
    print(f"   Found {len(results)} results")
    for r in results:
        print(f"   - {r['content'][:50]}... (score: {r['temporal_score']:.3f})")

    # Test stats
    print("\n3. Statistics:")
    stats = memory.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    print("\n✓ FAISS Memory System test complete!")
