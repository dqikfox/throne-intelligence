#!/usr/bin/env python3
"""NEXUS Data Sanitizer — Auto-redact sensitive data before IBM ingestion.

Scans exported NEXUS catalog for:
- API keys (sk_*, ghp_*, hf_*, etc.)
- Tokens, passwords, secrets
- Replaces with [REDACTED] markers
- Generates audit log of redactions

Usage:
    python sanitize_nexus_export.py --input E:/ultron-memory/exports/nexus_catalog.jsonl --output E:/ultron-memory/exports/nexus_catalog_sanitized.jsonl
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Patterns to detect and redact
SENSITIVE_PATTERNS = {
    "elevenlabs_key": (r"sk_[a-zA-Z0-9]{20,}", "[ELEVENLABS_KEY_REDACTED]"),
    "openai_key": (r"sk-proj-[a-zA-Z0-9_-]{20,}", "[OPENAI_KEY_REDACTED]"),
    "github_pat": (r"ghp_[a-zA-Z0-9]{20,}", "[GITHUB_PAT_REDACTED]"),
    "hf_token": (r"hf_[a-zA-Z0-9]{20,}", "[HF_TOKEN_REDACTED]"),
    "generic_api_key": (r"(?i)(api[_\s]?key[:\s=]+)([a-zA-Z0-9_\-\/\+]{8,})", r"\1[GENERIC_KEY_REDACTED]"),
    "generic_token": (r"(?i)(token[:\s=]+)([a-zA-Z0-9_\-\/\+]{8,})", r"\1[TOKEN_REDACTED]"),
    "bearer_token": (r"Bearer\s+[a-zA-Z0-9_\-\/\+]{10,}", "[BEARER_TOKEN_REDACTED]"),
    "jwt_token": (r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*", "[JWT_REDACTED]"),
}


def sanitize_record(record: dict) -> tuple[dict, list]:
    """Redact sensitive data from a single record. Returns (sanitized_record, redactions)."""
    content = record.get("content", "")
    redactions = []
    
    for pattern_name, (pattern, replacement) in SENSITIVE_PATTERNS.items():
        matches = re.findall(pattern, content)
        if matches:
            count = len(matches)
            content = re.sub(pattern, replacement, content)
            redactions.append({
                "pattern": pattern_name,
                "count": count,
                "preview": str(matches[0])[:30] + "..." if len(str(matches[0])) > 30 else str(matches[0])
            })
    
    if redactions:
        record["content"] = content
        record["_sanitized"] = True
        record["_redactions"] = redactions
    
    return record, redactions


def main():
    parser = argparse.ArgumentParser(description="Sanitize NEXUS export before IBM ingestion")
    parser.add_argument("--input", default="E:/ultron-memory/exports/nexus_catalog.jsonl")
    parser.add_argument("--output", default="E:/ultron-memory/exports/nexus_catalog_sanitized.jsonl")
    parser.add_argument("--audit-log", default="E:/ultron-memory/exports/sanitization_audit.json")
    args = parser.parse_args()
    
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Reading {input_path}...")
    
    records = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    
    print(f"Loaded {len(records)} records")
    print("Scanning for sensitive data...")
    
    sanitized_count = 0
    total_redactions = 0
    all_audits = []
    
    for i, record in enumerate(records):
        sanitized, redactions = sanitize_record(record)
        if redactions:
            sanitized_count += 1
            total_redactions += sum(r["count"] for r in redactions)
            all_audits.append({
                "index": i,
                "title": record.get("title", "untitled"),
                "record_type": record.get("record_type", "unknown"),
                "redactions": redactions
            })
    
    # Write sanitized output
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    # Write audit log
    audit = {
        "generated_at": datetime.now().isoformat(),
        "source_file": str(input_path),
        "output_file": str(output_path),
        "total_records": len(records),
        "records_sanitized": sanitized_count,
        "total_redactions": total_redactions,
        "redaction_types": {},
        "details": all_audits[:100]  # Limit detail size
    }
    
    # Summarize redaction types
    for entry in all_audits:
        for r in entry["redactions"]:
            name = r["pattern"]
            if name not in audit["redaction_types"]:
                audit["redaction_types"][name] = {"records_affected": 0, "total_count": 0}
            audit["redaction_types"][name]["records_affected"] += 1
            audit["redaction_types"][name]["total_count"] += r["count"]
    
    with open(args.audit_log, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*50}")
    print(f"SANITIZATION COMPLETE")
    print(f"{'='*50}")
    print(f"Records scanned: {len(records)}")
    print(f"Records sanitized: {sanitized_count}")
    print(f"Total redactions: {total_redactions}")
    print(f"\nRedaction breakdown:")
    for name, stats in audit["redaction_types"].items():
        print(f"  {name}: {stats['records_affected']} records, {stats['total_count']} occurrences")
    print(f"\nFiles written:")
    print(f"  Sanitized: {output_path}")
    print(f"  Audit log: {args.audit_log}")


if __name__ == "__main__":
    main()
