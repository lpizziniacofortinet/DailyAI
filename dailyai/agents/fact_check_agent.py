from datetime import datetime, timezone, timedelta
import re
from typing import Dict, List, Optional
from dateutil import parser as date_parser

from dailyai.agents.base import BaseAgent
from dailyai.config import Settings, get_settings
from dailyai.models.article import ArticleDraft, DomainType
from dailyai.models.fact_check import (
    ClaimCheck,
    VerificationResult,
    VerificationStatus,
    VerifiedArticle,
)
from dailyai.services.llm.base import BaseLLMClient
from dailyai.services.llm.factory import get_llm_client
from dailyai.services.search.base import BaseSearchEngine
from dailyai.services.search.factory import get_search_engine


def is_article_outdated(date_str: Optional[str], lookback_hours: int, buffer_days: int = 2) -> bool:
    """Return True if publication date is older than lookback window + buffer."""
    if not date_str:
        return False
    try:
        parsed = date_parser.parse(date_str)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        max_age = timedelta(hours=lookback_hours + (buffer_days * 24))
        cutoff = now - max_age
        return parsed < cutoff
    except Exception:
        return False


CVE_REGEX = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)
STANDARD_REGEX = re.compile(
    r"\b(3GPP\s+Rel(?:ease)?\s*\d+|IEEE\s+802\.\d+[a-z]*|ISO(?:/SAE)?\s+\d+|NIST\s+SP\s+\d+|FIPS\s+\d+)\b",
    re.IGNORECASE,
)


class FactCheckAgent(BaseAgent[List[ArticleDraft], List[VerifiedArticle]]):
    """Agent 2: Independent Fact-Checking, Hallucination Detection, and Quality Gating."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        llm_client: Optional[BaseLLMClient] = None,
        search_engine: Optional[BaseSearchEngine] = None,
    ):
        super().__init__(name="Agent 2 — Fact-Checking & Quality Gate")
        self.settings = settings or get_settings()
        self.llm = llm_client or get_llm_client(self.settings)
        self.search_engine = search_engine or get_search_engine(self.settings)

    def _validate_technical_identifiers(self, draft: ArticleDraft) -> Dict[str, Optional[str]]:
        """Validate format of CVEs and technical standards."""
        notes: Dict[str, Optional[str]] = {
            "cve": None,
            "standards": None,
        }

        # Check CVEs
        if draft.cve_identifiers:
            valid_cves = [cve for cve in draft.cve_identifiers if CVE_REGEX.match(cve.strip())]
            if len(valid_cves) == len(draft.cve_identifiers):
                notes["cve"] = f"Valid standard CVE format confirmed: {', '.join(valid_cves)}"
            else:
                notes["cve"] = f"Warning: Some CVE identifiers failed standard format verification: {draft.cve_identifiers}"

        # Check Standards
        if draft.standards_mentioned:
            matched_standards = []
            for std in draft.standards_mentioned:
                if STANDARD_REGEX.search(std):
                    matched_standards.append(std)
            if matched_standards:
                notes["standards"] = f"Standards referenced match formal naming schemes: {', '.join(matched_standards)}"

        return notes

    def _cross_check_and_verify(self, draft: ArticleDraft) -> VerificationResult:
        """Independently verify claims made in the research draft using LLM & heuristics."""
        # 1. Deterministic date gate. Unknown dates are not evidence of freshness.
        if self.settings.fact_check_strict_mode and not draft.published_date:
            return VerificationResult(
                status=VerificationStatus.INSUFFICIENT_EVIDENCE,
                confidence_score=0.0,
                claims_checked=[],
                hallucinations_detected=[],
                technical_terms_verified=[],
                rejection_reason="Publication date is missing; strict mode requires a verifiable date.",
                quality_score=0.0,
                cross_check_sources=[],
            )
        if draft.published_date:
            try:
                parsed_date = date_parser.parse(draft.published_date)
                if parsed_date.tzinfo is None:
                    parsed_date = parsed_date.replace(tzinfo=timezone.utc)
                if parsed_date > datetime.now(timezone.utc) + timedelta(hours=24):
                    return VerificationResult(
                        status=VerificationStatus.INSUFFICIENT_EVIDENCE,
                        confidence_score=0.0,
                        claims_checked=[],
                        hallucinations_detected=[],
                        technical_terms_verified=[],
                        rejection_reason="Publication date is unexpectedly in the future.",
                        quality_score=0.0,
                        cross_check_sources=[],
                    )
            except (ValueError, TypeError, OverflowError):
                if self.settings.fact_check_strict_mode:
                    return VerificationResult(
                        status=VerificationStatus.INSUFFICIENT_EVIDENCE,
                        confidence_score=0.0,
                        claims_checked=[],
                        hallucinations_detected=[],
                        technical_terms_verified=[],
                        rejection_reason="Publication date is malformed and cannot be verified.",
                        quality_score=0.0,
                        cross_check_sources=[],
                    )
            if is_article_outdated(draft.published_date, self.settings.lookback_hours):
                self.logger.warning(
                    f"Rejecting outdated article: '{draft.title}' (Published: {draft.published_date}, lookback: {self.settings.lookback_hours}h)"
                )
                return VerificationResult(
                    status=VerificationStatus.REJECTED,
                    confidence_score=0.1,
                    claims_checked=[],
                    hallucinations_detected=[],
                    technical_terms_verified=[],
                    rejection_reason=f"Article published on {draft.published_date} is too old (freshness window: {self.settings.lookback_hours} hours).",
                    quality_score=0.2,
                    cross_check_sources=[],
                )

        tech_notes = self._validate_technical_identifiers(draft)

        now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        earliest_dt = now - timedelta(hours=self.settings.lookback_hours + 48)
        earliest_str = earliest_dt.strftime("%Y-%m-%d")

        prompt = f"""
