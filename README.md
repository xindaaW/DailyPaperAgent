# DailyPaperAgent

DailyPaperAgent is an agentic workflow for tracking new arXiv papers and turning them into a polished Chinese research report.

Instead of using a rigid summarize-only pipeline, it combines a main orchestrating agent, role-based subagents, lightweight memory, and model-based quality gates so the system can search, compare, synthesize, revise, and decide when the report is ready.

- Chinese documentation: [README_CN.md](./README_CN.md)

## What It Does

- Fetches recent papers from arXiv under configurable topic scopes
- Builds a larger exploration pool instead of locking the system into a tiny fixed batch
- Lets a main agent decide when to search more, use memory, call subagents, revise, and stop
- Produces a Chinese daily report in Markdown and PDF
- Optionally sends the report by email
- Stores lightweight memory across runs for seen papers, trend traces, and idea backlog

## Technical Approach

The system is built around a single autonomous orchestrator.

1. Fetch a broad candidate pool from arXiv.
2. Let the main agent decide how to explore and narrow down the pool.
3. Use role-based subagents for different research tasks.
4. Run quality checks after subagent outputs and before finalizing the report.
5. Render the final report to Markdown, PDF, and optional email delivery.

The available subagent roles include:

## Quick Start

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a local config file:

```bash
cp config.example.yaml config.yaml
```

Run a dry run:

```bash
python main.py --config config.yaml --once --dry-run
```

Run a real report:

```bash
python main.py --config config.yaml --once
```

Run in scheduler mode:

```bash
python main.py --config config.yaml
```

## Configuration

You only need a local `config.yaml` file. It is already ignored by Git and should not be committed.

The main sections are:

- `llm`: API key, base URL, model name
- `topics`: arXiv categories and topic keywords
- `arxiv`: candidate pool size and lookback window
- `scheduler`: run interval and exploration/analysis pool sizing
- `report`: agent step budget, editorial rounds, context budget
- `mail`: optional SMTP delivery settings

Recommended environment variables:

```bash
export MINIMAX_API_KEY="your-api-key"
export MAIL_USERNAME="your-mail-account"
export MAIL_PASSWORD="your-mail-password"
export MAIL_FROM_ADDR="your-mail-address"
```

## How To Adapt It

You can use this project for many different research domains by changing only the topic scope:

- adjust arXiv categories
- adjust include and exclude keywords
- add your own domain presets
- tune exploration pool size and agent step budget

The code is meant to support focused paper tracking rather than one specific research topic.

## Outputs

- Markdown reports in `reports/`
- PDF reports in `reports/`
- State memory in `data/state.json`
- Runtime traces in `runtime_logs/`

## Open-Source Notes

- Keep secrets in local `config.yaml` or environment variables.
- Add a `LICENSE` file before public release.
