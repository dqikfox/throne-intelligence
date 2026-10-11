#!/usr/bin/env python3
"""Rebuild NEXUS DB from cleaned deduplicated JSONL export.

Reads nexus_deduped.jsonl, recreates SQLite DB with same schema,
populates notes + import_log tables, rebuilds FTS index if possible.

Usage:
    python rebuild_nexus_db.py --input E:/ultron-memory/exports/nexus_deduped.jsonl --output E:/ultron-memory/nexus-core/data/nexus.db
"""

import argparse
import json
import sqlite3
import sys
import hashlib
from datetime import datetime
from pathlib import Path


def create_schema(conn):
    """Create NEXUS DB schema matching original structure."""
    cursor = conn.cursor()
    
    # Main notes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            tags TEXT,
            source TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            source_hash TEXT
        )
    """)
    
    # FTS5 virtual table for search
    try:
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                title, body, tags,
                content='notes',
                content_rowid='id'
            )
        """)
    except sqlite3.OperationalError:
        print("WARNING: FTS5 not available — search will be limited", file=sys.stderr)
    
    # Import log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS import_log (
            source_hash TEXT PRIMARY KEY,
            source TEXT,
            slug TEXT,
            imported_at TEXT
        )
    """)
    
    conn.commit()


def generate_slug(title: str, index: int) -> str:
    """Generate a URL-friendly slug from title."""
    import re
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'\s+', '-', slug)
    slug = slug[:80]
    if not slug:
        slug = f"note-{index}"
    return slug


def generate_source_hash(content: str) -> str:
    """Generate a hash for deduplication tracking."""
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def rebuild_db(input_path: Path, output_path: Path):
    """Main rebuild logic."""
    print(f"Reading cleaned data from {input_path}...")
    
    records = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    
    print(f"Loaded {len(records)} cleaned records")
    
    # Remove old DB if exists (backup already made)
    if output_path.exists():
        output_path.unlink()
    
    # Create new DB
    conn = sqlite3.connect(str(output_path))
    create_schema(conn)
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    
    # Insert records
    inserted = 0
    import_hashes = set()
    
    for i, record in enumerate(records):
        title = record.get("title", "untitled")[:500]
        body = record.get("content", "")[:50000]  # Limit body size
        tags = json.dumps(record.get("tags", [])) if not isinstance(record.get("tags"), str) else record["tags"]
        source = record.get("source", "deduped")[:200]
        created_at = record.get("created_at", now)
        updated_at = record.get("timestamp", now)
        
        slug = generate_slug(title, i)
        source_hash = generate_source_hash(body)
        
        # Ensure unique slug
        slug_base = slug
        suffix = 0
        while True:
            cursor.execute("SELECT 1 FROM notes WHERE slug = ?", (slug,))
            if not cursor.fetchone():
                break
            suffix += 1
            slug = f"{slug_base}-{suffix}"
        
        cursor.execute("""
            INSERT INTO notes (slug, title, body, tags, source, created_at, updated_at, source_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (slug, title, body, tags, source, created_at, updated_at, source_hash))
        
        row_id = cursor.lastrowid
        
        # Insert FTS data if available
        try:
            cursor.execute("""
                INSERT INTO notes_fts (rowid, title, body, tags)
                VALUES (?, ?, ?, ?)
            """, (row_id, title, body, tags))
        except sqlite3.OperationalError:
            pass
        
        # Track in import log
        if source_hash not in import_hashes:
            import_hashes.add(source_hash)
            cursor.execute("""
                INSERT OR IGNORE INTO import_log (source_hash, source, slug, imported_at)
                VALUES (?, ?, ?, ?)
            """, (source_hash, source, slug, now))
        
        inserted += 1
        if inserted % 500 == 0:
            print(f"  Inserted {inserted}/{len(records)}...")
    
    conn.commit()
    conn.close()
    
    print(f"\nRebuild complete: {inserted} records written to {output_path}")
    return inserted


