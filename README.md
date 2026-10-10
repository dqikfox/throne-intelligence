# THRONE Intelligence

Integration layer for IBM watsonx Data Intelligence with local THRONE sovereign infrastructure. Data governance, quality, lineage, and catalog operations via MCP.

## Overview

THRONE Intelligence bridges IBM watsonx Data Intelligence with the local THRONE sovereign seat. It provides data governance automation, quality analysis, lineage tracking, and catalog enrichment through the watsonx MCP server, while maintaining local-first architecture and zero-cloud dependencies where possible.

## Development

This repository uses a standard make interface:

- make init
- make lint
- make test
- make benchmark
- make docs
- make format
- make release

## NEXUS Data Bridge

### Export NEXUS CORE to IBM Format

```powershell
python3 src\throne_intelligence\nexus_to_ibm_bridge.py --format both --output E:\ultron-memory\exports
```

**Outputs:**
- `nexus_catalog.jsonl` — JSONL for IBM catalog ingestion (3021 records)
- `nexus_notes.csv` — CSV for metadata enrichment
- `nexus_docs.csv` — CSV for document analysis

### Data Sources

| Source | Path | Records |
|--------|------|---------|
| NEXUS Notes | `nexus-core/data/nexus.db` | 2,931 |
| NEXUS Docs | `nexus-core/docs/` + `notes/` | 89 |
| Ingest | `nexus-core/ingest/` | 1+ |

### IBM MCP Configuration

See `ibm_bob_config.json` for full MCP server configuration.

**Key environment variables:**
- `IBM_API_KEY` — Windows user env (also in Hermes .env)
- `DI_SERVICE_URL` — `https://api.au-syd.dai.cloud.ibm.com`
- `DI_ENV_MODE` — `SaaS`

### IBM Trial Status

| Service | Expires |
|---------|---------|
| IBM Bob Trial | Nov 10, 2026 |
| IBM Cloud | Nov 10, 2026 |
| watsonx Orchestrate | Nov 8, 2026 |

### Next Steps

1. Import `nexus_catalog.jsonl` into IBM watsonx Data Intelligence
2. Run data quality analysis on imported catalog
3. Set up lineage tracking for NEXUS note origins
4. Create business glossary from exported tags
5. Schedule automated sync (every 6 hours)
