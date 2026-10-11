#!/usr/bin/env python3
"""NEXUS Duplicate Merger — Clean 240 duplicate groups (678 records) from NEXUS.

Reads sanitized/organized data, detects duplicates by title similarity,
merges the most complete version, and outputs a cleaned catalog.

Usage:
    python merge_nexus_duplicates.py --input-dir E:/ultron-memory/exports/nexus_organized --output E:/ultron-memory/exports/nexus_deduped.jsonl
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def load_all_records(input_dir: Path):
    """Load all topic JSONL files."""
    records = []
    for jsonl_file in input_dir.glob("topic_*.jsonl"):
        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
    return records


def normalize_title(title: str) -> str:
    """Normalize title for duplicate detection."""
    import re
    # Lowercase, remove UUIDs, timestamps, trailing numbers
    t = title.lower().strip()
    t = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '', t)
    t = re.sub(r'\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}', '', t)
    t = re.sub(r'\s+\d+(/\d+)?\s*$', '', t)
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def find_duplicate_groups(records: list, similarity_threshold: int = 5):
    """Group records by normalized title similarity."""
    groups = defaultdict(list)
    
    for i, rec in enumerate(records):
        title = rec.get("title", "")
        norm = normalize_title(title)
        if len(norm) >= 3:  # Only group titles with meaningful length
            groups[norm].append(i)
    
    # Return groups with more than 1 member
    return {k: v for k, v in groups.items() if len(v) > 1}


def select_best_record(indices: list, records: list) -> dict:
    """Select the best (most complete) record from a duplicate group."""
    candidates = [records[i] for i in indices]
    
    def score(rec):
        s = 0
        if rec.get("content", "").strip(): s += len(rec["content"])
        if rec.get("tags") and str(rec["tags"]) not in ("", "[]", "null"): s += 100
        if rec.get("source") and rec["source"] != "unknown": s += 50
        if rec.get("_sanitized", False): s += 25  # Prefer sanitized
        if rec.get("classification", {}).get("topic_score", 0) > 0: s += 10
        return s
    
    # Sort by score descending
    candidates.sort(key=score, reverse=True)
    best = candidates[0].copy()
    
    # Merge sources from all duplicates
    all_sources = list(set(
        r.get("source", "unknown") for r in candidates if r.get("source")
    ))
    if len(all_sources) > 1:
        best["_merged_sources"] = all_sources
    
    # Track merge info
    best["_merged_from"] = len(candidates)
    best["_merge_timestamp"] = datetime.now().isoformat()
    
    return best


def merge_duplicates(records: list):
    """Main merge logic. Returns (cleaned_records, merge_report)."""
    print(f"Scanning {len(records)} records for duplicates...")
    
    dup_groups = find_duplicate_groups(records)
    print(f"Found {len(dup_groups)} duplicate groups ({sum(len(v) for v in dup_groups.values())} total records)")
    
    # Track which indices to keep vs discard
    keep_indices = set(range(len(records)))
    merged_records = []
    merge_details = []
    
    for norm_title, indices in sorted(dup_groups.items(), key=lambda x: len(x[1]), reverse=True):
        # Remove all but the best from this group
        best = select_best_record(indices, records)
        
        merge_details.append({
            "normalized_title": norm_title[:80],
            "original_titles": [records[i].get("title", "")[:60] for i in indices[:5]],
            "records_merged": len(indices),
            "kept_title": best.get("title", "")[:60],
            "sources": best.get("_merged_sources", [best.get("source", "unknown")])
        })
        
        # Mark indices for removal
        for i in indices:
            keep_indices.discard(i)
        
        merged_records.append(best)
    
    # Add non-duplicate records
    for i in keep_indices:
        merged_records.append(records[i])
    
    report = {
        "total_original": len(records),
        "duplicate_groups": len(dup_groups),
        "records_removed": sum(len(v) for v in dup_groups.values()) - len(dup_groups),
        "records_kept": len(merged_records),
        "reduction_percent": round((sum(len(v) for v in dup_groups.values()) - len(dup_groups)) / len(records) * 100, 1) if records else 0,
        "merge_details": merge_details[:50],  # Limit detail size
        "generated_at": datetime.now().isoformat()
    }
    
    return merged_records, report


def main():
    parser = argparse.ArgumentParser(description="Merge duplicate NEXUS records")
    parser.add_argument("--input-dir", default="E:/ultron-memory/exports/nexus_organized")
    parser.add_argument("--output", default="E:/ultron-memory/exports/nexus_deduped.jsonl")
    parser.add_argument("--report", default="E:/ultron-memory/exports/merge_report.json")
    args = parser.parse_args()
    
    input_dir = Path(args.input_dir)
    output_path = Path(args.output)
    report_path = Path(args.report)
    
    print("=" * 60)
    print("NEXUS DUPLICATE MERGER")
    print("=" * 60)
    print()
    
    # Load
    records = load_all_records(input_dir)
    print(f"Loaded {len(records)} records from {input_dir}")
    print()
    
    # Merge
    cleaned, report = merge_duplicates(records)
    
    # Write cleaned output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for rec in cleaned:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    
    # Write report
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    # Summary
    print("=" * 60)
    print("MERGE COMPLETE")
    print("=" * 60)
    print(f"Original records: {report['total_original']:,}")
    print(f"Duplicate groups: {report['duplicate_groups']}")
    print(f"Records removed:  {report['records_removed']:,}")
    print(f"Records kept:     {report['records_kept']:,}")
    print(f"Reduction:        {report['reduction_percent']}%")
    print()
    print(f"Files written:")
    print(f"  Cleaned catalog: {output_path}")
    print(f"  Merge report:    {report_path}")
    print()
    print("Next: Rebuild NEXUS DB from cleaned catalog with:")
    print("  python nexus_to_ibm_bridge.py --import cleaned_catalog.jsonl")


if __name__ == "__main__":
    main()