You are an uncompromising Fact-Checking & Quality Verification Agent for technical intelligence.
Your task is to independently evaluate the following research draft. Never assume the draft is accurate.

TEMPORAL CONTEXT:
- Today's Date: {today_str} (Year {now.year})
- Configured Lookback Window: Past {self.settings.lookback_hours} hours (articles published from {earliest_str} to {today_str} are fully valid and considered recent).
- Note: Dates up to {today_str} in {now.year} are NOT future dates; they are current/recent.

DOMAIN: {draft.domain.value}
HEADLINE: {draft.title}
REPORTED SOURCE: {draft.original_source_name} ({draft.source_url})
REPORTED DATE: {draft.published_date or 'Recent'}
SUMMARY: {draft.summary}
KEY POINTS:
{chr(10).join('- ' + pt for pt in draft.key_points)}
CLAIMED FACTS:
{chr(10).join('- ' + f for f in draft.facts)}
SPECULATION / OPINIONS FLAGGED:
{chr(10).join('- ' + o for o in draft.opinions_or_speculation)}
ENTITIES / CVES / STANDARDS:
- Entities: {', '.join(draft.entities_mentioned)}
- CVEs: {', '.join(draft.cve_identifiers)}
- Standards: {', '.join(draft.standards_mentioned)}

EVALUATION CRITERIA:
1. Plausibility & Technical Accuracy: Are the technical terms, architectures, and performance metrics feasible and consistent with current state-of-the-art in {draft.domain.value}?
2. Freshness & Recency: Today is {today_str}. Any date between {earliest_str} and {today_str} is valid and NOT in the future. If the article is from a prior archival period older than {earliest_str}, mark status as REJECTED.
3. Hallucination Detection: Are there any fabricated metrics, exaggerated claims, or impossible timelines?
4. Source Trustworthiness: Is the reported source known and reputable?
5. Quality Score: Rate technical clarity and utility from 0.0 to 1.0.
6. Confidence Score: Assign a factual confidence score between 0.0 and 1.0.
7. Status:
   - VERIFIED: High confidence (>=0.80), substantiated claims, authoritative recent topic.
   - VERIFIED_WITH_CAVEATS: Acceptable (0.70-0.79), but contains early stage research, rumors, or unverified vendor claims.
   - REJECTED: Low confidence (<0.70), genuinely outdated news, obvious hallucinations, sensational clickbait, or uncorroborated rumors.
