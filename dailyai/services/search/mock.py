"""Deterministic mock search engine for testing and offline execution."""

from typing import Dict, List
from dailyai.logging_config import get_logger
from dailyai.models.article import DomainType, RawSourceItem
from dailyai.services.search.base import BaseSearchEngine

logger = get_logger("search.mock")

MOCK_SOURCE_DATA: Dict[DomainType, List[Dict[str, str]]] = {
    DomainType.AI: [
        {
            "title": "DeepSeek Releases Open Weights for DeepSeek-R2 Reasoning Model",
            "url": "https://arxiv.org/abs/2608.10982",
            "snippet": "Researchers introduce a new distilled reasoning architecture with native multimodality, achieving 94.2% on Math-500 benchmarks with 60% lower inference latency.",
            "source_name": "arXiv CS.AI",
            "published_at": "2026-08-17 08:30:00",
        },
        {
            "title": "Anthropic Unveils Constitutional Guardrails for Autonomous Coding Agents",
            "url": "https://anthropic.com/news/agent-constitutional-guardrails",
            "snippet": "New real-time policy evaluation hooks enforce safety bounds and sandbox boundaries on autonomous software engineering agents without degrading task completion rates.",
            "source_name": "Anthropic Research",
            "published_at": "2026-08-17 09:15:00",
        },
        {
            "title": "PyTorch 2.5 Introduces Next-Gen FlashAttention-4 and Distributed Quantization",
            "url": "https://pytorch.org/blog/pytorch-2-5-release",
            "snippet": "The PyTorch foundation announces stable support for sub-byte quantization and micro-kernel compilation, reducing LLM memory footprint across modern GPU architectures.",
            "source_name": "PyTorch Blog",
            "published_at": "2026-08-17 11:00:00",
        },
    ],
    DomainType.CYBERSECURITY: [
        {
            "title": "CISA Adds Critical Linux Kernel eBPF Privilege Escalation Flaw (CVE-2026-2189) to KEV Catalog",
            "url": "https://www.cisa.gov/news-events/cybersecurity-advisories/aa26-229a",
            "snippet": "CISA issues emergency directive warning of active in-the-wild exploitation of CVE-2026-2189 allowing root escalation in containerized cloud environments.",
            "source_name": "CISA Advisories",
            "published_at": "2026-08-17 07:45:00",
        },
        {
            "title": "Post-Quantum Cryptography: NIST Finalizes FIPS Standards for Key Encapsulation",
            "url": "https://csrc.nist.gov/publications/detail/fips/203/final",
            "snippet": "NIST officially standardizes ML-KEM and ML-DSA post-quantum cryptographic primitives, urging global infrastructure operators to begin migration from RSA and ECC.",
            "source_name": "NIST News",
            "published_at": "2026-08-17 10:20:00",
        },
        {
            "title": "Sophisticated Supply Chain Attack Compromises 40+ NPM Packages via Stolen Maintainer Tokens",
            "url": "https://thehackernews.com/2026/08/npm-supply-chain-attack.html",
            "snippet": "Security researchers uncover malicious payloads injected into popular build pipeline libraries designed to exfiltrate AWS and Kubernetes cluster secrets.",
            "source_name": "The Hacker News",
            "published_at": "2026-08-17 12:10:00",
        },
    ],
    DomainType.V2X: [
        {
            "title": "5GAA and Qualcomm Validate 3GPP Release 18 C-V2X Direct Communications for Vulnerable Road Users",
            "url": "https://5gaa.org/news/release-18-cv2x-vru-validation",
            "snippet": "Field trials demonstrate direct sidelink communication between connected vehicles and pedestrian smartphones, achieving sub-10ms emergency braking warning latency.",
            "source_name": "5G Automotive Association",
            "published_at": "2026-08-17 08:00:00",
        },
        {
            "title": "USDOT Finalizes National V2X Deployment Plan Mandating Interoperable Cross-State Infrastructure",
            "url": "https://transportation.gov/briefing-room/usdot-v2x-national-interoperability-plan",
            "snippet": "Federal highway administrators allocate $120M in grants to deploy dual-mode cellular and DSRC roadside units (RSUs) across interstate freight corridors.",
            "source_name": "USDOT News",
            "published_at": "2026-08-17 09:40:00",
        },
        {
            "title": "ISO and SAE Publish Revised Cybersecurity Engineering Standard ISO/SAE 21434:2026 for Connected Fleets",
            "url": "https://www.sae.org/standards/content/iso_sae_21434_2026",
            "snippet": "Updated standard specifies mandatory threat analysis and risk assessment (TARA) requirements for over-the-air (OTA) updates and vehicle-to-cloud telemetry pipelines.",
            "source_name": "SAE International",
            "published_at": "2026-08-17 11:30:00",
        },
    ],
}


class MockSearchEngine(BaseSearchEngine):
    """Deterministic mock search engine returning domain-specific items."""

    def search(
        self,
        query: str,
        domain: DomainType,
        max_results: int = 5,
        lookback_hours: int = 24,
    ) -> List[RawSourceItem]:
        """Return predefined domain items."""
        raw_items = MOCK_SOURCE_DATA.get(domain, [])
        results = []
        for item in raw_items[:max_results]:
            results.append(
                RawSourceItem(
                    title=item["title"],
                    url=item["url"],
                    snippet=item["snippet"],
                    source_name=item["source_name"],
                    published_at=item["published_at"],
                    domain=domain,
                    raw_metadata={"mock": True, "query": query},
                )
            )
        logger.info(f"Mock search returned {len(results)} items for domain '{domain.value}'")
        return results
