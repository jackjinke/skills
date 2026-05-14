---
name: company-analysis-report
description: Use when the user asks to analyze a company, research a business, evaluate a stock, or understand a company's fundamentals, financials, industry position, or growth prospects. Triggers on requests like "analyze [company]", "research [company]", "tell me about [company]'s business".
user-invocable: true
---

# Company Deep Analysis

Perform a comprehensive deep-dive analysis of a given company, producing a structured Markdown report with cited sources.

Arguments: `$ARGUMENTS` (company name or ticker symbol)

## Step 0: Create Output Directory

Before doing any research, create the output directory for all reports. All subsequent output — sub-reports from parallel agents and the final merged report — MUST be saved into this directory.

```
{current-working-directory}/{company-name}/
```

- `{company-name}` = company's English name, lowercase, hyphenated (e.g., `palo-alto-networks`, `china-mobile`)
- Follow the naming convention of existing subdirectories in the workspace (e.g., `chindata`, `modelbest`)
- Create this directory immediately so that parallel agents can write their sub-reports into it as they complete

## Research Process

### Phase 1: Information Gathering

Use all available research channels in parallel to maximize coverage. Dispatch research tasks to parallel subagents where possible to speed up data gathering.

**Adapting to company type:** Not all sources and sections apply equally. For **private companies**, SEC filings, P/E ratios, short seller reports, and analyst price targets will not exist — shift focus to funding history, investor profiles, employee reviews, press coverage, and industry positioning. For **smaller/early-stage companies**, fewer authoritative sources will be available — rely more on founder interviews, product reviews, community sentiment, and competitive analysis. Sections that cannot be meaningfully filled should state what was searched and why data was unavailable, rather than being silently skipped.

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

#### 2. Risk & Negative Information Sources (Critical)

**You MUST actively search for negative information and red flags.** A balanced analysis requires deliberate effort to uncover problems — do not rely on official sources alone, as they are inherently biased toward positive narratives. Search specifically for:

- **Litigation & legal issues**: Lawsuits (class-action, patent, antitrust, securities fraud), regulatory enforcement actions, SEC investigations, consent decrees
- **Short seller reports**: Reports from short-selling firms (e.g., Muddy Waters, Hindenburg Research, Citron, Grizzly Research) — these often contain deep forensic analysis of accounting irregularities, fraud, or overvaluation
- **Regulatory penalties & compliance failures**: Fines, sanctions, warning letters, product recalls, data breach disclosures, environmental violations
- **Corporate governance red flags**: Auditor changes or qualifications, restatements, related-party transactions, insider selling patterns, executive turnover, dual-class share structures with concentrated voting power
- **Investigative journalism**: In-depth exposés, whistleblower reports, leaked documents
- **Failed initiatives**: Abandoned products, withdrawn guidance, missed targets, failed acquisitions or integrations, shuttered business lines
- **Employee & workplace issues**: Labor disputes, layoffs, workplace safety violations, discrimination lawsuits, union conflicts, Glassdoor/Blind complaints about systemic issues (not just individual grievances)

**Search strategy**: Include negative keywords explicitly in searches — e.g., `"{company name}" lawsuit OR fraud OR investigation OR scandal OR fine OR penalty OR recall`, `"{company name}" short seller OR short report OR overvalued`, `"{company name}" controversy OR criticism OR failure OR problem`.

#### 3. Community Sentiment Sources (Supplementary)

Search these platforms for public sentiment, reputation analysis, AND as early-warning signals for risks not yet covered by mainstream media:

- **Reddit** — Search relevant subreddits (r/wallstreetbets, r/stocks, r/investing, industry-specific subs) for investor/user discussions, bullish AND bearish perspectives, whistleblower posts, and detailed bear-case analyses. Pay special attention to well-researched critical posts. Use Reddit-related skills if available.
- **Xiaohongshu** — If the company has significant Chinese market presence, search for consumer reviews, brand perception, product complaints, and service quality issues. Use Xiaohongshu-related skills if available.
- **Other platforms** — Glassdoor/Blind (employee sentiment), Twitter/X (real-time developments), industry forums

These platforms are NOT reliable sources for verified financial data. However, they are valuable for: (1) gauging public opinion and sentiment, (2) surfacing complaints, risks, or controversies that authoritative sources may lag on or omit, (3) identifying patterns of user/employee dissatisfaction. Always cross-reference community claims against authoritative sources before presenting them as facts — but do report significant recurring themes even when unverified, clearly labeled as such.

