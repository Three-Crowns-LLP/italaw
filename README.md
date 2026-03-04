# italaw Investment Arbitration Downloader

A tool that searches [italaw.com](https://www.italaw.com) — the world's largest open-access investment arbitration database — identifies cases with substantial publicly available materials (procedural orders, hearing transcripts, and awards), and downloads the relevant PDFs to a local folder.

---

## Quick start for Windows users (no command line needed)

### Step 1 — Install Python (one-time, ask IT if needed)

1. Go to **[python.org/downloads](https://www.python.org/downloads/)** and download the latest Python 3 installer.
2. Run the installer. **Tick "Add Python to PATH"** before clicking Install.
3. Click Install Now and wait for it to finish.

> Python is free, open-source software widely used in law firms and research institutions.

### Step 2 — Run the tool

Double-click **`run.bat`**.

That's it. On first run it automatically installs the required libraries, then opens this window:

```
┌──────────────────────────────────────────────────────────────┐
│  italaw  Investment Arbitration Downloader                   │
│  Downloads publicly available PDFs from italaw.com           │
├──────────────────────────────────────────────────────────────┤
│  Save to folder:  C:\Users\You\Documents\investment arb...  │
│  Respondent state: [________________]  (leave blank = all)  │
│  Max cases:        [____]  (leave blank = all cases)         │
│  Document types:  ☑ Awards & Decisions  ☑ Procedural Orders │
│                   ☑ Hearing Transcripts ☑ Rulings & Judgments│
│  □ Dry run (list files without downloading)                  │
│                                                              │
│  [ Start Download ]  [ Stop ]          [ Open output folder ]│
├──────────────────────────────────────────────────────────────┤
│  Progress log                                                │
│  > Collecting case links...                                  │
│  > [1/42] Achmea BV v Slovak Republic                        │
│  > ...                                                       │
└──────────────────────────────────────────────────────────────┘
```

### Tips

| Goal | What to do |
|---|---|
| Test before a full run | Enter `10` in **Max cases** and tick **Dry run** first |
| Only one country | Type the country name in **Respondent state**, e.g. `Argentina` |
| Only final awards | Un-tick Procedural Orders and Hearing Transcripts |
| Change save location | Click **Browse…** next to the folder field |
| Resume after stopping | Just run again — already-downloaded files are skipped |

---

## Command-line usage (advanced)

```bash
# Install dependencies
pip install -r requirements.txt

# Dry run on 10 cases
python italaw_downloader.py --max-cases 10 --dry-run

# All cases against Argentina
python italaw_downloader.py --respondent-state "Argentina"

# Only awards and decisions
python italaw_downloader.py --doc-types award decision

# Download everything, unlimited
python italaw_downloader.py --all-docs
```

### All options

| Flag | Description |
|---|---|
| `--max-cases N` | Stop after N cases (useful for testing) |
| `--respondent-state STATE` | Filter by state name, e.g. `"Argentina"` |
| `--output-dir DIR` | Change the save location |
| `--doc-types TYPE ...` | Override document types to download |
| `--all-docs` | Download every PDF on each case page |
| `--dry-run` | List what would be downloaded without saving |
| `--verbose` | Enable debug-level logging |

---

## Output structure

```
Documents/
└── investment arbitration materials/
    ├── _manifest.json                     ← tracks downloaded files
    ├── achmea-bv-v-slovak-republic/
    │   ├── award-on-jurisdiction.pdf
    │   └── procedural-order-no-3.pdf
    ├── apotex-inc-v-united-states/
    │   ├── award.pdf
    │   └── hearing-transcript-day-1.pdf
    └── ...
```

---

## Notes

- Requests are rate-limited (~1.5 s between pages, ~2 s between PDFs) to be respectful of italaw's servers.
- Re-running the tool skips files that were already downloaded (safe to resume).
- A full run across all italaw cases may take several hours and produce many gigabytes of PDFs. Use `--max-cases` or `--respondent-state` to scope your download.

## Data source

All documents are sourced from [italaw.com](https://www.italaw.com), maintained by Professor Andrew Newcombe at the University of Victoria Faculty of Law.
