#!/usr/bin/env python3
"""NEXUS -> IBM watsonx Data Bridge

Exports E:/ultron-memory (NEXUS CORE) into formats IBM watsonx
Data Intelligence can ingest:
- CSV for metadata enrichment
- JSONL for catalog assets
- Parquet for analytics (optional)

Usage:
    python nexus_to_ibm_bridge.py --format jsonl --output E:/ultron-memory/exports/
    python nexus_to_ibm_bridge.py --format csv --output E:/ultron-memory/exports/

The bridge reads:
- data/nexus.db (SQLite notes table)
- docs/ (markdown files with YAML frontmatter)
- CATALOG.md (structured catalog entries)
- ingest/ (specialized data sources like alchemy_graph)
"""

import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

NEXUS_ROOT = Path("E:/ultron-memory/nexus-core")
DB_PATH = NEXUS_ROOT / "data" / "nexus.db"
DOCS_PATH = NEXUS_ROOT / "docs"
NOTES_PATH = NEXUS_ROOT / "notes"
INGEST_PATH = NEXUS_ROOT / "ingest"
CATALOG_PATH = NEXUS_ROOT / "CATALOG.md"


def read_nexus_notes():
    """Read canonical notes from NEXUS SQLite."""
    if not DB_PATH.exists():
        print(f"NEXUS DB not found at {DB_PATH}", file=sys.stderr)
        return []

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT title, body, tags, source, created_at FROM notes")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error reading NEXUS DB: {e}", file=sys.stderr)
        return []


def read_docs_frontmatter():
    """Read markdown docs and extract YAML frontmatter."""
    docs = []
    if not DOCS_PATH.exists():
        return docs

    for md_file in [*DOCS_PATH.rglob("*.md"), *NOTES_PATH.rglob("*.md")]:
        if "_archive" in str(md_file):
            continue
        try:
            content = md_file.read_text(encoding="utf-8")
            # Simple frontmatter extraction
            if content.startswith("---"):
                _, frontmatter, body = content.split("---", 2)
                # Parse simple key: value pairs
                meta = {}
                for line in frontmatter.strip().split("\n"):
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()
                docs.append({
                    "source": str(md_file.relative_to(NEXUS_ROOT)),
                    "title": meta.get("title", md_file.stem),
                    "tags": meta.get("tags", ""),
                    "origin": meta.get("origin", "nexus"),
                    "body": body.strip()[:2000],  # Truncate for export
                    **meta
                })
        except Exception as e:
            print(f"Error reading {md_file}: {e}", file=sys.stderr)

    return docs


def read_ingest_sources():
    """Read specialized ingest sources."""
    sources = []
    if not INGEST_PATH.exists():
        return sources

    # Alchemy graph
    alchemy_dir = INGEST_PATH / "alchemy_graph"
    if alchemy_dir.exists():
        for f in alchemy_dir.rglob("*.json"):
            try:
                data = json.loads(f.read_text())
                sources.append({
                    "source_type": "alchemy_graph",
                    "source_file": str(f.relative_to(NEXUS_ROOT)),
                    "data": json.dumps(data, ensure_ascii=False)[:5000]
                })
            except Exception:
                pass

    return sources


def export_csv(notes, docs, output_dir):
    """Export to CSV for IBM watsonx metadata enrichment."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Notes CSV
    notes_csv = output_dir / "nexus_notes.csv"
    with open(notes_csv, "w", newline="", encoding="utf-8") as f:
        if notes:
            writer = csv.DictWriter(f, fieldnotes=list(notes[0].keys()))
            writer.writeheader()
            writer.writerows(notes)
    print(f"Exported {len(notes)} notes to {notes_csv}")

    # Docs CSV
    docs_csv = output_dir / "nexus_docs.csv"
    if docs:
        with open(docs_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(docs[0].keys()))
            writer.writeheader()
            writer.writerows(docs)
        print(f"Exported {len(docs)} docs to {docs_csv}")


def export_jsonl(notes, docs, ingest, output_dir):
    """Export to JSONL for IBM watsonx catalog ingestion."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Combined JSONL
    jsonl_path = output_dir / "nexus_catalog.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        # Notes
        for note in notes:
            # Parse tags from JSON
            try:
                tags = json.loads(note.get("tags", "[]"))
            except:
                tags = note.get("tags", "")
            record = {
                "record_type": "note",
                "title": note.get("title", ""),
                "content": note.get("body", "")[:5000],
                "tags": tags,
                "source": note.get("source", "nexus"),
                "timestamp": note.get("created_at", datetime.now().isoformat())
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        # Docs
        for doc in docs:
            record = {
                "record_type": "document",
                **doc
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        # Ingest sources
        for source in ingest:
            record = {
                "record_type": "ingested_data",
                **source
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Exported combined catalog to {jsonl_path}")
    total = len(notes) + len(docs) + len(ingest)
    print(f"Total records: {total}")


def main():
    parser = argparse.ArgumentParser(description="NEXUS → IBM watsonx bridge")
    parser.add_argument("--format", choices=["csv", "jsonl", "both"], default="both")
    parser.add_argument("--output", default="E:/ultron-memory/exports")
    args = parser.parse_args()

    print("Reading NEXUS CORE data...")
    notes = read_nexus_notes()
    docs = read_docs_frontmatter()
    ingest = read_ingest_sources()

    print(f"Found: {len(notes)} notes, {len(docs)} docs, {len(ingest)} ingest sources")

    if args.format in ("csv", "both"):
        export_csv(notes, docs, args.output)

    if args.format in ("jsonl", "both"):
        export_jsonl(notes, docs, ingest, args.output)

    print(f"\nExport complete. Files in: {args.output}")
    print("\nNext steps:")
    print("1. Upload CSV/JSONL to IBM watsonx Data Intelligence")
    print("2. Use MCP tool: import_glossary_from_csv")
    print("3. Use MCP tool: create_or_update_metadata_enrichment_asset")


if __name__ == "__main__":
    main()
