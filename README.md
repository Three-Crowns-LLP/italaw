# italaw Investment Arbitration Downloader

A Python tool that searches [italaw.com](https://www.italaw.com) — the world's largest open-access investment arbitration database — identifies cases with substantial publicly available materials (procedural orders, hearing transcripts, and awards), and downloads the relevant PDFs into an organised local folder.

## What it does

1. **Discovers cases** by crawling the italaw browse pages (A–Z by claimant, or filtered by respondent state).
2. **Filters for publicly rich cases** — only cases that have at least one award, decision, procedural order, hearing transcript, or ruling are downloaded.
3. **Downloads PDFs** into `~/Documents/investment arbitration materials/`, organised into one sub-folder per case.
4. **Saves a manifest** (`_manifest.json`) so re-runs skip already-downloaded files.

## Requirements

- Python 3.10+
- `requests`, `beautifulsoup4`, `lxml`

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

```
python italaw_downloader.py [options]
```

### Options

| Flag | Description |
|---|---|
| `--max-cases N` | Stop after processing N cases (useful for testing) |
| `--respondent-state STATE` | Filter to cases against a specific state, e.g. `"Argentina"` |
| `--output-dir DIR` | Change the save location (default: `~/Documents/investment arbitration materials`) |
| `--doc-types TYPE ...` | Override which document types to download (default: award, decision, order, transcript, ruling) |
| `--all-docs` | Download every PDF on a case page, not just target types |
| `--dry-run` | Print what would be downloaded without saving anything |
| `--verbose` | Enable debug-level logging |

### Examples

```bash
# Quick test — process 10 cases only
python italaw_downloader.py --max-cases 10 --dry-run

# Download all cases against Argentina
python italaw_downloader.py --respondent-state "Argentina"

# Download only final awards and decisions (skip procedural orders / transcripts)
python italaw_downloader.py --doc-types award decision

# Download everything publicly available for every case on italaw
python italaw_downloader.py --all-docs
```

## Output structure

```
~/Documents/investment arbitration materials/
├── _manifest.json                          ← tracks downloaded files
├── achmea-bv-v-slovak-republic/
│   ├── award-on-jurisdiction.pdf
│   └── procedural-order-no-3.pdf
├── apotex-inc-v-united-states-of-america/
│   ├── award.pdf
│   └── hearing-transcript-day-1.pdf
└── ...
```

## Notes

- The tool rate-limits requests to ~1.5 s between page fetches and ~2 s between PDF downloads, to avoid overloading italaw's servers.
- Retries with exponential backoff (2 s → 4 s → 8 s → 16 s) handle transient network errors.
- Running the tool a second time will skip any PDFs already saved (idempotent).
- italaw hosts thousands of cases; a full run without `--max-cases` may take several hours and produce many gigabytes of PDFs.

## Data source

All documents are sourced from [italaw.com](https://www.italaw.com), maintained by Professor Andrew Newcombe at the University of Victoria Faculty of Law. italaw is a free, open-access database of investor-state arbitration materials.
