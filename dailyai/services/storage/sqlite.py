"""SQLite implementation of persistent deduplication and audit storage."""

from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Union
from dailyai.logging_config import get_logger
from dailyai.models.pipeline import PipelineRunReport
from dailyai.services.storage.base import BaseDeduplicationStore

logger = get_logger("storage.sqlite")


from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "fbclid", "gclid", "mc_cid", "mc_eid", "_hsenc", "_hsmi"
}


def normalize_url(url: str) -> str:
    """Normalize URL by stripping tracking query parameters, fragments, trailing slashes, and lowercasing."""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower()
        netloc = parts.netloc.lower()
        path = parts.path.rstrip("/")
        # Filter tracking query parameters
        query_pairs = parse_qsl(parts.query, keep_blank_values=False)
        filtered_pairs = [(k, v) for k, v in query_pairs if k.lower() not in TRACKING_PARAMS]
        query = urlencode(filtered_pairs)
        rebuilt = urlunsplit((scheme, netloc, path, query, ""))
        return rebuilt.rstrip("/")
    except Exception:
        return url.strip().lower().rstrip("/")


def compute_url_hash(url: str) -> str:
    """Compute SHA-256 hash of normalized URL."""
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


def normalize_title(title: str) -> str:
    """Normalize title for fuzzy similarity comparison."""
    # Lowercase, remove punctuation and extra whitespaces
    cleaned = re.sub(r"[^\w\s]", " ", title.lower())
    return " ".join(cleaned.split())


class SQLiteDeduplicationStore(BaseDeduplicationStore):
    """SQLite backed persistent store for URL and title deduplication and run history."""

    def __init__(self, db_path: Union[str, Path] = "data/dailyai.sqlite"):
        self.db_path = Path(db_path)
        self._ensure_db_dir()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()
        logger.debug(f"Initialized SQLite storage at {self.db_path}")

    def _ensure_db_dir(self) -> None:
        """Create parent directory if it does not exist."""
        if self.db_path.parent:
            os.makedirs(self.db_path.parent, exist_ok=True)

    def _init_tables(self) -> None:
        """Initialize database schema."""
        cursor = self._conn.cursor()
        # Enable WAL mode for better concurrency
        cursor.execute("PRAGMA journal_mode=WAL;")
        
        # Table: Seen URLs (during research phase)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seen_urls (
                url_hash TEXT PRIMARY KEY,
                original_url TEXT NOT NULL,
                title TEXT,
                domain TEXT NOT NULL,
                draft_id TEXT,
                first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_seen_domain ON seen_urls(domain);")

        # Table: Published Articles (sent in newsletters)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS published_articles (
                url_hash TEXT PRIMARY KEY,
                original_url TEXT NOT NULL,
                normalized_title TEXT NOT NULL,
                title TEXT NOT NULL,
                domain TEXT NOT NULL,
                newsletter_id TEXT NOT NULL,
                published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_published_domain ON published_articles(domain);")

        # Table: Pipeline Run History
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                run_id TEXT PRIMARY KEY,
                started_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP NOT NULL,
                duration_seconds REAL NOT NULL,
                drafts_collected INTEGER NOT NULL,
                articles_verified INTEGER NOT NULL,
                articles_rejected INTEGER NOT NULL,
                articles_published INTEGER NOT NULL,
                delivery_status TEXT NOT NULL,
                is_success INTEGER NOT NULL,
                report_json TEXT NOT NULL
            );
        """)
        self._conn.commit()

    def is_url_processed(self, url: str) -> bool:
        """Check if URL exists in published_articles or seen_urls."""
        url_hash = compute_url_hash(url)
        cursor = self._conn.cursor()
        
        # Check published articles first
        cursor.execute("SELECT 1 FROM published_articles WHERE url_hash = ?", (url_hash,))
        if cursor.fetchone():
            return True
            
        # Check seen URLs
        cursor.execute("SELECT 1 FROM seen_urls WHERE url_hash = ?", (url_hash,))
        return cursor.fetchone() is not None

    def is_title_duplicate(self, title: str, threshold: float = 0.85) -> bool:
        """Check if title has a high similarity to already published titles."""
        norm_title = normalize_title(title)
        if not norm_title:
            return False

        cursor = self._conn.cursor()
        # Retrieve recent published titles (last 30 days)
        cursor.execute("""
            SELECT normalized_title FROM published_articles 
            ORDER BY published_at DESC LIMIT 200
        """)
        rows = cursor.fetchall()
        
        for row in rows:
            prev_title = row["normalized_title"]
            ratio = difflib.SequenceMatcher(None, norm_title, prev_title).ratio()
            if ratio >= threshold:
                logger.info(f"Duplicate title detected (similarity {ratio:.2f}): '{title}' vs '{prev_title}'")
                return True
        return False

    def mark_url_seen(
        self,
        url: str,
        title: str,
        domain: str,
        draft_id: Optional[str] = None,
    ) -> None:
        """Record seen URL."""
        url_hash = compute_url_hash(url)
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO seen_urls (url_hash, original_url, title, domain, draft_id, first_seen_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (url_hash, url, title, domain, draft_id, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def mark_article_published(
        self,
        url: str,
        title: str,
        domain: str,
        newsletter_id: str,
    ) -> None:
        """Record officially published article."""
        url_hash = compute_url_hash(url)
        norm_title = normalize_title(title)
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO published_articles 
            (url_hash, original_url, normalized_title, title, domain, newsletter_id, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (url_hash, url, norm_title, title, domain, newsletter_id, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def record_pipeline_run(self, report: PipelineRunReport) -> None:
        """Store pipeline execution report."""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO pipeline_runs 
            (run_id, started_at, finished_at, duration_seconds, drafts_collected, 
             articles_verified, articles_rejected, articles_published, delivery_status, is_success, report_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.run_id,
                report.started_at.isoformat(),
                report.finished_at.isoformat(),
                report.duration_seconds,
                report.drafts_collected,
                report.articles_verified,
                report.articles_rejected,
                report.articles_published,
                report.delivery_status,
                1 if report.is_success else 0,
                report.model_dump_json(),
            ),
        )
        self._conn.commit()
        logger.info(f"Recorded pipeline run report '{report.run_id}' in SQLite database.")

    def get_recent_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent pipeline run reports."""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT report_json FROM pipeline_runs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        results = []
        for r in rows:
            try:
                results.append(json.loads(r["report_json"]))
            except Exception as e:
                logger.warning(f"Error parsing stored pipeline report JSON: {e}")
        return results

    def close(self) -> None:
        """Close SQLite database connection."""
        if self._conn:
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
