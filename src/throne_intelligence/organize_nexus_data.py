#!/usr/bin/env python3
"""NEXUS Data Organizer — Auto-classify and catalog NEXUS notes using IBM-ready taxonomy.

Reads sanitized NEXUS export, classifies by topic, assigns business glossary terms,
and generates an IBM watsonx Data Intelligence-compatible catalog.

Usage:
    python organize_nexus_data.py --input E:/ultron-memory/exports/nexus_catalog_sanitized.jsonl --output E:/ultron-memory/exports/nexus_organized/
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# Topic classification rules (regex-based for speed)
TOPIC_RULES = {
    "api_keys_credentials": {
        "patterns": [r"api[_\s]?key", r"token", r"secret", r"password", r"credential", r"bearer", r"github_pat", r"elevenlabs", r"huggingface"],
        "glossary_terms": ["API Key", "Authentication Token", "Credential Management"],
        "sensitivity": "HIGH"
    },
    "infrastructure_systems": {
        "patterns": [r"server", r"host", r"port", r"ssh", r"network", r"firewall", r"router", r"vpn", r"tailscale", r"ip address", r"subnet", r"dns"],
        "glossary_terms": ["Network Infrastructure", "Server Configuration", "IP Address"],
        "sensitivity": "MEDIUM"
    },
    "ai_ml_models": {
        "patterns": [r"llm", r"model", r"ollama", r"embedding", r"vector", r"chroma", r"rag", r"fine-tune", r"training", r"inference", r"gpu", r"cuda", r"ollama", r"heretik", r"starscream"],
        "glossary_terms": ["Large Language Model", "Vector Database", "Model Inference"],
        "sensitivity": "LOW"
    },
    "project_development": {
        "patterns": [r"project", r"repo", r"github", r"git", r"commit", r"branch", r"pull request", r"issue", r"milestone", r"release", r"version"],
        "glossary_terms": ["Software Repository", "Version Control", "Release Management"],
        "sensitivity": "LOW"
    },
    "hardware_devices": {
        "patterns": [r"rtx", r"gpu", r"cpu", r"ram", r"ssd", r"nvidia", r"samsung", r"phone", r"device", r"serial", r"adb", r"usb"],
        "glossary_terms": ["Hardware Specification", "Device Configuration", "GPU Memory"],
        "sensitivity": "LOW"
    },
    "data_governance": {
        "patterns": [r"catalog", r"governance", r"lineage", r"quality", r"metadata", r"enrichment", r"classification", r"sensitive", r"pii", r"redact"],
        "glossary_terms": ["Data Catalog", "Data Lineage", "Metadata Management"],
        "sensitivity": "MEDIUM"
    },
    "voice_audio": {
        "patterns": [r"elevenlabs", r"voice", r"tts", r"speech", r"audio", r"microphone", r"synthesis", r"transcription"],
        "glossary_terms": ["Text-to-Speech", "Voice Synthesis", "Audio Pipeline"],
        "sensitivity": "LOW"
    },
    "network_connectivity": {
        "patterns": [r"tailscale", r"vpn", r"mesh", r"starlink", r"router", r"gateway", r"ping", r"latency", r"bandwidth", r"wifi", r"ethernet"],
        "glossary_terms": ["VPN Mesh", "Network Gateway", "Latency Monitoring"],
        "sensitivity": "LOW"
    },
    "automation_orchestration": {
        "patterns": [r"cron", r"scheduler", r"pipeline", r"workflow", r"orchestrate", r"agent", r"mcp", r"automation", r"deploy"],
        "glossary_terms": ["Workflow Orchestration", "Scheduled Task", "Agent Protocol"],
        "sensitivity": "LOW"
    },
    "security_access": {
        "patterns": [r"1password", r"vault", r"encrypt", r"decrypt", r"permission", r"role", r"access control", r"auth", r"login", r"2fa"],
        "glossary_terms": ["Password Vault", "Access Control", "Encryption at Rest"],
        "sensitivity": "HIGH"
    },
    "alchemy_research": {
        "patterns": [r"alchemy", r"philalethes", r"ripley", r"zodiac", r"mercury", r"sulphur", r"salt", r"athanor", r"prima materia", r"lapis"],
        "glossary_terms": ["Alchemical Corpus", "Philalethes Tradition", "Prima Materia"],
        "sensitivity": "LOW"
    },
    "personal_notes": {
        "patterns": [r"daily", r"journal", r"todo", r"reminder", r"meeting", r"call", r"appointment", r"schedule", r"personal"],
        "glossary_terms": ["Personal Note", "Daily Log", "Task List"],
        "sensitivity": "LOW"
    }
}


def classify_record(record: dict) -> dict:
    """Classify a record into topics based on content and title."""
    text = (record.get("title", "") + " " + record.get("content", "")).lower()
    matched_topics = []
    
    for topic_name, rules in TOPIC_RULES.items():
        score = 0
        for pattern in rules["patterns"]:
            matches = len(re.findall(pattern, text, re.IGNORECASE))
            score += matches
        
        if score > 0:
            matched_topics.append({
                "topic": topic_name,
                "score": score,
                "glossary_terms": rules["glossary_terms"],
                "sensitivity": rules["sensitivity"]
            })
    
    # Sort by score descending, pick top topic
    matched_topics.sort(key=lambda x: x["score"], reverse=True)
    primary_topic = matched_topics[0] if matched_topics else {
        "topic": "uncategorized",
        "score": 0,
        "glossary_terms": ["Unclassified"],
        "sensitivity": "UNKNOWN"
    }
    
    return {
        "primary_topic": primary_topic["topic"],
        "topic_score": primary_topic["score"],
        "glossary_terms": primary_topic["glossary_terms"],
        "sensitivity": primary_topic["sensitivity"],
        "all_topics": [t["topic"] for t in matched_topics[:3]],
        "sanitized": record.get("_sanitized", False)
    }


def generate_summary(records: list, classifications: list) -> dict:
    """Generate catalog summary statistics."""
    topic_counts = Counter(c["primary_topic"] for c in classifications)
    sensitivity_counts = Counter(c["sensitivity"] for c in classifications)
    sanitized_count = sum(1 for c in classifications if c["sanitized"])
    
    # Find duplicates by title similarity
    titles = [r.get("title", "").lower()[:50] for r in records]
    dupes = {title: count for title, count in Counter(titles).items() if count > 1}
    
    return {
        "total_records": len(records),
        "topic_distribution": dict(topic_counts.most_common()),
        "sensitivity_distribution": dict(sensitivity_counts),
        "sanitized_records": sanitized_count,
        "duplicate_groups": len(dupes),
        "duplicate_titles": list(dupes.keys())[:10],
        "generated_at": datetime.now().isoformat()
    }


def main():
    parser = argparse.ArgumentParser(description="Organize NEXUS data for IBM watsonx")
    parser.add_argument("--input", default="E:/ultron-memory/exports/nexus_catalog_sanitized.jsonl")
    parser.add_argument("--output-dir", default="E:/ultron-memory/exports/nexus_organized")
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Reading {input_path}...")
    records = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    
    print(f"Classifying {len(records)} records...")
    classifications = []
    organized = defaultdict(list)
    
    for record in records:
        classification = classify_record(record)
        classifications.append(classification)
        
        # Enrich record with classification
        enriched = {
            **record,
            "classification": classification,
            "_cataloged": True
        }
        organized[classification["primary_topic"]].append(enriched)
    
    # Write topic-organized files
    for topic, topic_records in organized.items():
        output_file = output_dir / f"topic_{topic}.jsonl"
        with open(output_file, "w", encoding="utf-8") as f:
            for r in topic_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  {topic}: {len(topic_records)} records -> {output_file.name}")
    
    # Generate summary
    summary = generate_summary(records, classifications)
    summary_file = output_dir / "catalog_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    # Generate IBM glossary import CSV
    glossary_terms = set()
    for c in classifications:
        glossary_terms.update(c["glossary_terms"])
    
    glossary_file = output_dir / "business_glossary.csv"
    with open(glossary_file, "w", newline="", encoding="utf-8") as f:
        import csv
        writer = csv.writer(f)
        writer.writerow(["term_name", "definition", "category", "status"])
        for term in sorted(glossary_terms):
            writer.writerow([
                term,
                f"Auto-generated glossary term from NEXUS classification: {term}",
                "NEXUS_DATA",
                "DRAFT"
            ])
    
    print(f"\n{'='*60}")
    print(f"ORGANIZATION COMPLETE")
    print(f"{'='*60}")
    print(f"Total records: {summary['total_records']}")
    print(f"Topics found: {len(summary['topic_distribution'])}")
    print(f"Sanitized records: {summary['sanitized_records']}")
    print(f"Duplicate groups: {summary['duplicate_groups']}")
    print(f"\nTopic distribution:")
    for topic, count in summary['topic_distribution'].items():
        print(f"  {topic}: {count}")
    print(f"\nSensitivity distribution:")
    for level, count in summary['sensitivity_distribution'].items():
        print(f"  {level}: {count}")
    print(f"\nFiles written to: {output_dir}")
    print(f"  Summary: {summary_file.name}")
    print(f"  Glossary: {glossary_file.name}")
    print(f"  Topic files: {len(organized)} files")


if __name__ == "__main__":
    main()
