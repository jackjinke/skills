---
name: company-analysis
description: Use when the user asks to analyze a company, research a business, evaluate a stock, or understand a company's fundamentals, financials, industry position, or growth prospects. Triggers on requests like "analyze [company]", "research [company]", "tell me about [company]'s business".
user-invocable: true
---

# Company Deep Analysis

Perform a comprehensive deep-dive analysis of a given company, producing a structured Markdown report with cited sources.

Arguments: `$ARGUMENTS` (company name or ticker symbol)

## Research Process

### Phase 1: Information Gathering

Use all available research channels in parallel to maximize coverage. Dispatch research tasks to parallel subagents where possible to speed up data gathering.

#### 1. Primary Sources (Authoritative Data)

Through web search, prioritize finding the following types of reliable sources:

- **Official company information**: Official website, investor relations pages, financial reports (annual/quarterly), prospectuses
- **Industry analysis reports**: Reports from reputable consulting or research institutions
- **Financial data platforms**: Publicly available financial data, market cap, valuation metrics
- **Authoritative news coverage**: In-depth reports from mainstream financial media
- **Analyst reports & ratings**: Brokerage research reports, analyst ratings
- **Regulatory filings**: SEC filings, company announcements, policy documents

Use whatever web search and web page reading tools are available in the current environment to find the above sources.

**Multi-language search**: Tailor search language to the company's market context. For Chinese companies, search in BOTH English (for international media coverage, SEC filings, analyst reports) AND Chinese (for Chinese financial media, domestic industry reports, company announcements, regulatory filings from CSRC/SSE/SZSE). Apply the same principle to companies from other non-English-speaking markets.

#### 2. Community Sentiment Sources (Supplementary)

**Only use these for public sentiment and reputation analysis (Section 3.3 of the report):**

- **Reddit** — Search relevant subreddits for investor/user discussions, bullish and bearish perspectives. Use Reddit-related skills if available.
- **Xiaohongshu** — If the company has significant Chinese market presence, search for consumer reviews and brand perception. Use Xiaohongshu-related skills if available.
- Other social media or community platforms as available

These platforms are NOT reliable sources for financial data, business strategy, or industry analysis. Use them exclusively for gauging public opinion and sentiment.

### Parallel Agent Strategy

For comprehensive analysis, dispatch multiple agents to research different sections concurrently. Each agent MUST follow the same citation and format standards as the final report.

**Agent division example:**
- Agent A: Company Overview + Financial Analysis (Sections 1 & 2)
- Agent B: Competitive Position + Recent Developments (Section 3)
- Agent C: Industry & Market Context (Section 4)
- Agent D: Future Outlook (Section 5)
- Agent E: Community Sentiment — Reddit, Xiaohongshu (Section 3.3)

**Sub-report requirements (mandatory for each agent):**
1. Each agent produces its own sub-report as a Markdown file, saved as `{company-name}-section-{section-number}-{YYYY-MM-DD}.md`
2. Every factual claim in the sub-report must include an inline citation with a clickable link — this is non-negotiable even for sub-reports
3. Each sub-report must end with its own Sources section listing all referenced URLs

**Final synthesis:**
After all agents complete, merge sub-reports into the final report. During merging:
- Consolidate all sources into a unified Sources section (deduplicate, keep all unique links)
- Resolve any conflicting information between sub-reports by noting discrepancies
- Ensure consistent tone and language throughout

### Phase 2: Analysis & Synthesis

After gathering information (directly or via sub-agent reports), synthesize findings into the report structure below. Cross-reference multiple authoritative sources for accuracy. Flag any conflicting information. Clearly distinguish between verified facts (from primary sources) and opinions/sentiment (from community sources).

## Report Structure

## Storage

Before generating any files, create a subdirectory named after the company's English name (lowercase, hyphenated) under the current working directory. All output files — sub-reports and final report — go into this subdirectory. Follow the naming convention of existing subdirectories in the workspace (e.g., `chindata`, `modelbest`).

```
{current-working-directory}/
  {company-name}/
    {company-name}-analysis-{YYYY-MM-DD}.md          # Final report
    {company-name}-section-1-{YYYY-MM-DD}.md          # Sub-reports (if using parallel agents)
    {company-name}-section-2-{YYYY-MM-DD}.md
    ...
```

