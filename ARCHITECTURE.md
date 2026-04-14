# adrx — Architecture

## Problem

TODO: Describe the pain point. What does a paid-search analyst have to do manually today, why is it slow or error-prone, and what does adrx replace?

## High-Level Design

TODO: One paragraph summarizing the end-to-end shape of the system — what goes in, what comes out, and the role Claude plays in the middle.

## Components

### 1. Input Layer (CLI)

A Click-based Python CLI accepting:

- `--input` — path to a Google Ads-style CSV file containing daily keyword-level performance data
- `--output` — optional path to write the final briefing as a structured JSON file

### 2. Data Loader

TODO: Describe how the CSV is read and normalized. What validation happens? How is the date window determined (e.g., rolling 60-day window, configurable lookback)?

### 3. Analysis Engine

TODO: Describe the set of analysis passes run over the data before the agent is invoked — e.g., budget pacing calculations, CPC trend detection, conversion rate comparisons, zero-conversion term identification. Is this pure pandas logic, or does it involve a pre-pass LLM call?

### 4. Agent Core

TODO: Describe the agentic loop — how Claude is prompted, what tools it has access to, and how the loop terminates. What does the system prompt look like at a high level?

### 5. Tools

TODO: List the functions exposed to Claude via the Anthropic tool-use schema and what each one does.

### 6. Output Layer

TODO: Describe how Claude's final response is formatted — Rich terminal output, JSON file, or both. What fields appear in the briefing? How are findings prioritized or ranked?

## Data Flow

```
CSV file (--input)
      ↓
Data Loader (pandas normalization + validation)
      ↓
Analysis Engine (pacing, CPC trends, CVR ranking, zero-conv terms)
      ↓
Agent Core (system prompt + analysis summary + tools)
      ↓
Claude API ⇄ Tool execution loop
      ↓
Structured JSON briefing
      ↓
Rich terminal report  [+  optional --output JSON file]
```

## Key Design Decisions

- **TODO: Decision 1.** Placeholder — e.g., why a pre-analysis pass rather than sending raw CSV rows to Claude.
- **TODO: Decision 2.** Placeholder — e.g., why JSON-structured output over free-form prose.
- **TODO: Decision 3.** Placeholder — e.g., why a single `brief` command rather than separate sub-commands per analysis type.
- **TODO: Decision 4.** Placeholder — e.g., tradeoffs between agentic tool-use loop vs. a single large-context call.

## Out of Scope (v1)

- TODO: List explicit non-goals here.

## Future Extensions

- TODO: List features or directions that are plausible next steps but deliberately deferred.
