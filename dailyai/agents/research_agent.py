"""Agent 1 — Research & Intelligence Agent.

Collects, deduplicates, and synthesizes the latest authoritative news and technical
developments in Artificial Intelligence, Cybersecurity, and V2X technologies.
"""

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
import uuid

from dailyai.agents.base import BaseAgent
from dailyai.config import Settings, get_settings
from dailyai.models.article import ArticleDraft, DomainType, RawSourceItem
from dailyai.services.llm.base import BaseLLMClient
from dailyai.services.llm.factory import get_llm_client
from dailyai.services.search.base import BaseSearchEngine
from dailyai.services.search.factory import get_search_engine
from dailyai.services.search.rss import RSSFeedAggregator
from dailyai.services.storage.base import BaseDeduplicationStore
from dailyai.services.storage.sqlite import SQLiteDeduplicationStore
from dailyai.temporal import (
    Clock,
    DateEvaluation,
    evaluate_publication_date,
    is_article_outdated,
    utc_now,
)


# Domain-specific search query templates for discovering recent authoritative developments
DOMAIN_SEARCH_QUERIES: Dict[DomainType, List[str]] = {
    DomainType.AI: [
        "latest artificial intelligence model release announcements",
        "new LLM reasoning benchmark research papers",
        "open source AI weights release",
        "autonomous AI agent safety framework breakthrough",
    ],
    DomainType.CYBERSECURITY: [
        "latest cybersecurity vulnerability CVE zero-day advisory",
        "CISA security advisory KEV catalog update",
        "critical software patch security bulletin exploit",
        "post-quantum cryptography standards research",
    ],
    DomainType.V2X: [
        "latest C-V2X 5G-V2X connected vehicle technology standard",
        "autonomous driving V2X roadside unit deployment 5GAA",
        "ISO SAE 21434 vehicle cybersecurity updates",
        "vehicle-to-everything intelligent transportation news",
    ],
}