def run_after_tests(db_path: Path):
    """Run the same metrics as before tests."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    print("\n" + "="*60)
    print("AFTER: Rebuilt NEXUS DB Metrics")
    print("="*60)
    print()
    
    # Row counts
    print("--- Row Counts ---")
    cursor.execute("SELECT COUNT(*) FROM notes")
    notes_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM import_log")
    import_count = cursor.fetchone()[0]
    print(f"  notes: {notes_count}")
    print(f"  import_log: {import_count}")
    
    # DB file size
    print()
    print("--- File Size ---")
    size = db_path.stat().st_size
    size_mb = size / (1024 * 1024)
    print(f"  Size: {size_mb:.1f}M")
    
    # Search performance (LIKE-based since FTS may not work)
    print()
    print("--- Search Performance ---")
    
    import time
    start = time.time()
    cursor.execute("SELECT count(*) FROM notes WHERE body LIKE '%ollama%'")
    result = cursor.fetchone()[0]
    duration = (time.time() - start) * 1000
    print(f"  LIKE search 'ollama': {duration:.0f}ms ({result} matches)")
    
    start = time.time()
    cursor.execute("SELECT count(*) FROM notes WHERE body LIKE '%API%'")
    result = cursor.fetchone()[0]
    duration = (time.time() - start) * 1000
    print(f"  LIKE search 'API': {duration:.0f}ms ({result} matches)")
    
    # Duplicate count
    print()
    print("--- Duplicate Analysis ---")
    cursor.execute("SELECT COUNT(*) FROM (SELECT LOWER(TRIM(title)) AS t FROM notes GROUP BY t HAVING COUNT(*) > 1)")
    dupes = cursor.fetchone()[0]
    print(f"  Duplicate title groups: {dupes}")
    
    # Content stats
    print()
    print("--- Content Stats ---")
    cursor.execute("SELECT ROUND(AVG(LENGTH(body)), 0) FROM notes")
    avg_len = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(LENGTH(body)) FROM notes")
    total_chars = cursor.fetchone()[0]
    print(f"  Avg content length: {avg_len} chars")
    print(f"  Total content: {total_chars} chars")
    
    conn.close()
    
    print()
    print("="*60)
    print("END AFTER TESTS")
    print("="*60)
    
    return {
        "notes_count": notes_count,
        "import_count": import_count,
        "size_mb": size_mb,
        "duplicates": dupes,
        "avg_length": avg_len,
        "total_chars": total_chars
    }


def main():
    parser = argparse.ArgumentParser(description="Rebuild NEXUS DB from cleaned data")
    parser.add_argument("--input", default="E:/ultron-memory/exports/nexus_deduped.jsonl")
    parser.add_argument("--output", default="E:/ultron-memory/nexus-core/data/nexus.db")
    parser.add_argument("--no-backup", action="store_true", help="Skip backup check (DANGER)")
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    
    # Check backup exists
    backup_dir = Path("E:/ultron-memory/backups")
    backups = list(backup_dir.glob("nexus_backup_*.db"))
    if not backups and not args.no_backup:
        print("ERROR: No backup found! Run backup first or use --no-backup", file=sys.stderr)
        sys.exit(1)
    elif backups:
        print(f"Backup verified: {backups[-1]}")
    
    print("="*60)
    print("REBUILDING NEXUS DB FROM CLEANED DATA")
    print("="*60)
    print()
    
    # Rebuild
    inserted = rebuild_db(input_path, output_path)
    
    # Run after tests
    after_metrics = run_after_tests(output_path)
    
    # Summary
    print("\n" + "="*60)
    print("REBUILD COMPLETE")
    print("="*60)
    print(f"Original DB backed up at: {backups[-1] if backups else 'N/A'}")
    print(f"New DB: {output_path}")
    print(f"Records inserted: {inserted}")
    print()
    print("To restore original if needed:")
    print(f"  cp {backups[-1] if backups else 'BACKUP_FILE'} {output_path}")


if __name__ == "__main__":
    main()
