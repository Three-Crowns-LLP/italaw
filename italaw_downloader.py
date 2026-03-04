#!/usr/bin/env python3
"""
italaw Investment Arbitration Case Downloader

Searches italaw.com for investment arbitration cases that have largely publicly
available documents (procedural orders, hearing transcripts, and awards), then
downloads the relevant PDFs to a local folder.

Usage:
    python italaw_downloader.py [options]

Examples:
    # Download all publicly available cases (may take a long time)
    python italaw_downloader.py

    # Download a sample of 20 cases to test
    python italaw_downloader.py --max-cases 20

    # Filter to cases against a specific respondent state
    python italaw_downloader.py --respondent-state "Argentina"

    # Custom output directory
    python italaw_downloader.py --output-dir "/path/to/folder"

    # Only download awards and decisions (skip procedural orders/transcripts)
    python italaw_downloader.py --doc-types award decision

    # List cases found without downloading
    python italaw_downloader.py --dry-run --max-cases 50
"""

import os
import re
import json
import time
import logging
import argparse
import threading
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlencode

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ITALAW_BASE = "https://www.italaw.com"

# Default output directory: ~/Documents/investment arbitration materials
DEFAULT_OUTPUT_DIR = Path.home() / "Documents" / "investment arbitration materials"

# Seconds to wait between HTTP requests (be respectful of the server)
REQUEST_DELAY = 1.5

# Seconds to wait between PDF downloads
DOWNLOAD_DELAY = 2.0

MAX_RETRIES = 4
RETRY_BACKOFF = [2, 4, 8, 16]  # exponential backoff in seconds

# Document types considered "target" documents that make a case publicly rich
TARGET_DOC_KEYWORDS = {
    "award",
    "decision",
    "procedural order",
    "order",
    "hearing transcript",
    "transcript",
    "ruling",
    "judgment",
}

