"""
Database Testing and Inspection Tool
Allows querying, viewing, and managing memories in both SQLite and ChromaDB storage systems
"""

import sys
import os
from pathlib import Path
import json
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional

# Fix Unicode encoding issues on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from local_memory import LocalMemorySystem
    LOCAL_MEMORY_AVAILABLE = True
except ImportError:
    LOCAL_MEMORY_AVAILABLE = False
    print("Warning: LocalMemorySystem not available")


class DatabaseInspector:
    """Inspect and query both SQLite and ChromaDB storage systems"""

    def __init__(self,
                 sqlite_db_path: str = "companion_memory.db",
                 chromadb_path: str = "local_memory_db",
                 user_id: str = "ekalabya2010_at_gmail_com",
                 api_key: Optional[str] = None):
        """
        Initialize database inspector

        Args:
            sqlite_db_path: Path to SQLite database
            chromadb_path: Path to ChromaDB directory
            user_id: User ID for memory isolation
            api_key: Google API key (required for ChromaDB operations)
        """
        self.sqlite_db_path = sqlite_db_path
        self.chromadb_path = chromadb_path
        self.user_id = user_id
        self.api_key = api_key

        # Initialize ChromaDB if available and API key provided
        self.local_memory = None
        if LOCAL_MEMORY_AVAILABLE and api_key:
            try:
                # Check if ChromaDB directory exists
                if Path(chromadb_path).exists():
                    self.local_memory = LocalMemorySystem(
                        api_key=api_key,
                        user_id=user_id,
                        db_path=chromadb_path
                    )
                    print(f"✓ Connected to ChromaDB at {chromadb_path}")
                else:
                    print(f"⚠️ ChromaDB directory not found at {chromadb_path}")
            except Exception as e:
                print(f"⚠️ Failed to connect to ChromaDB: {e}")

    def check_databases_exist(self) -> Dict[str, bool]:
        """Check which databases exist"""
        status = {
            'sqlite': Path(self.sqlite_db_path).exists(),
            'chromadb': Path(self.chromadb_path).exists(),
            'chromadb_sqlite': Path(self.chromadb_path) / "chroma.sqlite3"
        }

        # Check for the actual chroma.sqlite3 file
        if status['chromadb']:
            chroma_files = list(Path(self.chromadb_path).glob("*.sqlite*"))
            status['chromadb_files'] = [str(f) for f in chroma_files]
        else:
            status['chromadb_files'] = []

        return status

    def get_sqlite_stats(self) -> Dict[str, Any]:
        """Get statistics from SQLite database"""
        if not Path(self.sqlite_db_path).exists():
            return {"error": "SQLite database not found", "path": self.sqlite_db_path}

        try:
            conn = sqlite3.connect(self.sqlite_db_path)
            cursor = conn.cursor()

            # Get table info
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]

            stats = {
                "path": self.sqlite_db_path,
                "tables": tables,
                "table_counts": {}
            }

            # Get row counts for each table
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                stats["table_counts"][table] = count

            # Get column info for context_snapshots
            if "context_snapshots" in tables:
                cursor.execute("PRAGMA table_info(context_snapshots)")
                columns = [row[1] for row in cursor.fetchall()]
                stats["context_snapshots_columns"] = columns

            conn.close()
            return stats

        except Exception as e:
            return {"error": str(e), "path": self.sqlite_db_path}

    def get_chromadb_stats(self) -> Dict[str, Any]:
        """Get statistics from ChromaDB"""
        if not self.local_memory:
            return {"error": "ChromaDB not initialized", "path": self.chromadb_path}

        try:
            stats = self.local_memory.get_stats()
            return stats
        except Exception as e:
            return {"error": str(e), "path": self.chromadb_path}

    def view_all_sqlite_memories(self, limit: int = 100) -> List[Dict[str, Any]]:
        """View all memories from SQLite database"""
        if not Path(self.sqlite_db_path).exists():
            return []

        try:
            conn = sqlite3.connect(self.sqlite_db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, timestamp, description, active_window, active_files,
                       open_applications, tags, created_at, screen_text
                FROM context_snapshots
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))

            columns = [desc[0] for desc in cursor.description]
            memories = []

            for row in cursor.fetchall():
                memory = dict(zip(columns, row))
                memories.append(memory)

            conn.close()
            return memories

        except Exception as e:
            print(f"Error reading SQLite memories: {e}")
            return []

    def view_all_chromadb_memories(self, limit: int = 100) -> List[Dict[str, Any]]:
        """View all memories from ChromaDB"""
        if not self.local_memory:
            return []

        try:
            memories = self.local_memory.get_recent_memories(limit=limit)
            return memories
        except Exception as e:
            print(f"Error reading ChromaDB memories: {e}")
            return []

    def search_sqlite_memories(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search SQLite database using simple text matching"""
        if not Path(self.sqlite_db_path).exists():
            return []

        try:
            conn = sqlite3.connect(self.sqlite_db_path)
            cursor = conn.cursor()

            search_pattern = f"%{query}%"
            cursor.execute("""
                SELECT id, timestamp, description, active_window, active_files,
                       open_applications, tags, created_at, screen_text
                FROM context_snapshots
                WHERE description LIKE ? OR screen_text LIKE ? OR tags LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (search_pattern, search_pattern, search_pattern, limit))

            columns = [desc[0] for desc in cursor.description]
            results = []

            for row in cursor.fetchall():
                memory = dict(zip(columns, row))
                results.append(memory)

            conn.close()
            return results

        except Exception as e:
            print(f"Error searching SQLite: {e}")
            return []

    def search_chromadb_memories(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search ChromaDB using semantic search"""
        if not self.local_memory:
            return []

        try:
            results = self.local_memory.search_memories(query=query, top_k=limit)
            return results
        except Exception as e:
            print(f"Error searching ChromaDB: {e}")
            return []

    def clear_sqlite_database(self) -> bool:
        """Clear all data from SQLite database"""
        if not Path(self.sqlite_db_path).exists():
            print(f"SQLite database not found at {self.sqlite_db_path}")
            return False

        try:
            conn = sqlite3.connect(self.sqlite_db_path)
            cursor = conn.cursor()

            cursor.execute("DELETE FROM context_snapshots")
            deleted_count = cursor.rowcount

            conn.commit()
            conn.close()

            print(f"✓ Cleared {deleted_count} records from SQLite database")
            return True

        except Exception as e:
            print(f"Error clearing SQLite database: {e}")
            return False

    def clear_chromadb_database(self) -> bool:
        """Clear all data from ChromaDB"""
        if not self.local_memory:
            print("ChromaDB not initialized")
            return False

        try:
            result = self.local_memory.clear_all_memories()
            if result:
                print(f"✓ Cleared all memories from ChromaDB")
            return result
        except Exception as e:
            print(f"Error clearing ChromaDB: {e}")
            return False

    def add_test_memory_to_chromadb(self, content: str, summary: str,
                                     importance: str = "medium",
                                     tags: Optional[List[str]] = None) -> bool:
        """Add a test memory to ChromaDB"""
        if not self.local_memory:
            print("❌ ChromaDB not initialized")
            return False

        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            tags_str = ", ".join(tags) if tags else "general"

            formatted_content = f"""[Test Memory - {importance.upper()} priority]
Timestamp: {timestamp}
Summary: {summary}
Tags: {tags_str}

{content}
"""

            memory_metadata = {
                "summary": summary,
                "importance": importance,
                "tags": json.dumps(tags) if tags else "[]",
                "timestamp": timestamp,
                "type": "test_memory"
            }

            memory_id = self.local_memory.add_memory(
                content=formatted_content,
                metadata=memory_metadata
            )

            print(f"✓ Test memory added to ChromaDB: {memory_id}")
            print(f"  Summary: {summary}")
            print(f"  Importance: {importance}")
            print(f"  Tags: {tags_str}")
            return True

        except Exception as e:
            print(f"❌ Error adding test memory to ChromaDB: {e}")
            import traceback
            traceback.print_exc()
            return False

    def add_test_memory_to_sqlite(self, content: str, summary: str,
                                   importance: str = "medium",
                                   tags: Optional[List[str]] = None) -> bool:
        """Add a test memory to SQLite database"""
        if not Path(self.sqlite_db_path).exists():
            print(f"❌ SQLite database not found at {self.sqlite_db_path}")
            print("   Creating database...")
            # Create the database
            conn = sqlite3.connect(self.sqlite_db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS context_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    screenshot_path TEXT,
                    description TEXT NOT NULL,
                    active_window TEXT,
                    active_files TEXT,
                    open_applications TEXT,
                    tags TEXT,
                    embedding BLOB,
                    created_at TEXT NOT NULL,
                    screen_text TEXT
                )
            ''')
            conn.commit()
            conn.close()

        try:
            conn = sqlite3.connect(self.sqlite_db_path)
            cursor = conn.cursor()

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            tags_str = json.dumps(tags) if tags else "[]"

            cursor.execute('''
                INSERT INTO context_snapshots
                (timestamp, screenshot_path, description, active_files, open_applications,
                 embedding, created_at, screen_text, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                timestamp,
                None,
                f"[Test Memory - {importance}] {summary}",
                "[]",
                "[]",
                None,  # No embedding for test memories
                timestamp,
                content,
                tags_str
            ))

            conn.commit()
            memory_id = cursor.lastrowid
            conn.close()

            print(f"✓ Test memory added to SQLite: ID {memory_id}")
            print(f"  Summary: {summary}")
            print(f"  Importance: {importance}")
            print(f"  Tags: {tags_str if tags else 'None'}")
            return True

        except Exception as e:
            print(f"❌ Error adding test memory to SQLite: {e}")
            import traceback
            traceback.print_exc()
            return False

    def add_test_memory_to_both(self, content: str, summary: str,
                                 importance: str = "medium",
                                 tags: Optional[List[str]] = None) -> Dict[str, bool]:
        """Add a test memory to both databases"""
        results = {
            "chromadb": False,
            "sqlite": False
        }

        print(f"\n📝 Adding test memory to both databases...")
        print(f"Summary: {summary}")
        print(f"Content: {content[:100]}...")

        # Add to ChromaDB
        if self.local_memory:
            results["chromadb"] = self.add_test_memory_to_chromadb(
                content, summary, importance, tags
            )
        else:
            print("⚠️ ChromaDB not available, skipping")

        # Add to SQLite
        results["sqlite"] = self.add_test_memory_to_sqlite(
            content, summary, importance, tags
        )

        # Summary
        print(f"\n✅ Results:")
        print(f"   ChromaDB: {'✓ Success' if results['chromadb'] else '✗ Failed or Skipped'}")
        print(f"   SQLite: {'✓ Success' if results['sqlite'] else '✗ Failed'}")

        return results

    def print_database_status(self):
        """Print comprehensive database status"""
        print("\n" + "="*70)
        print("DATABASE STATUS REPORT")
        print("="*70)

        # Check existence
        print("\n📁 Database Files:")
        status = self.check_databases_exist()
        print(f"   SQLite DB ({self.sqlite_db_path}): {'✓ EXISTS' if status['sqlite'] else '✗ NOT FOUND'}")
        print(f"   ChromaDB Dir ({self.chromadb_path}): {'✓ EXISTS' if status['chromadb'] else '✗ NOT FOUND'}")

        if status.get('chromadb_files'):
            print(f"   ChromaDB Files:")
            for file in status['chromadb_files']:
                print(f"      - {file}")

        # SQLite stats
        print("\n📊 SQLite Database:")
        sqlite_stats = self.get_sqlite_stats()
        if "error" in sqlite_stats:
            print(f"   ✗ Error: {sqlite_stats['error']}")
        else:
            print(f"   Tables: {', '.join(sqlite_stats.get('tables', []))}")
            for table, count in sqlite_stats.get('table_counts', {}).items():
                print(f"   {table}: {count} records")
            if "context_snapshots_columns" in sqlite_stats:
                print(f"   Columns: {len(sqlite_stats['context_snapshots_columns'])}")

        # ChromaDB stats
        print("\n📊 ChromaDB Database:")
        chromadb_stats = self.get_chromadb_stats()
        if "error" in chromadb_stats:
            print(f"   ✗ Error: {chromadb_stats['error']}")
        else:
            print(f"   Total memories: {chromadb_stats.get('total_memories', 0)}")
            print(f"   User ID: {chromadb_stats.get('user_id', 'N/A')}")
            print(f"   Storage path: {chromadb_stats.get('storage_path', 'N/A')}")
            print(f"   Temporal decay: {chromadb_stats.get('temporal_decay_days', 'N/A')} days")

        print("\n" + "="*70)


def main():
    """Interactive CLI for database testing"""
    import argparse

    parser = argparse.ArgumentParser(description="Database Testing and Inspection Tool")
    parser.add_argument("--sqlite-db", default="companion_memory.db", help="SQLite database path")
    parser.add_argument("--chromadb", default="local_memory_db", help="ChromaDB directory path")
    parser.add_argument("--user-id", default="ekalabya2010_at_gmail_com", help="User ID")
    parser.add_argument("--api-key", help="Google API key (required for ChromaDB operations)")
    parser.add_argument("--action", choices=[
        "status", "view-sqlite", "view-chromadb", "search-sqlite",
        "search-chromadb", "clear-sqlite", "clear-chromadb", "add-test-memory", "interactive"
    ], default="interactive", help="Action to perform")
    parser.add_argument("--query", help="Search query")
    parser.add_argument("--limit", type=int, default=10, help="Limit for results")
    parser.add_argument("--content", help="Memory content (for add-test-memory)")
    parser.add_argument("--summary", help="Memory summary (for add-test-memory)")
    parser.add_argument("--importance", default="medium", choices=["low", "medium", "high"],
                        help="Memory importance (for add-test-memory)")
    parser.add_argument("--tags", help="Comma-separated tags (for add-test-memory)")

    args = parser.parse_args()

    # Get API key from environment if not provided
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if not api_key:
        print("[WARNING] No API key found in environment. Some features may fail.")

    inspector = DatabaseInspector(
        sqlite_db_path=args.sqlite_db,
        chromadb_path=args.chromadb,
        user_id=args.user_id,
        api_key=api_key
    )

    if args.action == "status":
        inspector.print_database_status()

    elif args.action == "view-sqlite":
        memories = inspector.view_all_sqlite_memories(limit=args.limit)
        print(f"\n📚 SQLite Memories (showing {len(memories)}):")
        for i, mem in enumerate(memories, 1):
            print(f"\n{i}. ID: {mem.get('id')}")
            print(f"   Time: {mem.get('timestamp')}")
            print(f"   Description: {mem.get('description', '')[:200]}")
            print(f"   Tags: {mem.get('tags', 'None')}")

    elif args.action == "view-chromadb":
        memories = inspector.view_all_chromadb_memories(limit=args.limit)
        print(f"\n📚 ChromaDB Memories (showing {len(memories)}):")
        for i, mem in enumerate(memories, 1):
            print(f"\n{i}. ID: {mem.get('id')}")
            print(f"   Created: {mem.get('created_at')}")
            print(f"   Content: {mem.get('content', '')[:200]}")
            metadata = mem.get('metadata', {})
            print(f"   Summary: {metadata.get('summary', 'N/A')}")
            print(f"   Importance: {metadata.get('importance', 'N/A')}")

    elif args.action == "search-sqlite":
        if not args.query:
            print("Error: --query is required for search")
            return
        results = inspector.search_sqlite_memories(args.query, limit=args.limit)
        print(f"\n🔍 SQLite Search Results for '{args.query}' ({len(results)} found):")
        for i, mem in enumerate(results, 1):
            print(f"\n{i}. {mem.get('description', '')[:200]}")

    elif args.action == "search-chromadb":
        if not args.query:
            print("Error: --query is required for search")
            return
        results = inspector.search_chromadb_memories(args.query, limit=args.limit)
        print(f"\n🔍 ChromaDB Search Results for '{args.query}' ({len(results)} found):")
        for i, mem in enumerate(results, 1):
            print(f"\n{i}. Score: {mem.get('temporal_score', 0):.3f}")
            print(f"   {mem.get('content', '')[:200]}")

    elif args.action == "clear-sqlite":
        confirm = input("⚠️ This will delete all SQLite data. Type 'yes' to confirm: ")
        if confirm.lower() == 'yes':
            inspector.clear_sqlite_database()

    elif args.action == "clear-chromadb":
        confirm = input("⚠️ This will delete all ChromaDB data. Type 'yes' to confirm: ")
        if confirm.lower() == 'yes':
            inspector.clear_chromadb_database()

    elif args.action == "add-test-memory":
        if not args.content or not args.summary:
            print("❌ Error: --content and --summary are required for add-test-memory")
            return

        tags = args.tags.split(",") if args.tags else None
        inspector.add_test_memory_to_both(
            content=args.content,
            summary=args.summary,
            importance=args.importance,
            tags=tags
        )

    elif args.action == "interactive":
        # Interactive mode
        inspector.print_database_status()

        print("\n" + "="*70)
        print("INTERACTIVE MODE")
        print("="*70)
        print("\nAvailable commands:")
        print("  1. View SQLite memories")
        print("  2. View ChromaDB memories")
        print("  3. Search SQLite")
        print("  4. Search ChromaDB")
        print("  5. Compare both databases")
        print("  6. Clear SQLite database")
        print("  7. Clear ChromaDB database")
        print("  8. Add test memory")
        print("  9. Refresh status")
        print("  q. Quit")

        while True:
            choice = input("\nEnter command (1-9 or q): ").strip()

            if choice == 'q':
                print("Goodbye!")
                break

            elif choice == '1':
                limit = input("Limit (default 10): ").strip() or "10"
                memories = inspector.view_all_sqlite_memories(limit=int(limit))
                print(f"\n📚 SQLite Memories ({len(memories)} found):")
                for i, mem in enumerate(memories, 1):
                    print(f"\n{i}. [{mem.get('timestamp')}] {mem.get('description', '')[:150]}")

            elif choice == '2':
                limit = input("Limit (default 10): ").strip() or "10"
                memories = inspector.view_all_chromadb_memories(limit=int(limit))
                print(f"\n📚 ChromaDB Memories ({len(memories)} found):")
                for i, mem in enumerate(memories, 1):
                    metadata = mem.get('metadata', {})
                    print(f"\n{i}. [{mem.get('created_at')}]")
                    print(f"   Summary: {metadata.get('summary', 'N/A')}")
                    print(f"   Content: {mem.get('content', '')[:150]}")

            elif choice == '3':
                query = input("Search query: ").strip()
                results = inspector.search_sqlite_memories(query)
                print(f"\n🔍 Found {len(results)} results:")
                for i, mem in enumerate(results, 1):
                    print(f"{i}. {mem.get('description', '')[:100]}")

            elif choice == '4':
                if not api_key:
                    print("❌ API key required for ChromaDB search")
                    continue
                query = input("Search query: ").strip()
                results = inspector.search_chromadb_memories(query)
                print(f"\n🔍 Found {len(results)} results:")
                for i, mem in enumerate(results, 1):
                    print(f"{i}. [Score: {mem.get('temporal_score', 0):.3f}] {mem.get('content', '')[:100]}")

            elif choice == '5':
                print("\n🔄 Comparing databases...")
                sqlite_count = len(inspector.view_all_sqlite_memories(limit=1000))
                chromadb_count = len(inspector.view_all_chromadb_memories(limit=1000))
                print(f"   SQLite: {sqlite_count} memories")
                print(f"   ChromaDB: {chromadb_count} memories")
                print(f"   Difference: {abs(sqlite_count - chromadb_count)}")

            elif choice == '6':
                confirm = input("⚠️ Clear SQLite? (yes/no): ")
                if confirm.lower() == 'yes':
                    inspector.clear_sqlite_database()

            elif choice == '7':
                confirm = input("⚠️ Clear ChromaDB? (yes/no): ")
                if confirm.lower() == 'yes':
                    inspector.clear_chromadb_database()

            elif choice == '8':
                print("\n📝 Add Test Memory")
                content = input("Content: ").strip()
                summary = input("Summary: ").strip()
                importance = input("Importance (low/medium/high, default: medium): ").strip() or "medium"
                tags_input = input("Tags (comma-separated, optional): ").strip()
                tags = [t.strip() for t in tags_input.split(",")] if tags_input else None

                if content and summary:
                    inspector.add_test_memory_to_both(content, summary, importance, tags)
                else:
                    print("❌ Content and summary are required")

            elif choice == '9':
                inspector.print_database_status()

            else:
                print("Invalid command")


if __name__ == "__main__":
    main()