### Parallel Agent Strategy

For comprehensive analysis, dispatch multiple subagents to research different domains concurrently. **Each subagent MUST be scoped to a single, specific domain and perform deep vertical analysis within that domain only.**

**⚠️ CRITICAL INSTRUCTIONS FOR SUBAGENT DISPATCH:**

When dispatching each subagent, you MUST include the following in its context/prompt:

1. **Explicit domain scope**: State clearly which specific domain the subagent is responsible for. Example: "You are the Financial Analysis specialist. Your ONLY responsibility is to analyze the company's financials."
2. **Prohibition on skill re-invocation**: Explicitly instruct: "You MUST NOT run or invoke the Company Analysis skill again. Do NOT attempt to produce the full company analysis report. Focus ONLY on your assigned domain."
3. **Prohibition on cross-domain work**: Explicitly instruct: "You MUST NOT research or write about other domains (e.g., if you are the Financial Analysis agent, do not research leadership, competitive position, or industry context). Stay strictly within your assigned scope."
4. **Tool usage mandate**: Explicitly instruct: "You MUST actively use available tools (web search, web page reading, Reddit, Xiaohongshu, or any other tools available in your environment) to conduct DEEP research within your domain. Surface-level summaries are unacceptable — dig into specific numbers, events, patterns, and evidence."
5. **Deep analysis expectation**: Explicitly instruct: "Your analysis should be VERTICAL and DEEP, not broad and shallow. For example, the Financial Analysis agent should pull actual financial figures, calculate ratios, compare against peers, and identify trends — not just provide a generic overview."

**How to divide agents (dynamic, not hard-coded):**

Rather than prescribing fixed agent roles, determine the optimal division based on:
- **Company type**: Public vs. private, size, stage (startup vs. mature)
- **Data availability**: Which domains have sufficient sources for deep analysis
- **User focus**: If the user hinted at specific concerns (e.g., "Is the CEO trustworthy?"), allocate a dedicated agent for that area

Use the report sections (Sections 1–5) as natural boundaries, but feel free to merge or split based on depth requirements. Common patterns include:
- One agent per major section (Company Overview, Financials, Competitive Position, Industry Context, Future Outlook)
- A dedicated adversarial agent for risk & negative information (mandatory — this must always have its own agent)
- A dedicated agent for community sentiment if the company has significant public presence
- Sub-dividing large sections (e.g., separating leadership analysis from financial analysis if both warrant deep treatment)

**⚠️ NEVER assign an agent to produce the entire report or to cover multiple unrelated domains superficially.**

**Sub-report requirements (mandatory for each agent):**
1. Each agent saves its sub-report into the output directory created in Step 0, using a filename that reflects its research domain: `{company-name}/{company-name}-section-{domain-name}-{YYYY-MM-DD}.md`
   - `{domain-name}` should be a clear, lowercase, hyphenated description of the domain (e.g., `financial-analysis`, `leadership-key-people`, `competitive-position`, `industry-market-context`, `future-outlook`, `community-sentiment`, `risk-negative-info`).
   - Choose a `{domain-name}` that accurately describes what this subagent researched — do NOT use generic numbers like `section-1`, `section-2`.
2. Every factual claim in the sub-report must include an inline citation with a clickable link — this is non-negotiable even for sub-reports
3. Each sub-report must end with its own Sources section listing all referenced URLs
4. When dispatching agents, pass the absolute path of the output directory so each agent knows where to write
5. Each sub-report should demonstrate DEPTH in its domain — include specific numbers, named individuals, dated events, and detailed evidence

**Final synthesis:**
After all agents complete, merge sub-reports into the final report. During merging:
- Consolidate all sources into a unified Sources section (deduplicate, keep all unique links)
- Resolve any conflicting information between sub-reports by noting discrepancies
- Ensure consistent tone and language throughout

### Phase 2: Analysis & Synthesis

After gathering information (directly or via sub-agent reports), synthesize findings into the report structure below.