# Minimum number of target documents for a case to be considered "largely public"
MIN_TARGET_DOCS = 1

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def get_page(session: requests.Session, url: str) -> requests.Response | None:
    """Fetch a URL with retries and exponential backoff."""
    for attempt, backoff in enumerate(RETRY_BACKOFF, 1):
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", backoff * 2))
                log.warning(f"Rate limited. Waiting {wait}s before retry...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return resp
        except requests.RequestException as exc:
            log.warning(f"Request failed (attempt {attempt}/{len(RETRY_BACKOFF)}): {url} — {exc}")
            if attempt < len(RETRY_BACKOFF):
                time.sleep(backoff)
    log.error(f"Giving up on: {url}")
    return None


# ---------------------------------------------------------------------------
# Text / path helpers
# ---------------------------------------------------------------------------

def slugify(text: str, max_len: int = 80) -> str:
    """Convert a string to a safe filesystem name."""
    text = re.sub(r"[^\w\s\-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "-", text.strip())
    return text[:max_len].rstrip("-") or "unnamed"


def is_target_doc(label: str) -> bool:
    """Return True if the document label matches one of our target types."""
    low = label.lower()
    return any(kw in low for kw in TARGET_DOC_KEYWORDS)


# ---------------------------------------------------------------------------
# Case list scraping
# ---------------------------------------------------------------------------

def get_browse_urls(respondent_state: str | None = None) -> list[str]:
    """Build the list of browse URLs to crawl for case links."""
    if respondent_state:
        # Single URL filtered by respondent state keyword
        params = urlencode({"field_respondent_state_name": respondent_state})
        return [f"{ITALAW_BASE}/browse/respondent-state?{params}"]

    # All cases: browse A–Z by claimant investor name, plus numeric
    letters = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + ["0-9"]
    return [f"{ITALAW_BASE}/browse/claimant-investor/{letter}" for letter in letters]


def scrape_case_links_from_page(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """Extract (case_name, case_url) pairs from a single browse page."""
    cases = []
    # italaw browse pages list cases as links to /cases/<id>
    for link in soup.select("a[href]"):
        href = link.get("href", "")
        if re.search(r"/cases/\d+", href) or re.search(r"/cases/[a-z0-9\-]+$", href):
            full_url = urljoin(ITALAW_BASE, href)
            name = link.get_text(strip=True)
            if name:
                cases.append((name, full_url))
    return cases


def get_next_page_url(soup: BeautifulSoup) -> str | None:
    """Return the URL of the next pagination page, or None."""
    selectors = [
        "li.pager-next a",
        "a[title='Go to next page']",
        ".pager__item--next a",
        "a[rel='next']",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el and el.get("href"):
            return urljoin(ITALAW_BASE, el["href"])
    return None


def collect_all_cases(
    session: requests.Session,
    respondent_state: str | None = None,
    max_cases: int | None = None,
) -> list[tuple[str, str]]:
    """Crawl browse pages and return a deduplicated list of (name, url) tuples."""
    browse_urls = get_browse_urls(respondent_state)
    seen_urls: set[str] = set()
    all_cases: list[tuple[str, str]] = []

    for browse_url in browse_urls:
        page_url: str | None = browse_url
        while page_url:
            log.info(f"Fetching case list: {page_url}")
            resp = get_page(session, page_url)
            if not resp:
                break

            soup = BeautifulSoup(resp.text, "lxml")
            for name, url in scrape_case_links_from_page(soup):
                if url not in seen_urls:
                    seen_urls.add(url)
                    all_cases.append((name, url))

            if max_cases and len(all_cases) >= max_cases:
                log.info(f"Reached max-cases limit ({max_cases}). Stopping browse.")
                return all_cases[:max_cases]

            page_url = get_next_page_url(soup)

    return all_cases


# ---------------------------------------------------------------------------
# Case document scraping
# ---------------------------------------------------------------------------

def scrape_case_documents(
    session: requests.Session, case_url: str
) -> list[dict]:
    """
    Fetch a case page and return a list of document dicts:
        {title, doc_type, pdf_url, is_target}
    """
    resp = get_page(session, case_url)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    documents: list[dict] = []
    seen_pdf_urls: set[str] = set()

    # Strategy 1: italaw renders documents in a <table> or <div> with rows
    # Each row typically has: doc type label | document title | PDF link

    # Try table rows first
    for row in soup.select("table tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        row_text = " ".join(c.get_text(" ", strip=True) for c in cells)
        pdf_links = row.select("a[href$='.pdf'], a[href*='case-documents']")
        for link in pdf_links:
            href = link.get("href", "")
            if not href:
                continue
            pdf_url = urljoin(ITALAW_BASE, href)
            if pdf_url in seen_pdf_urls:
                continue
            seen_pdf_urls.add(pdf_url)
            title = link.get_text(strip=True) or Path(urlparse(pdf_url).path).stem
            documents.append({
                "title": title,
                "doc_type": row_text,
                "pdf_url": pdf_url,
                "is_target": is_target_doc(row_text),
            })

    # Strategy 2: Look for field-items / view-rows (Drupal-style markup)
    for item in soup.select(".views-row, .field-item, .view-content .views-field"):
        pdf_links = item.select("a[href$='.pdf'], a[href*='case-documents']")
        label_el = item.select_one(
            ".views-field-title, .field-label, .document-type, span"
        )
        label = label_el.get_text(strip=True) if label_el else item.get_text(" ", strip=True)[:100]
        for link in pdf_links:
            href = link.get("href", "")
            if not href:
                continue
            pdf_url = urljoin(ITALAW_BASE, href)
            if pdf_url in seen_pdf_urls:
                continue
            seen_pdf_urls.add(pdf_url)
            title = link.get_text(strip=True) or Path(urlparse(pdf_url).path).stem
            documents.append({
                "title": title,
                "doc_type": label,
                "pdf_url": pdf_url,
                "is_target": is_target_doc(label),
            })

    # Strategy 3: Catch all remaining PDF links anywhere on the page
    for link in soup.select("a[href$='.pdf'], a[href*='/case-documents/']"):
        href = link.get("href", "")
        if not href:
            continue
        pdf_url = urljoin(ITALAW_BASE, href)
        if pdf_url in seen_pdf_urls:
            continue
        seen_pdf_urls.add(pdf_url)
        title = link.get_text(strip=True) or Path(urlparse(pdf_url).path).stem

        # Try to infer doc type from nearby text
        parent_label = ""
        for ancestor in link.parents:
            text = ancestor.get_text(" ", strip=True)
            if 10 < len(text) < 300:
                parent_label = text
                break

        documents.append({
            "title": title,
            "doc_type": parent_label,
            "pdf_url": pdf_url,
            "is_target": is_target_doc(parent_label) or is_target_doc(title),
        })

    return documents


def case_is_publicly_rich(documents: list[dict], min_target: int = MIN_TARGET_DOCS) -> bool:
    """Return True if the case has enough publicly available target documents."""
    target_count = sum(1 for d in documents if d["is_target"])
    return target_count >= min_target


# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------

def download_pdf(
    session: requests.Session,
    pdf_url: str,
    dest_path: Path,
    dry_run: bool = False,
) -> bool:
    """Download a PDF to dest_path. Returns True on success (or skip)."""
    if dest_path.exists():
        log.info(f"    [skip] Already downloaded: {dest_path.name}")
        return True

    if dry_run:
        log.info(f"    [dry-run] Would download: {pdf_url}")
        return True

    log.info(f"    Downloading: {pdf_url}")
    for attempt, backoff in enumerate(RETRY_BACKOFF, 1):
        try:
            with session.get(pdf_url, timeout=60, stream=True) as resp:
                resp.raise_for_status()
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with open(dest_path, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=16384):
                        fh.write(chunk)
            time.sleep(DOWNLOAD_DELAY)
            log.info(f"    [ok] Saved: {dest_path.name}")
            return True
        except requests.RequestException as exc:
            log.warning(f"    Download failed (attempt {attempt}): {exc}")
            if attempt < len(RETRY_BACKOFF):
                time.sleep(backoff)

    log.error(f"    [fail] Could not download: {pdf_url}")
    return False


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

def load_manifest(manifest_path: Path) -> dict:
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"cases": {}}


def save_manifest(manifest_path: Path, manifest: dict) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(
    max_cases: int | None = None,
    respondent_state: str | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    doc_types: list[str] | None = None,
    dry_run: bool = False,
    all_docs: bool = False,
    stop_flag: "threading.Event | None" = None,
) -> None:
    """
    Main entry point: discover cases, filter for public richness, download PDFs.

    Args:
        max_cases:        Stop after processing this many cases.
        respondent_state: Free-text filter for respondent state name (e.g. "Argentina").
        output_dir:       Root folder where PDFs are saved.
        doc_types:        Override the default target document type keywords.
        dry_run:          Print what would be downloaded without actually downloading.
        all_docs:         Download every document on a case page, not just target types.
        stop_flag:        threading.Event; if set, the run loop will exit cleanly.
    """
    if doc_types:
        TARGET_DOC_KEYWORDS.clear()
        TARGET_DOC_KEYWORDS.update(t.lower() for t in doc_types)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "_manifest.json"
    manifest = load_manifest(manifest_path)

    session = make_session()

    log.info("=" * 60)
    log.info("italaw Investment Arbitration Downloader")
    log.info(f"Output directory : {output_dir}")
    log.info(f"Target doc types : {sorted(TARGET_DOC_KEYWORDS)}")
    log.info(f"Max cases        : {max_cases or 'unlimited'}")
    log.info(f"Respondent state : {respondent_state or 'all'}")
    log.info(f"Dry run          : {dry_run}")
    log.info("=" * 60)

    # Step 1: Collect case URLs
    log.info("Step 1: Collecting case links from browse pages...")
    cases = collect_all_cases(session, respondent_state, max_cases)
    log.info(f"Found {len(cases)} unique cases.")

    # Step 2: Process each case
    stats = {"processed": 0, "skipped_no_docs": 0, "skipped_not_public": 0,
             "downloaded": 0, "failed": 0}

    for idx, (case_name, case_url) in enumerate(cases, 1):
        if stop_flag and stop_flag.is_set():
            log.info("Stop flag set — exiting early.")
            break

        log.info(f"\n[{idx}/{len(cases)}] {case_name}")
        log.info(f"  URL: {case_url}")
        stats["processed"] += 1

        # Step 2a: Scrape documents
        documents = scrape_case_documents(session, case_url)
        if not documents:
            log.info("  No documents found. Skipping.")
            stats["skipped_no_docs"] += 1
            continue

        # Step 2b: Check if case is publicly rich enough
        if not case_is_publicly_rich(documents):
            log.info(
                f"  Only {sum(1 for d in documents if d['is_target'])} target "
                f"document(s) found (minimum: {MIN_TARGET_DOCS}). Skipping."
            )
            stats["skipped_not_public"] += 1
            continue

        target_docs = [d for d in documents if d["is_target"] or all_docs]
        log.info(
            f"  Found {len(documents)} total doc(s), "
            f"{len(target_docs)} to download."
        )

        # Step 2c: Create case subfolder
        case_slug = slugify(case_name)
        case_dir = output_dir / case_slug
        if not dry_run:
            case_dir.mkdir(parents=True, exist_ok=True)

        # Step 2d: Download each target document
        case_record = manifest["cases"].setdefault(case_url, {
            "name": case_name, "downloaded": []
        })

        for doc in target_docs:
            pdf_url = doc["pdf_url"]
            filename = slugify(doc["title"]) + ".pdf"
            dest = case_dir / filename

            ok = download_pdf(session, pdf_url, dest, dry_run=dry_run)
            if ok:
                stats["downloaded"] += 1
                if pdf_url not in case_record["downloaded"]:
                    case_record["downloaded"].append(pdf_url)
            else:
                stats["failed"] += 1

        if not dry_run:
            save_manifest(manifest_path, manifest)

    # Summary
    log.info("\n" + "=" * 60)
    log.info("Download complete.")
    log.info(f"  Cases processed       : {stats['processed']}")
    log.info(f"  Skipped (no docs)     : {stats['skipped_no_docs']}")
    log.info(f"  Skipped (not public)  : {stats['skipped_not_public']}")
    log.info(f"  PDFs downloaded/found : {stats['downloaded']}")
    log.info(f"  PDFs failed           : {stats['failed']}")
    log.info(f"  Output directory      : {output_dir}")
    if not dry_run:
        log.info(f"  Manifest saved to     : {manifest_path}")
    log.info("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Download investment arbitration materials from italaw.com.\n"
            "Searches for cases with publicly available procedural orders,\n"
            "hearing transcripts, and awards, then saves PDFs locally."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=None,
        metavar="N",
        help="Stop after processing N cases (useful for testing). Default: process all.",
    )
    parser.add_argument(
        "--respondent-state",
        type=str,
        default=None,
        metavar="STATE",
        help=(
            "Filter cases by respondent state name (case-insensitive partial match). "
            "Example: --respondent-state 'Argentina'"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        metavar="DIR",
        help=(
            f"Directory where PDFs are saved. "
            f"Default: {DEFAULT_OUTPUT_DIR}"
        ),
    )
    parser.add_argument(
        "--doc-types",
        type=str,
        nargs="+",
        default=None,
        metavar="TYPE",
        help=(
            "Override the document types to download. "
            "Default: award, decision, procedural order, order, transcript, ruling, judgment. "
            "Example: --doc-types award decision"
        ),
    )
    parser.add_argument(
        "--all-docs",
        action="store_true",
        help="Download every PDF found on a case page, not just target document types.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be downloaded without saving any files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    run(
        max_cases=args.max_cases,
        respondent_state=args.respondent_state,
        output_dir=Path(args.output_dir),
        doc_types=args.doc_types,
        dry_run=args.dry_run,
        all_docs=args.all_docs,
    )


if __name__ == "__main__":
    main()