Generate a Markdown report with the following sections.

```markdown
# {Company Name} Deep Analysis Report

> Analysis Date: {YYYY-MM-DD}
> Analyst: AI-Assisted Research

## Executive Summary
<!-- 3-5 sentence overview of the company and key findings -->

## 1. Company Overview
### 1.1 Basic Information
- Full legal name, ticker symbol (if public), headquarters
- Founded date, founder(s), current CEO/leadership
- Number of employees, key office locations
- Market capitalization (if public)

### 1.2 Core Business & Products
- Main business segments and revenue breakdown
- Key products/services and their market position
- Business model description
- Key customers/partners

### 1.3 History & Milestones
- Major historical events and turning points
- Key acquisitions or strategic decisions

## 2. Financial Analysis
### 2.1 Financial Overview
- Revenue trends (recent 3-5 years if available)
- Profitability metrics (gross margin, operating margin, net margin)
- Cash flow situation
- Debt levels and balance sheet health

### 2.2 Key Financial Metrics
- YoY growth rates
- P/E ratio, P/S ratio (if public)
- Comparison with industry averages

### 2.3 Funding & Investors (if private)
- Funding rounds and valuations
- Key investors

## 3. Current Status & Competitive Position
### 3.1 Market Position
- Market share and ranking within industry
- Key competitors and competitive advantages (moat)
- SWOT analysis (Strengths, Weaknesses, Opportunities, Threats)

### 3.2 Recent Developments
- Latest news, product launches, strategic moves
- Management changes or organizational restructuring
- Regulatory or legal issues

### 3.3 Community & Public Sentiment
- Summary of discussions from Reddit, Xiaohongshu, social media
- Customer/user satisfaction signals
- Employee sentiment (Glassdoor, etc.)

## 4. Industry & Market Context
### 4.1 Industry Overview
- Industry definition, size, and growth rate
- Key trends and drivers
- Regulatory environment

### 4.2 Competitive Landscape
- Major players and their market shares
- Recent M&A activity in the industry
- Emerging disruptors or technologies

### 4.3 Macroeconomic Factors
- Relevant economic conditions affecting the industry
- Geopolitical considerations (if applicable)

## 5. Future Outlook
### 5.1 Growth Opportunities
- New markets, products, or services in development
- Strategic initiatives and expansion plans
- Technology or innovation pipeline

### 5.2 Potential Major Achievements
- Catalysts that could significantly increase company value
- Upcoming milestones (IPO, major product launch, market expansion)
- Analyst predictions and price targets (if public)

### 5.3 Risks & Challenges
- Key risks to the growth thesis
- Competitive threats
- Regulatory or market headwinds

## 6. Conclusion & Assessment
- Overall assessment of the company's position and prospects
- Key factors to watch going forward
- Summary rating or outlook (Positive / Neutral / Cautious)

## Sources
<!-- ALL sources must be listed here with clickable links -->
1. [Source Title](URL) — Brief description of what was referenced
2. ...
```

## Citation Requirements

**Every factual claim must be traceable to a source.**

- When referencing information from web search, include an inline citation like `[Source Name](URL)` at the point of reference AND list it in the Sources section at the end.
- When referencing Reddit discussions, link to the specific post or thread.
- When referencing Xiaohongshu content, include the feed/post ID or link.
- If a fact appears in multiple sources, cite the most authoritative one.
- Clearly mark any information that could not be independently verified.
- Distinguish source reliability: primary/authoritative sources (financial reports, official filings, industry reports) vs. supplementary sources (social media, community forums).

## Quality Standards

- **Objectivity**: Present balanced analysis — include both bull and bear cases.
- **Recency**: Prioritize the most recent data available. Always note the date of financial data.
- **Depth**: Go beyond surface-level summaries. Include specific numbers, percentages, and comparisons.
- **Completeness**: If a section cannot be filled due to lack of data, explicitly state "Information not available" rather than omitting it.
- **Language**: Write the report in the same language the user used when requesting the analysis. If `$ARGUMENTS` contains Chinese text, the entire report MUST be written in Chinese. Language detection should be based on the input arguments, not the skill definition language.
