"""Mock LLM client for deterministic unit testing, local demos, and offline modes."""

import json
from typing import Any, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel
from dailyai.logging_config import get_logger
from dailyai.services.llm.base import BaseLLMClient

logger = get_logger("llm.mock")

T = TypeVar("T", bound=BaseModel)


class MockLLMClient(BaseLLMClient):
    """Deterministic Mock LLM client for test suites and offline execution."""

    def __init__(self, canned_responses: Optional[Dict[str, Any]] = None):
        self.canned_responses = canned_responses or {}
        logger.info("Initialized Mock LLM client (offline / test mode).")

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        """Return deterministic mock response text."""
        prompt_lower = prompt.lower()
        if "subject" in prompt_lower or "newsletter title" in prompt_lower:
            return "DailyAI Intelligence Brief: Breakthroughs in LLM Reasoning, Critical Zero-Day Patching, and 5G-V2X Rollouts"
        if "section summary" in prompt_lower or "executive summary" in prompt_lower:
            return "Key developments highlight major performance optimizations, high-severity CVE mitigations, and cross-border V2X interoperability."
        return "Mock generated synthesis based on authoritative technical reporting."

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_instruction: Optional[str] = None,
        temperature: float = 0.1,
    ) -> T:
        """Return structured mock model conforming to response_model."""
        schema_name = response_model.__name__
        logger.debug(f"MockLLM generate_structured for {schema_name}")

        prompt_lower = prompt.lower()

        # Handle ArticleDraft synthesis
        if "draft" in schema_name.lower() or "articledraft" in schema_name.lower():
            title = "Major Technical Breakthrough Announced in Domain Architecture"
            source_name = "Authoritative Technical Press"
            source_url = "https://example.com/authoritative-report"
            domain = "ai"
            snippet = ""

            for line in prompt.split("\n"):
                if "domain 'ai'" in line.lower():
                    domain = "ai"
                elif "domain 'cybersecurity'" in line.lower():
                    domain = "cybersecurity"
                elif "domain 'v2x'" in line.lower():
                    domain = "v2x"
                elif line.startswith("Raw Title:"):
                    title = line.replace("Raw Title:", "").strip()
                elif line.startswith("Reported Source:"):
                    source_name = line.replace("Reported Source:", "").strip()
                elif line.startswith("Source URL:"):
                    source_url = line.replace("Source URL:", "").strip()

            summary = f"Authoritative technical reporting from {source_name} on recent developments in {domain.upper()}."

            mock_data = {
                "id": "draft-mock-001",
                "domain": domain,
                "title": title,
                "summary": summary,
                "key_points": [
                    "Empirical validation conducted under standardized test benchmarks.",
                    "Complies with latest industry security and safety protocols.",
                    "Full documentation and reproducibility artifacts published."
                ],
                "facts": [
                    f"Validated by {source_name} under formal technical testing.",
                    "Deployment and reference implementations verified."
                ],
                "opinions_or_speculation": [
                    "Market analysts project accelerated commercial adoption."
                ] if "speculative" in prompt_lower else [],
                "source_url": source_url,
                "original_source_name": source_name,
                "original_source_url": source_url,
                "published_date": "2026-08-17",
                "relevance_score": 0.92,
                "entities_mentioned": ["TechCorp", "StandardBody"],
                "cve_identifiers": ["CVE-2026-2189"] if domain == "cybersecurity" else [],
                "standards_mentioned": ["3GPP Rel-18", "ISO 26262"] if domain == "v2x" else [],
            }
            return response_model.model_validate(mock_data)

        # Handle VerificationResult
        if "verification" in schema_name.lower():
            # Check if prompt explicitly flags test rejection or test caveat
            is_rejected = "test_reject" in prompt_lower or "bogus_unsupported_claim" in prompt_lower
            is_caveat = "early stage" in prompt_lower or "speculative" in prompt_lower or "rumor" in prompt_lower

            if is_rejected:
                status = "REJECTED"
                conf = 0.25
                rejection = "Claims could not be corroborated against primary source registries."
            elif is_caveat:
                status = "VERIFIED_WITH_CAVEATS"
                conf = 0.78
                rejection = None
            else:
                status = "VERIFIED"
                conf = 0.94
                rejection = None

            mock_data = {
                "status": status,
                "confidence_score": conf,
                "claims_checked": [
                    {
                        "claim": "The reported performance figures and implementation details are accurate.",
                        "status": "VERIFIED" if not is_rejected else "UNVERIFIED",
                        "reasoning": "Corroborated against official technical disclosures.",
                        "cross_references": ["https://cisa.gov/advisory", "https://arxiv.org/abs/2608.12345"],
                    }
                ],
                "hallucinations_detected": ["Unsupported timeline extrapolation"] if is_caveat else [],
                "technical_terms_verified": ["Transformer", "3GPP C-V2X", "CVE-2026-2189"],
                "cve_validation_notes": "CVE identifier matches standard format and vendor disclosure." if "cve" in prompt_lower else None,
                "standards_validation_notes": "Standards reference accurately conforms to official release notes." if "v2x" in prompt_lower else None,
                "rejection_reason": rejection,
                "quality_score": 0.9,
                "cross_check_sources": ["https://nvd.nist.gov", "https://5gaa.org"],
            }
            return response_model.model_validate(mock_data)

        # Generic fallback for any other Pydantic schema
        try:
            return response_model.model_construct()
        except Exception:
            return response_model.model_validate({})
