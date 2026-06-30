---
name: douyin-industry-video
description: Extract subtitles and metadata from Douyin or short-video links, then analyze investment or industry-chain claims in Chinese. Use when the user shares a Douyin/TikTok-style video link or downloaded video and asks to get complete subtitles, summarize the video, analyze AI/semiconductor/memory/order logic, identify who pays, judge cycle stage, or turn the workflow into reusable research.
---

# Douyin Industry Video

Use this skill to turn a short-video link into a verifiable transcript and an industry-research answer. Default to Chinese replies.

## Workflow

1. **Read local project context first** when available:
   - Follow the current workspace's `AGENTS.md`, `CLAUDE.md`, or equivalent instructions.
   - If the user maintains a research vault or durable notes, read the relevant investing, industry-chain, AI hardware, memory, orders, or "who pays" notes before analysis.
   - If no durable context exists, continue with the built-in framework in `references/analysis-framework.md`.
2. **Fetch the video**:
   - For a Douyin URL, run `scripts/fetch_douyin_video.py <url> --out-dir work/video`.
   - If the user already provided a local video, skip fetch and use that file.
3. **Get subtitles in this order**:
   - Use official page metadata or subtitle fields if present.
   - If there are burned-in subtitles, run `scripts/ocr_burned_subtitles.swift <video.mp4> <raw.jsonl> 1`.
   - Clean OCR with `scripts/clean_ocr_subtitles.py <raw.jsonl> <transcript.md> --json <transcript.json>`.
   - If OCR quality is weak and an OpenAI audio key or local `whisper` CLI is available, transcribe audio and cross-check. Never print keys or save secrets.
4. **State transcript confidence**:
   - Say whether the transcript is official, audio-transcribed, or OCR-derived.
   - For OCR, mark it as machine extracted from burned subtitles and note likely OCR errors.
5. **Analyze the video**:
   - Separate `video claim -> evidence -> inference -> risk`.
   - For industry-chain topics, use `天道产业链版` completeness: reality check, chain map, true bottleneck, company mapping, revenue/profit elasticity, event energy, falsification, tracking metrics, unresolved checks.
   - For "AI chain all have orders / who pays" claims, apply the sponsor chain:
     `hyperscaler / AI cloud capex -> GPU / ASIC -> TSMC / advanced packaging -> HBM / server DRAM / SSD -> equipment / materials / power / optical interconnect`.
6. **Memory closeout**:
   - If a reusable framework, trigger, or follow-up is created, update the user's configured durable memory or project notes when allowed.
   - Do not store raw chat logs, secrets, account details, exact personal holdings, or irrelevant one-off content.

## Practical Rules

- Do not pretend to have watched or transcribed a video if only metadata was available.
- Prefer direct evidence: transcript, official filings, earnings calls, company press releases, and current market data.
- Browse for current facts when the answer depends on recent financials, capex guidance, orders, prices, or stock-market moves.
- For investment answers, do not provide buy/sell instructions. Separate industry quality, cycle stage, valuation/timing, and position risk.
- Give numeric event energy when relevant, for example `短线事件能量 86/100，中期兑现能量 74/100`.

## Script Notes

- `fetch_douyin_video.py` uses mobile user-agent HTML parsing and downloads the reflow video when Douyin exposes `play_addr`.
- `ocr_burned_subtitles.swift` uses macOS AVFoundation and Vision. It requires no global install but only works on macOS.
- `clean_ocr_subtitles.py` filters the subtitle band, deduplicates repeated OCR frames, and outputs Markdown plus optional JSON.
