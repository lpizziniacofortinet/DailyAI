# DailyAI — Autonomous Intelligence & Fact-Checking Pipeline

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Architecture](https://img.shields.io/badge/pipeline-3--agent%20architecture-emerald.svg)]()
[![Fact Checking](https://img.shields.io/badge/verification-independent%20layer-red.svg)]()
[![Tests](https://img.shields.io/badge/tests-39%20passed-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**DailyAI** is an autonomous, production-grade multi-agent service that continuously tracks, verifies, summarizes, and delivers mission-critical technical intelligence across three specialized domains:

1. 🤖 **Artificial Intelligence (AI)** — Frontier reasoning models, benchmark breakthroughs, open weights releases, architecture papers, and autonomous agent safety frameworks.
2. 🔐 **Cybersecurity** — Zero-day disclosures, CISA Known Exploited Vulnerabilities (KEV) directives, CVE root-cause analyses, post-quantum cryptography (PQC) standards, and supply-chain threats.
3. 🚗 **V2X & Automotive Technology** — Cellular V2X (C-V2X / 5G-V2X sidelink), 3GPP Release 18/19 standards, ISO/SAE 21434 vehicle cybersecurity, USDOT ITS roadside deployments, and connected autonomous fleet safety.

---

## 🏛 Pipeline Architecture

The system operates as an uncompromising sequential pipeline of **three specialized autonomous agents** communicating through strictly validated Pydantic data models:

```
                         ┌──────────────────────────────────────────────┐
                         │              Live Web & Feeds                │
                         │ (DuckDuckGo / Tavily / Serper / CISA / arXiv)│
                         └──────────────────────┬───────────────────────┘
                                                │
                                                ▼
                         ┌──────────────────────────────────────────────┐
                         │   Agent 1 — Research & Intelligence Agent    │
                         │ • Targeted multi-query domain searches       │
                         │ • Ingestion of authoritative RSS feeds       │
                         │ • Canonical URL normalization & dedup        │
                         │ • Temporal grounding & draft synthesis       │
                         └──────────────────────┬───────────────────────┘
                                                │ List[ArticleDraft]
                                                ▼
                         ┌──────────────────────────────────────────────┐
                         │    Agent 2 — Fact-Checking & Quality Agent   │
                         │ • Independent verification layer             │
                         │ • Real-time date freshness validation        │
                         │ • Hallucination & exaggeration detection     │
                         │ • Technical identifier audit (CVEs, 3GPP, ISO)│
                         │ • Confidence score gating (>= 0.75)          │
                         │ • Relevance ranking & "Why It Matters" notes │
                         └──────────────────────┬───────────────────────┘
                                                │ List[VerifiedArticle]
                                                ▼
                         ┌──────────────────────────────────────────────┐
                         │    Agent 3 — Newsletter & Delivery Agent     │
                         │ • Executive subject line synthesis           │
                         │ • Responsive HTML & Plain-Text templating    │
                         │ • "Why It Matters" operational impact notes  │
                         │ • Explicit caveat & uncertainty flags        │
                         │ • Multi-channel delivery (SMTP / File export)│
                         │ • Permanent publication deduplication record │
                         └──────────────────────┬───────────────────────┘
                                                │
                                                ▼
                         ┌──────────────────────────────────────────────┐
                         │         Multi-Channel Distribution           │
                         │ • SMTP (STARTTLS / SSL Email)                │
                         │ • Responsive Email Newsletter                │
                         │ • Local HTML/JSON/Markdown Archive           │
                         └──────────────────────────────────────────────┘
```

---

## 🤖 Detailed Agent Breakdown

### Agent 1 — Research & Intelligence Agent
* **Role**: Primary discovery, web ingestion, and raw draft synthesis.
* **Responsibilities**:
  - Gathers live intelligence from search engines (DuckDuckGo News, Tavily, Google Serper) and curated high-authority feeds (CISA Advisories, arXiv CS.AI/CS.LG, NIST, 5GAA, IEEE, SAE).
  - Normalizes tracking query parameters (`utm_*`, `ref`, `fbclid`, `gclid`) to guarantee canonical URL uniqueness.
  - Queries persistent SQLite storage to filter out previously seen URLs and near-duplicate headlines before calling LLMs.
  - Injects **temporal reference context** (current real-world date and valid lookback period) to ensure contemporary articles are extracted with exact publication dates.
  - Synthesizes findings into structured `ArticleDraft` instances, cleanly isolating verified empirical facts from speculative marketing claims.
  - *Reliability Rule*: If sources are scarce, produces fewer articles rather than inventing or extrapolating information.

### Agent 2 — Fact-Checking & Quality Agent
* **Role**: Uncompromising independent verification layer (never trusts Agent 1's output blindly).
* **Responsibilities**:
  - **Deterministic Date Freshness Gate**: Enforces that article publication dates fall within the configured `LOOKBACK_HOURS` window (with configurable buffer), immediately rejecting historical, stale, or evergreen articles.
  - **Temporal Grounding**: Provides the LLM with the exact current reference date and computed valid historical range to eliminate false-positive "future date" rejections.
  - **Technical Identifier Auditing**: Regex-validates standard security identifiers (`CVE-YYYY-NNNN+`) and formal engineering standards (`3GPP Release XX`, `ISO/SAE 21434`, `NIST FIPS/SP`).
  - **Hallucination & Hype Screening**: Detects fabricated metrics, ungrounded benchmark claims, and impossible vendor timelines.
  - **Confidence Score Gating**: Enforces minimum confidence threshold (`MIN_CONFIDENCE_SCORE`, default `0.75`).
  - **Caveat Flagging**: Explicitly annotates early-stage research, unverified vendor assertions, or rumors.
  - Generates concise **"Why It Matters"** operational impact notes and ranks approved articles by importance.

### Agent 3 — Newsletter & Delivery Agent
* **Role**: Publication assembly, layout rendering, and distribution engine.
* **Responsibilities**:
  - Organizes strictly verified articles into three standardized sections:
    - 🤖 **Artificial Intelligence**
    - 🔐 **Cybersecurity**
    - 🚗 **V2X & Automotive Technology**
  - Synthesizes executive-level email subject lines summarizing key developments.
  - Renders both bulletproof responsive HTML email (compatible with Gmail, Apple Mail, Outlook, mobile clients) and clean Plain-Text.
  - Dispatches via secure SMTP with STARTTLS or SSL/TLS encryption.
  - Exports local HTML, Text, and JSON run archives to `output/newsletters/`.
  - Marks published articles in SQLite database so they are never sent again in future runs.

---

## 📁 Project Structure

```
DailyAI/
├── .env.example                     # Environment configuration template
├── .gitignore                       # Git ignore rules
├── LICENSE                          # MIT License
├── pyproject.toml                   # Standard packaging & tool configurations
├── requirements.txt                 # Core runtime dependencies
├── requirements-dev.txt             # Development and testing dependencies
├── README.md                        # Project documentation
│
├── dailyai/                         # Core Python package
│   ├── __init__.py                  # Package version and metadata
│   ├── __main__.py                  # CLI executable entrypoint
│   ├── cli.py                       # Click + Rich CLI commands
│   ├── config.py                    # Pydantic Settings & environment validation
│   ├── logging_config.py            # Structured Rich console & file logging
│   │
│   ├── models/                      # Structured Pydantic Data Models
│   │   ├── __init__.py
│   │   ├── article.py               # RawSourceItem, ArticleDraft, DomainType
│   │   ├── fact_check.py            # ClaimCheck, VerificationResult, VerifiedArticle
│   │   ├── newsletter.py            # NewsletterSection, Newsletter
│   │   └── pipeline.py              # PipelineRunReport, AgentExecutionRecord
│   │
│   ├── agents/                      # Specialized Pipeline Agents
│   │   ├── __init__.py
│   │   ├── base.py                  # BaseAgent, AgentResult execution wrapper
│   │   ├── research_agent.py        # Agent 1 (Research & Intelligence)
│   │   ├── fact_check_agent.py      # Agent 2 (Fact-Checking & Quality Gate)
│   │   └── newsletter_agent.py      # Agent 3 (Newsletter & Delivery)
│   │
│   ├── pipeline/                    # Orchestration Layer
│   │   ├── __init__.py
│   │   └── orchestrator.py          # PipelineOrchestrator coordinating Agents 1->2->3
│   │
│   ├── services/                    # Pluggable Service Implementations
│   │   ├── llm/                     # LLM Provider Backends
│   │   │   ├── base.py              # BaseLLMClient interface & JSON extractor
│   │   │   ├── gemini.py            # Google Gemini (google-genai SDK)
│   │   │   ├── openai_provider.py   # OpenAI & compatible providers
│   │   │   ├── mock.py              # High-fidelity deterministic Mock LLM
│   │   │   └── factory.py           # LLM client factory
│   │   │
│   │   ├── search/                  # Search & Ingestion Providers
│   │   │   ├── base.py              # BaseSearchEngine interface
│   │   │   ├── duckduckgo.py        # DuckDuckGo News & Web search
│   │   │   ├── rss.py               # Curated high-authority RSS aggregator
│   │   │   ├── tavily.py            # Tavily AI Search API
│   │   │   ├── serper.py            # Google Serper API
│   │   │   ├── mock.py              # Deterministic mock search engine
│   │   │   └── factory.py           # Search engine factory
│   │   │
│   │   ├── storage/                 # Deduplication & Audit Persistence
│   │   │   ├── base.py              # BaseDeduplicationStore interface
│   │   │   └── sqlite.py            # SQLite storage (URL hashes, titles, runs)
│   │   │
│   │   ├── delivery/                # Multi-Channel Distribution
│   │   │   ├── base.py              # BaseDeliveryChannel interface
│   │   │   ├── email_smtp.py        # SMTP email client with STARTTLS / SSL
│   │   │   ├── file_export.py       # Local file archiver (HTML/Text/JSON)
│   │   │   └── mock.py              # Mock delivery channel for tests
│   │   │
│   │   └── scheduler/               # Scheduling Service
│   │       └── scheduler.py         # APScheduler cron & interval runner
│   │
│   └── templates/                   # Jinja2 Email Templates
│       ├── __init__.py              # Template environment loader
│       ├── email_html.jinja2        # Modern, responsive HTML email template
│       └── email_text.jinja2        # Formatted plain-text email template
│
└── tests/                           # Comprehensive Pytest Suite (39 tests)
    ├── conftest.py                  # Shared fixtures & test configurations
    ├── test_config.py               # Settings and environment validation tests
    ├── test_models.py               # Model schema & serialization tests
    ├── test_storage.py              # SQLite deduplication & history tests
    ├── test_search.py               # Search engine & RSS tests
    ├── test_llm.py                  # LLM client & JSON extraction tests
    ├── test_research_agent.py       # Agent 1 unit tests
    ├── test_fact_check_agent.py     # Agent 2 unit tests (incl. date freshness)
    ├── test_newsletter_agent.py     # Agent 3 unit tests
    ├── test_delivery.py             # Email & file export tests
    ├── test_pipeline.py             # End-to-end integration tests
    └── test_scheduler.py            # Scheduling mechanism tests
```

---

## 🚀 Installation & Setup

### 1. Clone & Setup Virtual Environment
```bash
git clone <repository_url> DailyAI
cd DailyAI

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy the template `.env.example`:
```bash
cp .env.example .env
```

Edit `.env` to configure your preferred LLM provider, search preferences, and SMTP email settings:

```ini
# ==============================================================================
# 1. LLM Provider Configuration
# ==============================================================================
# Provider choices: 'gemini', 'openai', or 'mock'
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_from_google_ai_studio
GEMINI_MODEL=gemini-2.5-flash

# ==============================================================================
# 2. Intelligence Gathering & Search
# ==============================================================================
# Provider choices: 'duckduckgo', 'tavily', 'serper', 'rss_only', 'mock'
SEARCH_PROVIDER=duckduckgo
LOOKBACK_HOURS=24
ENABLE_RSS_FEEDS=true
MAX_ARTICLES_PER_CATEGORY=4

# ==============================================================================
# 3. Email Delivery (SMTP)
# ==============================================================================
EMAIL_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_16_char_app_password
EMAIL_FROM="DailyAI Intelligence <your_email@gmail.com>"
EMAIL_RECIPIENTS=subscriber1@example.com,subscriber2@example.com
```

---

## 🧠 LLM Model Selection Guide

| Model Name | Best Use Case | Rationale |
| :--- | :--- | :--- |
| **`gemini-2.5-pro`** *(or `gemini-1.5-pro`)* | 🏆 **Highest Accuracy** | Superior reasoning for Agent 2 fact-checking, subtle hallucination detection, and insightful "Why It Matters" impact notes. |
| **`gemini-2.5-flash`** *(or `gemini-2.0-flash`)* | ⚡ **Fast & Cost-Efficient** | High throughput and generous rate limits for scanning dozens of search queries. |
| **`gemini-2.5-flash-thinking`** | 🔬 **Deep Chain-of-Thought** | Uses internal reasoning tokens to evaluate technical standards and complex claims. |
| **`gpt-4o` / `gpt-4o-mini`** | 🌐 **OpenAI Backend** | Fully supported via OpenAI SDK backend (`LLM_PROVIDER=openai`). |
| **`mock`** | 🧪 **Offline / CI Testing** | Zero-key deterministic execution for fast previews and automated testing. |

---

## 💻 CLI Usage & Execution Modes

DailyAI provides a rich command-line interface via `python3 -m dailyai`:

### 1. Instant Preview Mode (Offline / Zero-Key)
Generates an immediate briefing using deterministic mock data to verify template rendering:
```bash
python3 -m dailyai preview
```
*Displays plain-text newsletter in terminal and exports responsive HTML to `output/newsletters/latest.html`.*

### 2. Run Pipeline Immediately
Executes intelligence discovery, fact-checking, and newsletter dispatch:
```bash
# Standard run using configuration from .env
python3 -m dailyai run

# Specify custom lookback window (e.g. 240 hours = 10 days)
python3 -m dailyai run --lookback 240

# Run in dry-run mode (does not send email or update persistent SQLite deduplication)
python3 -m dailyai run --dry-run

# Override options via CLI flags
python3 -m dailyai run --provider gemini --search duckduckgo --lookback 48 --max-articles 4 --recipients "user@example.com"
```

### 3. Clear Cache & Deduplication History
Clears all processed URLs, fuzzy title hashes, and publication history for a completely fresh start:
```bash
python3 -m dailyai reset-cache
```

### 4. Start Automated Scheduler
Runs DailyAI on a recurring schedule in the foreground (with graceful `SIGINT`/`SIGTERM` handling):
```bash
# Uses SCHEDULE_CRON from .env (default: daily at 08:00 AM UTC)
python3 -m dailyai schedule

# Override with custom cron pattern
python3 -m dailyai schedule --cron "0 8 * * *"

# Or run on a fixed interval (e.g. every 720 minutes / 12 hours)
python3 -m dailyai schedule --interval 720
```

### 5. Audit & History Inspection
View execution reports, processing durations, and article throughput:
```bash
python3 -m dailyai history --limit 10
```

---

## ✉️ SMTP Configuration Examples

### Gmail
1. Generate an **App Password** at [Google Account Security → App Passwords](https://myaccount.google.com/apppasswords).
2. Set in `.env`:
   ```ini
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USE_TLS=true
   SMTP_USERNAME=your_email@gmail.com
   SMTP_PASSWORD=your_16_char_app_password
   ```

### Microsoft 365 / Outlook
```ini
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USERNAME=your_email@domain.com
SMTP_PASSWORD=your_password
```

### SendGrid
```ini
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USERNAME=apikey
SMTP_PASSWORD=SG.your_sendgrid_api_key
```

---

## 🧪 Running the Test Suite

The test suite includes 39 unit and integration tests covering data models, SQLite deduplication, agents, search providers, templates, delivery channels, and end-to-end pipelines:

```bash
# Run full test suite
pytest -v

# Run with test coverage
pytest --cov=dailyai -v
```

---

## ⚙️ Configuration Reference

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `LLM_PROVIDER` | `str` | `gemini` | LLM backend: `gemini`, `openai`, or `mock` |
| `GEMINI_API_KEY` | `SecretStr` | `None` | Google Gemini API Key from Google AI Studio |
| `GEMINI_MODEL` | `str` | `gemini-2.5-flash` | Gemini model ID (`gemini-2.5-pro`, `gemini-2.5-flash`, etc.) |
| `OPENAI_API_KEY` | `SecretStr` | `None` | OpenAI API Key |
| `OPENAI_MODEL` | `str` | `gpt-4o-mini` | OpenAI model ID (`gpt-4o`, `gpt-4o-mini`, etc.) |
| `SEARCH_PROVIDER` | `str` | `duckduckgo` | Web search provider: `duckduckgo`, `tavily`, `serper`, `rss_only`, `mock` |
| `LOOKBACK_HOURS` | `int` | `24` | Hours of history to consider for recent news (1 to 8760) |
| `ENABLE_RSS_FEEDS` | `bool` | `true` | Ingest curated domain RSS feeds alongside search |
| `FACT_CHECK_STRICT_MODE` | `bool` | `true` | Strict mode rejects uncorroborated articles |
| `MIN_CONFIDENCE_SCORE` | `float`| `0.75` | Minimum credibility score (0.0 - 1.0) required to pass Agent 2 |
| `MAX_ARTICLES_PER_CATEGORY` | `int` | `4` | Maximum articles published per section (1 to 50) |
| `EMAIL_ENABLED` | `bool` | `false` | Enable/disable actual SMTP outbound email dispatch |
| `SMTP_HOST` | `str` | `smtp.gmail.com` | SMTP server host |
| `SMTP_PORT` | `int` | `587` | SMTP port (587 for STARTTLS, 465 for direct SSL) |
| `SMTP_USE_TLS` | `bool` | `true` | Enable STARTTLS encryption |
| `SMTP_USE_SSL` | `bool` | `false` | Enable direct SSL/TLS encryption |
| `SMTP_USERNAME` | `str` | `""` | SMTP authentication username |
| `SMTP_PASSWORD` | `SecretStr` | `""` | SMTP password or App Password |
| `EMAIL_FROM` | `str` | `"DailyAI <...>"` | Sender address in From header |
| `EMAIL_RECIPIENTS` | `str` | `""` | Comma-separated list of recipient emails |
| `DATABASE_PATH` | `Path`| `data/dailyai.sqlite` | Path to persistent SQLite deduplication database |
| `OUTPUT_DIR` | `Path`| `output/newsletters` | Local directory for archived newsletters (HTML/Text/JSON) |
| `SCHEDULE_CRON` | `str` | `"0 8 * * *"` | Standard 5-field cron expression for recurring scheduler |

---

## 🔒 Security & Reliability Design

1. **Independent Fact-Checking**: Agent 2 uses dedicated verification queries, deterministic publication date checks, CVE regex validation, standards checking, and hallucination screening to ensure ungrounded claims are filtered out.
2. **Temporal Grounding**: Both Agent 1 and Agent 2 receive explicit real-time calendar references (`today_str` and computed valid window) to eliminate false-positive future-date rejections.
3. **Persistent Deduplication**: SQLite persistent store records URL hashes and uses normalized fuzzy title similarity to prevent the same event or syndicated repost from appearing in future briefings.
4. **Secret Masking**: All sensitive credentials (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `SMTP_PASSWORD`) utilize Pydantic `SecretStr` to prevent accidental logging or exposure in exception traces.
5. **Resilient Retry Backoff**: Network calls, search requests, and LLM completions incorporate `tenacity` exponential backoff with automatic recovery.
6. **Multi-Format Archival**: Every newsletter run is automatically exported as responsive HTML, Markdown/Text, and structured JSON for auditability and compliance.

---

## 📄 License
Released under the [MIT License](LICENSE).
