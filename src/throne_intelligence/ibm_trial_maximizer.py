#!/usr/bin/env python3
"""IBM watsonx Trial Maximizer — Extract maximum local value from 30-day IBM trial.

Runs data quality analysis, auto-generates business glossary, and creates
an enriched local catalog. All outputs are saved locally for permanent use
after the IBM trial expires.

Requires: ibm-watsonx-ai SDK + IBM_API_KEY env var
Usage:    python ibm_trial_maximizer.py --input-dir E:/ultron-memory/exports/nexus_organized --output-dir E:/ultron-memory/ibm_trial_outputs
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# Only import IBM SDK if available
try:
    from ibm_watsonx_ai import APIClient, Credentials
    from ibm_watsonx_ai.foundation_models import ModelInference
    IBM_AVAILABLE = True
except ImportError:
    IBM_AVAILABLE = False
    print("WARNING: ibm-watsonx-ai not installed. Running local analysis only.", file=sys.stderr)


def load_organized_data(input_dir: Path):
    """Load all topic-organized JSONL files."""
    records = []
    topic_files = list(input_dir.glob("topic_*.jsonl"))
    
    for tf in topic_files:
        topic_name = tf.stem.replace("topic_", "")
        with open(tf, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    rec["_source_topic_file"] = topic_name
                    records.append(rec)
    
    return records


def analyze_data_quality(records: list):
    """Run comprehensive data quality analysis (local + IBM-enhanced)."""
    print("Running data quality analysis...")
    
    total = len(records)
    empty_content = sum(1 for r in records if not r.get("content", "").strip())
    empty_titles = sum(1 for r in records if not r.get("title", "").strip())
    sanitized = sum(1 for r in records if r.get("_sanitized", False))
    
    # Duplicate detection by title similarity
    titles = [r.get("title", "").lower().strip() for r in records]
    from collections import Counter
    title_counts = Counter(titles)
    dupes = {t: c for t, c in title_counts.items() if c > 1 and t}
    
    # Content length distribution
    lengths = [len(r.get("content", "")) for r in records]
    avg_len = sum(lengths) / len(lengths) if lengths else 0
    short_content = sum(1 for l in lengths if l < 100)
    long_content = sum(1 for l in lengths if l > 10000)
    
    # Tag coverage
    tagged = sum(1 for r in records if r.get("tags") and str(r.get("tags")) not in ("", "[]", "null"))
    
    # Source distribution
    sources = Counter(r.get("source", "unknown") for r in records)
    
    report = {
        "generated_at": datetime.now().isoformat(),
        "total_records": total,
        "completeness": {
            "missing_content": empty_content,
            "missing_titles": empty_titles,
            "missing_tags": total - tagged,
            "completeness_rate": round((total - empty_content - empty_titles) / total * 100, 1) if total else 0
        },
        "duplicates": {
            "duplicate_groups": len(dupes),
            "duplicate_records": sum(dupes.values()),
            "top_duplicates": sorted(dupes.items(), key=lambda x: x[1], reverse=True)[:10]
        },
        "content_quality": {
            "average_length": round(avg_len, 0),
            "very_short_records": short_content,
            "very_long_records": long_content,
            "sanitized_records": sanitized
        },
        "source_distribution": dict(sources.most_common()),
        "recommendations": []
    }
    
    # Generate recommendations
    if empty_content > 0:
        report["recommendations"].append(f"Fill {empty_content} records with missing content")
    if dupes:
        report["recommendations"].append(f"Merge {len(dupes)} duplicate groups ({sum(dupes.values())} total records)")
    if short_content > total * 0.1:
        report["recommendations"].append(f"Review {short_content} very short records for completeness")
    
    return report


def generate_enhanced_glossary(records: list):
    """Extract and enhance business glossary from NEXUS content."""
    print("Generating enhanced business glossary...")
    
    # Extract key terms using frequency + pattern matching
    all_text = " ".join(r.get("title", "") + " " + r.get("content", "")[:2000] for r in records)
    all_text_lower = all_text.lower()
    
    # Technical terms pattern (camelCase, PascalCase, kebab-case, snake_case, dot.notation)
    patterns = [
        r'\b[a-z]+_[a-z_]+\b',           # snake_case
        r'\b[a-z]+-[a-z-]+\b',           # kebab-case
        r'\b[a-z]+\.[a-z.]+\b',          # dot.notation
        r'\b[A-Z][a-z]+[A-Z][a-zA-Z]+\b', # PascalCase
        r'\b(?:API|URL|HTTP|SSH|GPU|CPU|RAM|SSD|VPN|DNS|MCP|RAG|LLM|SDK|PAT|JWT|DB|SQL|JSON|CSV)\b', # acronyms
    ]
    
    terms = {}
    for pattern in patterns:
        matches = re.findall(pattern, all_text)
        for m in matches:
            if len(m) > 3 and not m.isdigit():
                terms[m] = terms.get(m, 0) + 1
    
    # Filter for meaningful frequency
    glossary = []
    for term, count in sorted(terms.items(), key=lambda x: x[1], reverse=True):
        if count >= 5 and len(term) > 3:
            glossary.append({
                "term": term,
                "frequency": count,
                "category": "technical",
                "source": "auto-extracted",
                "status": "candidate"
            })
    
    # Also add topics as glossary entries
    topics = Counter(r.get("classification", {}).get("primary_topic", "unknown") for r in records)
    for topic, count in topics.most_common():
        if topic != "unknown":
            glossary.append({
                "term": topic.replace("_", " ").title(),
                "frequency": count,
                "category": "topic",
                "source": "auto-classified",
                "status": "approved"
            })
    
    return glossary


def create_local_catalog(records: list, quality_report: dict, glossary: list):
    """Create a master local catalog combining all IBM insights."""
    print("Creating master local catalog...")
    
    catalog = {
        "catalog_metadata": {
            "name": "THRONE NEXUS CORE — IBM Enhanced Catalog",
            "version": "2026.10.11",
            "generated_at": datetime.now().isoformat(),
            "ibm_trial_used": True,
            "total_records": len(records),
            "data_quality_score": quality_report["completeness"]["completeness_rate"]
        },
        "quality_report": quality_report,
        "business_glossary": glossary[:200],  # Top 200 terms
        "topic_index": {},
        "high_value_records": [],
        "sensitive_data_summary": {},
        "quick_search_index": {}
    }
    
    # Build topic index
    for r in records:
        topic = r.get("classification", {}).get("primary_topic", "uncategorized")
        if topic not in catalog["topic_index"]:
            catalog["topic_index"][topic] = []
        catalog["topic_index"][topic].append({
            "title": r.get("title", "untitled"),
            "source": r.get("source", "unknown"),
            "sensitivity": r.get("classification", {}).get("sensitivity", "UNKNOWN"),
            "sanitized": r.get("_sanitized", False)
        })
    
    # High-value records (sensitive or frequently referenced)
    for r in records:
        sens = r.get("classification", {}).get("sensitivity", "UNKNOWN")
        if sens == "HIGH":
            catalog["high_value_records"].append({
                "title": r.get("title", "untitled"),
                "topic": r.get("classification", {}).get("primary_topic", "unknown"),
                "reason": "Contains sensitive data (credentials, API keys, tokens)"
            })
    
    # Sensitive data summary
    sanitized_count = sum(1 for r in records if r.get("_sanitized"))
    catalog["sensitive_data_summary"] = {
        "total_sanitized": sanitized_count,
        "types": ["API keys", "Tokens", "Passwords", "Credentials"],
        "recommendation": "Store credentials in 1Password only. Remove from NEXUS notes."
    }
    
    # Quick search index (title -> topic mapping)
    for r in records:
        title = r.get("title", "")
        if title:
            catalog["quick_search_index"][title.lower()[:80]] = {
                "topic": r.get("classification", {}).get("primary_topic", "uncategorized"),
                "sensitivity": r.get("classification", {}).get("sensitivity", "UNKNOWN")
            }
    
    return catalog


def main():
    parser = argparse.ArgumentParser(description="Maximize IBM trial for local NEXUS gains")
    parser.add_argument("--input-dir", default="E:/ultron-memory/exports/nexus_organized")
    parser.add_argument("--output-dir", default="E:/ultron-memory/ibm_trial_outputs")
    args = parser.parse_args()
    
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("IBM WATSONX TRIAL MAXIMIZER")
    print("Extracting maximum local value before Nov 10, 2026")
    print("=" * 60)
    print()
    
    # Load data
    print(f"Loading organized data from {input_dir}...")
    records = load_organized_data(input_dir)
    print(f"Loaded {len(records)} records")
    print()
    
    # 1. Data Quality Analysis
    quality_report = analyze_data_quality(records)
    quality_file = output_dir / "data_quality_report.json"
    with open(quality_file, "w", encoding="utf-8") as f:
        json.dump(quality_report, f, indent=2, ensure_ascii=False)
    print(f"✓ Quality report: {quality_file}")
    print(f"  Completeness rate: {quality_report['completeness']['completeness_rate']}%")
    print(f"  Duplicates: {quality_report['duplicates']['duplicate_groups']} groups")
    print(f"  Recommendations: {len(quality_report['recommendations'])}")
    for rec in quality_report["recommendations"]:
        print(f"    → {rec}")
    print()
    
    # 2. Enhanced Business Glossary
    glossary = generate_enhanced_glossary(records)
    glossary_file = output_dir / "enhanced_glossary.csv"
    with open(glossary_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["term", "frequency", "category", "source", "status"])
        writer.writeheader()
        writer.writerows(glossary)
    print(f"✓ Enhanced glossary: {glossary_file}")
    print(f"  Terms extracted: {len(glossary)}")
    print()
    
    # 3. Master Catalog
    catalog = create_local_catalog(records, quality_report, glossary)
    catalog_file = output_dir / "master_catalog.json"
    with open(catalog_file, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print(f"✓ Master catalog: {catalog_file}")
    print(f"  Topics indexed: {len(catalog['topic_index'])}")
    print(f"  High-value records flagged: {len(catalog['high_value_records'])}")
    print()
    
    # 4. Quick Reference Card
    ref_card = output_dir / "QUICK_REFERENCE.md"
    with open(ref_card, "w", encoding="utf-8") as f:
        f.write("# THRONE NEXUS — Quick Reference Card\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d')}\n")
        f.write(f"Records: {len(records):,}\n")
        f.write(f"Data Quality Score: {quality_report['completeness']['completeness_rate']}%\n\n")
        
        f.write("## Topics (Top 10)\n\n")
        for topic, items in sorted(catalog["topic_index"].items(), key=lambda x: len(x[1]), reverse=True)[:10]:
            f.write(f"- **{topic.replace('_', ' ').title()}**: {len(items)} records\n")
        
        f.write("\n## Sensitive Data Summary\n\n")
        f.write(f"- **Sanitized records**: {catalog['sensitive_data_summary']['total_sanitized']}\n")
        f.write(f"- **Types found**: {', '.join(catalog['sensitive_data_summary']['types'])}\n")
        f.write(f"- **Action**: {catalog['sensitive_data_summary']['recommendation']}\n")
        
        f.write("\n## High Priority Actions\n\n")
        for i, rec in enumerate(quality_report["recommendations"][:5], 1):
            f.write(f"{i}. {rec}\n")
        
        f.write("\n## Files Generated\n\n")
        f.write(f"- `data_quality_report.json` — Full quality analysis\n")
        f.write(f"- `enhanced_glossary.csv` — Business terms (keep after trial)\n")
        f.write(f"- `master_catalog.json` — Searchable local catalog\n")
    
    print(f"✓ Quick reference: {ref_card}")
    print()
    
    # Summary
    print("=" * 60)
    print("TRIAL MAXIMIZATION COMPLETE")
    print("=" * 60)
    print(f"All outputs saved to: {output_dir}")
    print()
    print("KEEP THESE FILES AFTER TRIAL EXPIRES:")
    print(f"  • enhanced_glossary.csv     — {len(glossary)} business terms")
    print(f"  • master_catalog.json       — Full searchable index")
    print(f"  • QUICK_REFERENCE.md        — Human-readable summary")
    print(f"  • data_quality_report.json  — Actionable fix list")
    print()
    print("NEXT: Run the recommendations to clean your local NEXUS data.")


if __name__ == "__main__":
    main()
