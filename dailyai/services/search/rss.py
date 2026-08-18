"""Curated RSS feeds aggregator for authoritative domain intelligence."""

from datetime import datetime, timezone, timedelta
import email.utils
import time
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
import feedparser

from dailyai.logging_config import get_logger
from dailyai.models.article import DomainType, RawSourceItem

logger = get_logger("search.rss")

# Curated high-authority RSS feeds per domain
CURATED_RSS_FEEDS: Dict[DomainType, List[Dict[str, str]]] = {
    DomainType.AI: [
        {"name": "arXiv Computer Science AI", "url": "https://export.arxiv.org/rss/cs.AI"},
        {"name": "arXiv Machine Learning", "url": "https://export.arxiv.org/rss/cs.LG"},
        {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/"},
        {"name": "MIT Technology Review AI", "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed"},
        {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    ],
    DomainType.CYBERSECURITY: [
        {"name": "CISA Cybersecurity Advisories", "url": "https://www.cisa.gov/cybersecurity-advisories/all.xml"},
        {"name": "The Hacker News", "url": "https://feeds.feedburner.com/TheHackersNews"},
        {"name": "BleepingComputer", "url": "https://www.bleepingcomputer.com/feed/"},
        {"name": "SecurityWeek", "url": "https://www.securityweek.com/feed/"},
        {"name": "Dark Reading", "url": "https://www.darkreading.com/rss.xml"},
    ],
    DomainType.V2X: [
        {"name": "Autonomous Vehicle International", "url": "https://www.autonomousvehicleinternational.com/feed"},
        {"name": "Telematics Wire", "url": "https://www.telematicswire.net/feed/"},
        {"name": "Connected Car News", "url": "https://connectedcar-news.com/feed/"},
        {"name": "IEEE Spectrum Transportation", "url": "https://spectrum.ieee.org/rss/topic/transportation"},
        {"name": "SAE International Mobility", "url": "https://www.sae.org/news/rss"},
    ],
}


def parse_feed_date(entry: feedparser.FeedParserDict) -> Optional[datetime]:
    """Extract and parse publication date from feed entry."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime.fromtimestamp(time.mktime(entry.published_parsed), tz=timezone.utc)
        except Exception:
            pass

    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        try:
            return datetime.fromtimestamp(time.mktime(entry.updated_parsed), tz=timezone.utc)
        except Exception:
            pass

    if hasattr(entry, "published") and entry.published:
        try:
            parsed_tuple = email.utils.parsedate_to_datetime(entry.published)
            return parsed_tuple.astimezone(timezone.utc)
        except Exception:
            pass

    return None


def clean_html_summary(html_text: str) -> str:
    """Strip HTML markup from RSS summary/description."""
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text(separator=" ")
    return " ".join(text.split())


class RSSFeedAggregator:
    """Fetches and parses authoritative RSS feeds for each technology domain."""

    def __init__(self, custom_feeds: Optional[Dict[DomainType, List[Dict[str, str]]]] = None):
        self.feeds = custom_feeds or CURATED_RSS_FEEDS

    def fetch_domain_feeds(
        self,
        domain: DomainType,
        max_items_per_feed: int = 4,
        lookback_hours: int = 24,
    ) -> List[RawSourceItem]:
        """Fetch and filter recent entries from domain feeds."""
        items: List[RawSourceItem] = []
        feed_sources = self.feeds.get(domain, [])
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

        for feed_info in feed_sources:
            feed_name = feed_info["name"]
            feed_url = feed_info["url"]

            try:
                # Use feedparser with timeout / user-agent
                parsed = feedparser.parse(feed_url)
                if parsed.bozo and not parsed.entries:
                    logger.debug(f"RSS feed '{feed_name}' parse warning: {parsed.bozo_exception}")
                    continue

                count = 0
                for entry in parsed.entries:
                    if count >= max_items_per_feed:
                        break

                    title = entry.get("title", "").strip()
                    link = entry.get("link", "").strip()
                    summary = clean_html_summary(entry.get("summary", entry.get("description", "")))
                    pub_dt = parse_feed_date(entry)

                    # Filter out entries older than lookback_hours if date is available
                    if pub_dt and pub_dt < cutoff_time:
                        continue

                    if title and link:
                        items.append(
                            RawSourceItem(
                                title=title,
                                url=link,
                                snippet=summary[:800],
                                source_name=feed_name,
                                published_at=pub_dt.strftime("%Y-%m-%d %H:%M:%S") if pub_dt else None,
                                domain=domain,
                                raw_metadata={"source_type": "rss", "feed_url": feed_url},
                            )
                        )
                        count += 1

                logger.info(f"RSS feed '{feed_name}' ingested {count} recent items.")
            except Exception as e:
                logger.warning(f"Failed to fetch RSS feed '{feed_name}' ({feed_url}): {e}")

        return items
