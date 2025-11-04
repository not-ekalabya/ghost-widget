#!/usr/bin/env python3
"""
Emergency ChromaDB Reset Script
Use this if ChromaDB is crashing or corrupted.
"""

import shutil
from pathlib import Path
from datetime import datetime

# Paths
local_memory_db = Path("local_memory_db")
backup_dir = Path("local_memory_db_backups")

def reset_chromadb():
    """Reset ChromaDB by backing up and deleting the database."""

    if not local_memory_db.exists():
        print("✓ No ChromaDB found - nothing to reset")
        return

    # Create backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"backup_{timestamp}"
    backup_dir.mkdir(exist_ok=True)

    print(f"📦 Backing up ChromaDB to: {backup_path}")
    shutil.copytree(local_memory_db, backup_path)
    print(f"✓ Backup complete")

    # Delete current database
    print(f"🗑️  Deleting corrupted ChromaDB...")
    shutil.rmtree(local_memory_db)
    print(f"✓ ChromaDB deleted")

    print(f"\n✅ Reset complete!")
    print(f"   - Backup saved to: {backup_path}")
    print(f"   - Database will be recreated on next app start")
    print(f"\n⚠️  Note: All stored memories are backed up but will not be in the new database")

if __name__ == "__main__":
    print("="*60)
    print("ChromaDB Reset Tool")
    print("="*60)
    print("\nThis will:")
    print("  1. Backup current ChromaDB to local_memory_db_backups/")
    print("  2. Delete the current ChromaDB database")
    print("  3. Allow the app to create a fresh database\n")

    response = input("Continue? (yes/no): ").strip().lower()
    if response == "yes":
        reset_chromadb()
    else:
        print("Cancelled.")