**Synthesis guidelines:**
- **Cross-reference**: Verify key claims against at least two independent sources. When sources conflict, present both perspectives and assess which is more credible (and why).
- **Separate fact from opinion**: Clearly distinguish verified facts (financial filings, official announcements) from analyst opinions, community sentiment, and your own inferences.
- **Connect the dots**: Don't just list facts — explain how they relate. Does the leadership's track record (Section 1.3) align with the financial trajectory (Section 2)? Do the community complaints (Section 3.4) foreshadow the risks you identified (Section 3.3)?
- **Stress-test the narrative**: If the bull case sounds compelling, ask "what has to go right for this to work?" and "what would make me wrong?" Surface the assumptions, then evaluate them.
- **Weight by materiality**: Not all findings deserve equal space. A $50M lawsuit against a $500B company is a footnote; the same lawsuit against a $500M company is a headline. Allocate depth proportionally.

## Report Template

After all sub-reports are collected, merge them into the final report and save it as `{company-name}/{company-name}-analysis-{YYYY-MM-DD}.md` in the output directory created in Step 0.

Generate the final report with the following sections.

```markdown
# {Company Name} Deep Analysis Report

> Analysis Date: {YYYY-MM-DD}
> Analyst: AI-Assisted Research

## Executive Summary
<!-- 5-8 sentences. MUST cover: (1) what the company does and its current position, (2) the most significant positive finding, (3) the most significant risk or concern, (4) overall assessment. This is NOT a pitch — a reader should be able to decide whether to read further based on a balanced summary. -->

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

### 1.3 Leadership & Key People
<!-- Analyze not just the CEO, but all individuals who materially influence the company's direction and success. -->

#### Top Leadership
- **CEO / founder(s)**: Background, track record at this and prior companies, tenure, and leadership style
- **Leadership style & philosophy**: Centralized vs. delegated decision-making, risk appetite, culture they foster. Cite interviews, shareholder letters, or employee accounts.
- **Vision & strategic thinking**: Does leadership articulate a clear, credible long-term vision? Have they anticipated industry shifts or been reactive? Evaluate based on past strategic calls — what did they get right, what did they get wrong?
- **Execution track record**: Do they deliver on promises? Compare past guidance, announced initiatives, and stated timelines against actual results. Pattern of overpromising and underdelivering is a red flag.

#### Other Key Figures
- **C-suite & senior executives**: CFO, CTO/CIO, COO, Chief Product Officer, General Counsel — background, tenure, and notable contributions or missteps
- **Key technical / creative leaders**: Chief scientist, lead architect, head of R&D, or other individuals whose expertise is core to the company's competitive advantage
- **Influential board members & investor representatives**: Board composition, independence, notable directors, activist investors with board seats
- **Recent departures**: Key people who left recently — why, and what impact has it had?

#### External Commitments & Time Allocation
<!-- Analyze whether key leaders hold positions at other companies, and assess how much focus they can realistically devote to THIS company. -->
- **Cross-holdings & external roles**: Do the CEO, founders, or key executives hold board seats, advisory roles, executive positions, or significant ownership stakes at other companies? List each company and the specific role(s) held.
- **Related-party transactions & conflicts of interest**: Are there business dealings between this company and other entities where leadership holds interests? Any historical pattern of channeling resources or attention toward external ventures at the core company's expense?
- **Estimated focus / effort allocation**: Based on external signals, provide a qualitative assessment of how much professional energy leadership devotes to this company versus elsewhere. Signals to evaluate include:
  - **Public visibility**: Frequency of earnings call participation, investor day attendance, and media appearances on behalf of this company vs. other entities
  - **Operational involvement**: Reporting lines, stated day-to-day responsibilities, and internal communications cited in press or filings
  - **External activity load**: Board meetings, capital-raising events, product launches, or public advocacy for other ventures
  - **Historical patterns**: Changes in engagement level over time (e.g., gradual disengagement after a secondary venture gains traction)
  - Categorize the estimated focus as one of: **Fully dedicated** | **Primarily focused** | **Split attention** | **Marginally engaged**
- **Evidence & methodology**: Explicitly state which signals were used and their sources (e.g., "CEO X missed 2 of 4 quarterly earnings calls in 2024 while serving as active chair of Company Y"; "Founder Z’s social media activity in Q1–Q3 was 80% about their AI startup and 20% about this company per post analysis"). Distinguish hard facts (disclosed positions, verified filings) from reasonable inferences.
- **Implications for governance & execution**: Does divided attention appear to affect strategic decisions, operational oversight, crisis response speed, or capital allocation? Have shareholders, analysts, or board members publicly raised concerns? Cite specific instances.

#### Leadership Assessment
- **Public reputation & perception**: How is leadership viewed by employees (Glassdoor/Blind), investors (analyst commentary), media, and the industry? Any personal controversies, legal issues, or ethical concerns?
- **Team cohesion & stability**: Is the leadership team stable, or has there been significant turnover? Do public signals suggest alignment or internal friction?
- **Succession & key-person risk**: How dependent is the company on specific individuals? Is there a credible succession plan or a deep bench?

### 1.4 History & Milestones
- Major historical events and turning points
- Key acquisitions or strategic decisions
- Notable failures, crises, or controversies in company history

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

### 3.3 Known Issues, Controversies & Red Flags
<!-- This section is MANDATORY — every company has risks. "No issues found" is not acceptable without demonstrating thorough search effort. -->
- **Litigation & legal exposure**: Active lawsuits, regulatory investigations, historical settlements, class-action status
- **Short seller / bear case reports**: Key claims from short sellers or prominent critics, and the company's response (if any)
- **Regulatory & compliance**: Fines, sanctions, warning letters, product recalls, data privacy violations, environmental penalties
- **Corporate governance concerns**: Auditor changes, financial restatements, related-party transactions, insider selling trends, board independence issues, shareholder disputes
- **Operational failures**: Product failures, service outages, security breaches, supply chain disruptions, missed guidance
- **Management & culture risks**: Executive turnover, founder controversies, workplace culture issues, key-person dependency (cross-reference with Section 1.3 Leadership assessment)

### 3.4 Community & Public Sentiment
- Summary of discussions from Reddit, Xiaohongshu, social media
- Customer/user satisfaction signals — both positive and negative patterns
- Employee sentiment (Glassdoor, Blind, etc.) — recurring complaints vs. praise
- Notable bearish theses or criticism from the investor community

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
<!-- Be specific and concrete — vague platitudes like "regulatory risk" are not useful. Name the specific regulation, the specific competitor, the specific vulnerability. -->
- **Thesis-breaking risks**: What specific scenarios would invalidate the bull case? What assumptions must hold true for the growth story to work?
- **Competitive threats**: Which specific competitors are gaining ground, and in what segments? What disruptive technologies could erode the moat?
- **Regulatory & political risks**: Specific pending legislation, regulatory reviews, or geopolitical tensions that directly affect this company
- **Financial risks**: Debt maturity schedules, liquidity concerns, customer concentration, revenue quality issues, accounting concerns flagged by auditors or analysts
- **Operational risks**: Key-person dependency, technology debt, supply chain vulnerabilities, geographic concentration
- **Unresolved issues from Section 3.3**: Any ongoing litigation, investigations, or controversies that remain unresolved and could materially impact the company

## 6. Conclusion & Assessment
- **Overall assessment**: Synthesize the key findings into a coherent thesis — what is this company's story, and how credible is it?
- **Key factors to watch**: 3-5 specific, monitorable items (upcoming earnings, pending litigation ruling, regulatory decision date, competitor product launch) — not vague themes
- **Summary outlook**: Rate as one of: Strong Positive / Positive / Neutral / Cautious / Negative. Justify the rating explicitly by weighing:
  - Leadership quality and execution track record (Section 1.3)
  - Financial health and trajectory (Section 2)
  - Competitive position durability (Section 3.1)
  - Severity and probability of identified risks (Sections 3.3, 5.3)
  - If risks are concentrated (e.g., single regulatory decision could be fatal) vs. diversified, note this

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

- **Objectivity**: Present balanced analysis — include both bull and bear cases. The bear case should be given equal rigor and depth as the bull case, not treated as an afterthought.
- **Adversarial rigor**: Actively try to find reasons NOT to invest. A report that reads like a pitch deck has failed. If Section 3.3 (Known Issues) is significantly shorter than Section 1.2 (Core Business), revisit your research — you likely haven't searched hard enough for negative information.
- **Recency**: Prioritize the most recent data available. Always note the date of financial data.
- **Depth**: Go beyond surface-level summaries. Include specific numbers, percentages, and comparisons.
- **Specificity over platitudes**: "The company faces regulatory risk" is useless. "The EU Digital Markets Act (effective March 2024) could force the company to open its payment system to competitors, threatening an estimated 15% of services revenue" is useful.
- **Completeness**: If a section cannot be filled due to lack of data, explicitly state "Information not available" rather than omitting it.
- **Language**: Write the report in the same language the user used when requesting the analysis. If `$ARGUMENTS` contains Chinese text, the entire report MUST be written in Chinese. Language detection should be based on the input arguments, not the skill definition language.