class ResearchAgent(BaseAgent[Optional[Dict[str, Any]], List[ArticleDraft]]):
    """Agent 1: Discovers, gathers, filters, and synthesizes authoritative news drafts."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        llm_client: Optional[BaseLLMClient] = None,
        search_engine: Optional[BaseSearchEngine] = None,
        rss_aggregator: Optional[RSSFeedAggregator] = None,
        storage: Optional[BaseDeduplicationStore] = None,
        clock: Optional[Clock] = None,
    ):
        super().__init__(name="Agent 1 — Research & Intelligence")
        self.settings = settings or get_settings()
        self.llm = llm_client or get_llm_client(self.settings)
        self.search_engine = search_engine or get_search_engine(self.settings)
        self.rss = rss_aggregator or (RSSFeedAggregator() if self.settings.enable_rss_feeds else None)
        self.storage = storage or SQLiteDeduplicationStore(self.settings.database_path)
        self._now: Clock = clock or utc_now
        self.last_quarantined_items: List[Dict[str, Any]] = []

    def is_article_outdated(
        self,
        date_str: Optional[str],
        lookback_hours: Optional[int] = None,
        buffer_days: int = 2,
        now: Optional[datetime] = None,
        strict_mode: Optional[bool] = None,
    ) -> bool:
        """Evaluate whether a publication date fails this agent's freshness gate."""
        return is_article_outdated(
            date_str=date_str,
            lookback_hours=lookback_hours if lookback_hours is not None else self.settings.lookback_hours,
            buffer_days=buffer_days,
            now=now if now is not None else self._now(),
            strict_mode=self.settings.fact_check_strict_mode if strict_mode is None else strict_mode,
        )

    def _gather_raw_items_for_domain(self, domain: DomainType) -> List[RawSourceItem]:
        """Aggregate raw intelligence from Web Search queries and RSS feeds."""
        raw_items: List[RawSourceItem] = []
        seen_batch_urls = set()

        # 1. Ingest RSS Feeds (High-authority direct feeds)
        if self.rss and self.settings.enable_rss_feeds:
            try:
                rss_items = self.rss.fetch_domain_feeds(
                    domain=domain,
                    max_items_per_feed=2,
                    lookback_hours=self.settings.lookback_hours,
                )
                for item in rss_items:
                    if item.url not in seen_batch_urls:
                        seen_batch_urls.add(item.url)
                        raw_items.append(item)
            except Exception as e:
                warn_msg = f"Error gathering RSS feeds for domain {domain.value}: {e}"
                self.logger.warning(warn_msg)
                self._run_warnings.append(warn_msg)

        # 2. Ingest Web Search Hits
        queries = DOMAIN_SEARCH_QUERIES.get(domain, [])[: self.settings.search_queries_per_category]
        for query in queries:
            try:
                hits = self.search_engine.search(
                    query=query,
                    domain=domain,
                    max_results=self.settings.max_search_results_per_query,
                    lookback_hours=self.settings.lookback_hours,
                )
                for hit in hits:
                    if hit.url not in seen_batch_urls:
                        seen_batch_urls.add(hit.url)
                        raw_items.append(hit)
            except Exception as e:
                warn_msg = f"Error querying search engine for '{query}': {e}"
                self.logger.warning(warn_msg)
                self._run_warnings.append(warn_msg)

        self.logger.info(f"Gathered {len(raw_items)} candidate raw items for domain '{domain.value}'")
        return raw_items

    def _filter_and_deduplicate(self, raw_items: List[RawSourceItem]) -> List[RawSourceItem]:
        """Filter out already-seen URLs, duplicate titles, and low-quality items."""
        valid_items: List[RawSourceItem] = []
        seen_urls_in_filter = set()

        for item in raw_items:
            norm_url = item.url.strip().lower().rstrip("/")
            if norm_url in seen_urls_in_filter:
                continue
            seen_urls_in_filter.add(norm_url)

            # Check persistent store for URL and title (skipped in dry_run mode)
            if not self.settings.dry_run:
                if self.storage.is_url_processed(item.url):
                    self.logger.debug(f"Skipping already processed URL: {item.url}")
                    continue

                if self.storage.is_title_duplicate(item.title):
                    self.logger.debug(f"Skipping near-duplicate title: {item.title}")
                    continue

            # Evaluate publication date strictly (fail closed in strict mode; flag unverified in non-strict mode)
            date_eval: DateEvaluation = evaluate_publication_date(
                date_str=item.published_at,
                lookback_hours=self.settings.lookback_hours,
                now=self._now(),
            )
            if date_eval.should_reject(strict_mode=self.settings.fact_check_strict_mode):
                self.logger.warning(
                    f"Quarantining raw item '{item.title}' ({date_eval.status.value}): {date_eval.reason}"
                )
                self.last_quarantined_items.append(
                    {
                        "stage": "research",
                        "title": item.title,
                        "url": item.url,
                        "domain": item.domain.value,
                        "published_at": item.published_at,
                        "status": date_eval.status.value,
                        "reason": date_eval.reason,
                    }
                )
                continue

            if date_eval.date_unverified:
                item = item.model_copy(update={"date_unverified": True})

            # Basic quality filter: ignore very short snippets or spam titles
            if len(item.title.strip()) < 10:
                continue

            valid_items.append(item)

        self.logger.info(f"Retained {len(valid_items)} novel items after deduplication & filtering.")
        return valid_items

    def _synthesize_draft(self, raw_item: RawSourceItem) -> Optional[ArticleDraft]:
        """Use LLM to extract structured facts, key takeaways, and metadata."""
        now = self._now()
        today_str = now.strftime("%Y-%m-%d")

        prompt = f"""
You are the Research & Intelligence Agent for a daily technology intelligence briefing.
Analyze the following raw technical news item from domain '{raw_item.domain.value}'.

TEMPORAL CONTEXT:
- Today's Date: {today_str} (Year {now.year})
- Current articles up to {today_str} are contemporary and recent.

Raw Title: {raw_item.title}
Reported Source: {raw_item.source_name}
Source URL: {raw_item.url}
Reported Date: {raw_item.published_at or 'Unknown / Unverified'}
Content / Snippet:
{raw_item.snippet}

YOUR OBJECTIVES:
1. Identify the original source organization or publisher (e.g. CISA, NIST, arXiv, OpenAI, Qualcomm, SAE).
2. Extract the actual publication date in YYYY-MM-DD format (dates up to {today_str} in {now.year} are contemporary).
3. Produce a clear, highly factual, concise summary of the recent development (2-3 sentences).
4. Extract 2-4 key highlight bullet points.
5. Extract explicit factual assertions (e.g., benchmark numbers, CVE numbers, standards, releases).
6. Explicitly isolate any speculative claims, marketing hype, or unverified opinions into 'opinions_or_speculation'.
7. Extract relevant CVE identifiers (if security related) and technical standards (e.g. 3GPP Rel-18, ISO 26262, NIST FIPS).
8. Do not invent or hallucinate any facts not substantiated by the source text.
"""
        system_instruction = (
            "You are an expert technical intelligence analyst specializing in AI, Cybersecurity, and V2X. "
            "You prioritize empirical facts, technical accuracy, and source attribution. "
            "You strictly separate verified facts from speculative assertions."
        )

        try:
            draft = self.llm.generate_structured(
                prompt=prompt,
                response_model=ArticleDraft,
                system_instruction=system_instruction,
                temperature=0.1,
            )
            # Ensure identifiers and canonical URLs are cleanly set
            draft.id = f"draft-{uuid.uuid4().hex[:8]}"
            draft.domain = raw_item.domain
            draft.source_url = raw_item.url
            if not draft.original_source_name or draft.original_source_name == "Unknown":
                draft.original_source_name = raw_item.source_name
            if raw_item.updated_at and not draft.updated_date:
                draft.updated_date = raw_item.updated_at.split()[0]
            if raw_item.event_date and not draft.event_date:
                draft.event_date = raw_item.event_date
            if raw_item.date_unverified:
                draft.date_unverified = True
                draft.published_date = raw_item.published_at
            elif raw_item.published_at and not draft.published_date:
                draft.published_date = raw_item.published_at.split()[0]

            return draft
        except Exception as e:
            self.logger.warning(f"LLM synthesis failed for item '{raw_item.title}': {e}")
            # Resilient fallback: build basic draft directly from raw item without failing
            return ArticleDraft(
                id=f"draft-{uuid.uuid4().hex[:8]}",
                domain=raw_item.domain,
                title=raw_item.title,
                summary=raw_item.snippet[:300] if raw_item.snippet else raw_item.title,
                key_points=[raw_item.snippet[:150]] if raw_item.snippet else [],
                facts=[raw_item.title],
                opinions_or_speculation=[],
                source_url=raw_item.url,
                original_source_name=raw_item.source_name,
                published_date=(
                    raw_item.published_at
                    if raw_item.date_unverified
                    else (raw_item.published_at.split()[0] if raw_item.published_at else None)
                ),
                updated_date=raw_item.updated_at.split()[0] if raw_item.updated_at else None,
                event_date=raw_item.event_date,
                date_unverified=raw_item.date_unverified,
                relevance_score=0.75,
            )

    def _run(self, input_data: Optional[Dict[str, Any]] = None) -> List[ArticleDraft]:
        """Execute complete research and intelligence collection across all domains."""
        all_drafts: List[ArticleDraft] = []
        self.last_quarantined_items = []
        domains_to_process = [DomainType.AI, DomainType.CYBERSECURITY, DomainType.V2X]

        for domain in domains_to_process:
            self.logger.info(f"Processing domain intelligence: {domain.display_name}")
            raw_items = self._gather_raw_items_for_domain(domain)
            filtered_items = self._filter_and_deduplicate(raw_items)

            # Limit number of candidate drafts to synthesize per domain
            max_candidates = max(self.settings.max_articles_per_category * 2, 6)
            domain_drafts: List[ArticleDraft] = []

            for item in filtered_items[:max_candidates]:
                draft = self._synthesize_draft(item)
                if draft:
                    domain_drafts.append(draft)
                    # Persist only after successful publication; failed or rejected drafts remain retryable.

            self.logger.info(f"Domain '{domain.value}' synthesized {len(domain_drafts)} research drafts.")
            all_drafts.extend(domain_drafts)

        self._run_metadata["quarantined_count"] = str(len(self.last_quarantined_items))
        self._run_metadata["date_unverified_count"] = str(sum(1 for d in all_drafts if d.date_unverified))
        self.logger.info(f"Agent 1 produced a total of {len(all_drafts)} research drafts.")
        return all_drafts