"""
        system_instruction = (
            "You are a rigorous scientific and cybersecurity fact-checker. "
            "You reject hype, buzzwords, and unsubstantiated claims. "
            "You enforce high standards for technical accuracy and clear attribution."
        )

        try:
            verification = self.llm.generate_structured(
                prompt=prompt,
                response_model=VerificationResult,
                system_instruction=system_instruction,
                temperature=0.0,
            )
            # Inject deterministic technical identifier notes
            if tech_notes["cve"]:
                verification.cve_validation_notes = tech_notes["cve"]
            if tech_notes["standards"]:
                verification.standards_validation_notes = tech_notes["standards"]
            return verification

        except Exception as e:
            self.logger.warning(
                "Verification provider failed for '%s'; refusing automatic approval: %s",
                draft.title,
                e,
            )
            # Fail closed: a provider outage is not evidence that a claim is true.
            return VerificationResult(
                status=VerificationStatus.INSUFFICIENT_EVIDENCE,
                confidence_score=0.0,
                claims_checked=[
                    ClaimCheck(
                        claim=draft.title,
                        status="UNVERIFIED",
                        reasoning=(
                            "Automated verification could not be completed because "
                            "the verification provider failed. No approval was granted."
                        ),
                        cross_references=[],
                    )
                ],
                hallucinations_detected=[],
                technical_terms_verified=[],
                cve_validation_notes=tech_notes["cve"],
                standards_validation_notes=tech_notes["standards"],
                rejection_reason=(
                    "Verification unavailable: the LLM provider failed. "
                    "Retry the fact-check before considering publication."
                ),
                quality_score=0.0,
                cross_check_sources=[],
            )

    def _generate_verified_article(
        self,
        draft: ArticleDraft,
        verification: VerificationResult,
    ) -> VerifiedArticle:
        """Create verified article with polished headline and impact analysis."""
        # Clean headline and remove sensationalism if any
        clean_headline = draft.title.strip()
        # Compile caveats
        caveats = list(draft.opinions_or_speculation)
        if verification.hallucinations_detected:
            caveats.extend([f"Caveat: {h}" for h in verification.hallucinations_detected])

        # Impact analysis synthesis
        impact_prompt = f"""
Provide a concise, 1-2 sentence explanation of 'Why this matters' (impact analysis) for domain '{draft.domain.value}'.
Headline: {clean_headline}
Summary: {draft.summary}
Key points: {', '.join(draft.key_points)}
"""
        try:
            impact_analysis = self.llm.generate_text(
                prompt=impact_prompt,
                system_instruction="Be succinct, practical, and focus on industry or operational impact.",
                temperature=0.2,
            ).strip()
        except Exception:
            impact_analysis = f"Significantly advances development and operational standards in {draft.domain.display_name}."

        is_approved = (
            verification.status in [VerificationStatus.VERIFIED, VerificationStatus.VERIFIED_WITH_CAVEATS]
            and verification.confidence_score >= self.settings.min_confidence_score
        )

        return VerifiedArticle(
            draft=draft,
            verification=verification,
            final_headline=clean_headline,
            final_summary=draft.summary,
            impact_analysis=impact_analysis,
            caveats_and_uncertainty=caveats,
            is_approved=is_approved,
        )

    def _run(self, input_data: List[ArticleDraft]) -> List[VerifiedArticle]:
        """Execute independent verification, filtering, and ranking of all drafts."""
        if not input_data:
            self.logger.warning("No drafts received from Agent 1. Returning empty verified list.")
            return []

        verified_articles: List[VerifiedArticle] = []
        approved_count = 0
        rejected_count = 0

        for draft in input_data:
            self.logger.info(f"Fact-checking draft: '{draft.title}' ({draft.domain.value})")
            verification = self._cross_check_and_verify(draft)
            verified_article = self._generate_verified_article(draft, verification)

            if verified_article.is_approved:
                approved_count += 1
                verified_articles.append(verified_article)
                self.logger.info(
                    f"✓ APPROVED: '{draft.title}' (Confidence: {verification.confidence_score:.2f}, Status: {verification.status.value})"
                )
            else:
                rejected_count += 1
                self.logger.warning(
                    f"✗ REJECTED: '{draft.title}' (Confidence: {verification.confidence_score:.2f}, Reason: {verification.rejection_reason or 'Failed confidence threshold'})"
                )

        # Rank approved articles within each domain by confidence score & quality
        domains = [DomainType.AI, DomainType.CYBERSECURITY, DomainType.V2X]
        final_ranked_list: List[VerifiedArticle] = []

        for domain in domains:
            domain_articles = [a for a in verified_articles if a.domain == domain]
            # Sort by composite score (confidence_score * 0.6 + quality_score * 0.4) descending
            domain_articles.sort(
                key=lambda a: (a.verification.confidence_score * 0.6 + a.verification.quality_score * 0.4),
                reverse=True,
            )

            # Assign priority ranks
            for rank_idx, article in enumerate(domain_articles, start=1):
                article.relevance_rank = rank_idx

            # Limit to max_articles_per_category
            selected = domain_articles[: self.settings.max_articles_per_category]
            final_ranked_list.extend(selected)

        self.logger.info(
            f"Agent 2 completed verification: {approved_count} approved, {rejected_count} rejected. "
            f"Retained {len(final_ranked_list)} top-ranked articles for publication."
        )
        return final_ranked_list
