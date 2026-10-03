---
name: douyin-industry-video
description: Extract subtitles and metadata from Douyin or short-video links, then analyze investment or industry-chain claims in Chinese. Use when the user shares a Douyin/TikTok-style video link or downloaded video and asks to get complete subtitles, summarize the video, analyze AI/semiconductor/memory/order logic, identify who pays, judge cycle stage, or turn the workflow into reusable research.
---

# Douyin Industry Video

Use this skill to turn a short-video link into a verifiable transcript and an industry-research answer. Default to Chinese replies.

Paths like `scripts/...` are relative to this skill's folder (`.agents/skills/douyin-industry-video` in this repository).

## Workflow

1. **Read local project context first** when available:
   - Follow the current workspace's `AGENTS.md`, `CLAUDE.md`, or equivalent instructions.
   - If the user maintains a research vault or durable notes, read the relevant investing, industry-chain, AI hardware, memory, orders, or "who pays" notes before analysis.
   - If no durable context exists, continue with the built-in framework in `references/analysis-framework.md`.
2. **Get the video.** If the user already provided a local video, skip to step 3. Douyin's video API is signed inside the browser, so a real browser reads the data and the script downloads:
   1. `python3 scripts/fetch_douyin_video.py "<link or pasted share text>"` resolves the video id (short links too) and prints `page_url`.
   2. Open `page_url` (`https://www.douyin.com/video/<id>`) in a real browser your agent can drive: for example Claude Code's browser pane, Claude in Chrome, a Codex browser or computer-use tool, or a Playwright CLI `eval` (the Codex and Playwright routes are untested; ask the user before installing any browser tooling). Wait until the player has loaded; a login popup can stay open. If a captcha or verification appears, stop and ask the user to complete it themselves. Never automate it.
   3. Evaluate the whole of `scripts/douyin_page_probe.js` in that tab and save the returned object as `probe.json`. It sends no requests; it reads the video object the page already loaded. On `ok: false`, follow its `error`.
   4. `python3 scripts/fetch_douyin_video.py <id> --probe-json probe.json --out-dir <work>` writes `<work>/dy-<id>.metadata.json` (title, author, statistics, Douyin AI chapters) and reports file name, source and size without downloading.
   5. Tell the user the file name, source and size, and download only after they agree: rerun with `--download` (default 1080p; `--ratio 720p` or `540p` is smaller).
   - If the probe cannot find the data (Douyin changed its page), use the browser's own view instead: read the `aweme/detail` response from the page's network log for title, author, statistics and chapters, and take `document.querySelector('video').currentSrc`, a `*.douyinvod.com` mp4 link that expires after a few hours. Check its size with `curl -sIL -e https://www.douyin.com/ -A "<desktop browser UA>" "<link>"`, ask the user, then download with the same Referer and UA (without the Referer the CDN answers 403).
   - Without any drivable browser, ask the user for a local video file instead.
3. **Get subtitles in this order**:
   - Official subtitles first: check the probe's `subtitle_hints` (if non-empty, inspect those fields for caption URLs; the test videos had none, so this path is unverified) and the web player's subtitle menu. A menu with only an "off" entry means no official subtitles.
   - Burned-in subtitles: `swift scripts/ocr_burned_subtitles.swift <video.mp4> <raw.jsonl>`. It finds the subtitle band itself for landscape and portrait videos and prints it, e.g. `OCR band 0.823-1.0 of height (auto)`; a 6-10 minute video takes about 2 minutes. If the band looks wrong, rerun with `--band TOP:BOTTOM` (fractions of frame height from the top, e.g. `0.84:1.0`).
   - On-screen text (data cards, slides, charts; numbers there are often the evidence): scan the rest of the frame with a second pass, `swift scripts/ocr_burned_subtitles.swift <video.mp4> <screen-raw.jsonl> --band 0:0.84 --interval 2` (about 35 s for 6 minutes), then `python3 scripts/clean_ocr_subtitles.py <screen-raw.jsonl> <screen.md> --screen`. Use the band that excludes the subtitles; check numbers and units against the video.
   - Clean: `python3 scripts/clean_ocr_subtitles.py <raw.jsonl> <transcript.md> --json <transcript.json>`. Read its one-line summary: `mode` (bilingual / zh / en), `coverage`, `gaps_over_8s` (check those stretches against frames), `static_overlays_dropped`, `overlay_words_removed`, `rows_read_through_overlay`.
     - `--industry`: opt-in OCR fixes for Chinese AI / semiconductor / memory videos (A1→AI, 肉存→内存, trailing sticker noise).
     - `--strip REGEX`: remove a creator watermark glued into the text, e.g. `--strip 'MyChannel\w*'`; `--drop REGEX` drops whole boxes. Both also work with `--screen`.
   - If OCR quality is weak and an OpenAI audio key or local `whisper` CLI is available, transcribe audio and cross-check. Never print keys or save secrets.
   - `chapter_abstract` / `chapters` in the metadata are Douyin's AI summary: a structure reference, not the creator's words.
4. **State transcript confidence**:
   - Say whether the transcript is official, audio-transcribed, or OCR-derived.
   - For OCR, mark it as machine extracted from burned subtitles and note likely OCR errors; ⚠ rows were low-confidence or read through a watermark.
5. **Analyze the video**:
   - Separate `video claim -> evidence -> inference -> risk`.
   - For industry-chain topics, use `天道产业链版` completeness: reality check, chain map, true bottleneck, company mapping, revenue/profit elasticity, event energy, falsification, tracking metrics, unresolved checks.
   - For "AI chain all have orders / who pays" claims, apply the sponsor chain:
     `hyperscaler / AI cloud capex -> GPU / ASIC -> TSMC / advanced packaging -> HBM / server DRAM / SSD -> equipment / materials / power / optical interconnect`.
6. **Clean up downloaded video**:
   - Remove an exact task-owned download only when cleanup is already authorized. Otherwise retain it and report its location when useful; cleanup is not a prerequisite for delivering the transcript and analysis.
   - Keep metadata, OCR raw subtitles, cleaned transcript, and analysis notes when they are useful; do not delete user-provided local videos.
   - If extraction or analysis fails, report the completed portion and exact blocker. Partial-download deletion follows the same authorization boundary; do not claim success or delete user material.
7. **Memory closeout**:
   - If a reusable framework, trigger, or follow-up is created, update the user's configured durable memory or project notes when allowed.
   - Do not store raw chat logs, secrets, account details, exact personal holdings, or irrelevant one-off content.

## Practical Rules

- Do not pretend to have watched or transcribed a video if only metadata was available.
- Do not bypass captchas or reverse-engineer Douyin request signatures; signed requests stay inside the real browser.
- Prefer direct evidence: transcript, official filings, earnings calls, company press releases, and current market data.
- Browse for current facts when the answer depends on recent financials, capex guidance, orders, prices, or stock-market moves.
- For investment answers, do not provide buy/sell instructions. Separate industry quality, cycle stage, valuation/timing, and position risk.
- Give numeric event energy when relevant, for example `短线事件能量 86/100，中期兑现能量 74/100`.

## Script Notes

- `fetch_douyin_video.py` (Python 3.9+, standard library only) never calls Douyin's signed APIs. It downloads through `aweme.snssdk.com/aweme/v1/play/?video_id=<uri>`, which redirects to a `*.douyinvod.com` mp4, and falls back to the probe's signed CDN link, which expires after a few hours. Without `--download` it only writes metadata and reports the size.
- `douyin_page_probe.js` is read-only: it finds the video object in the page's React props and returns about 3 KB of JSON, or `ok: false` with the reason (page not loaded, captcha shown). In the metadata, `source_resolution` is the uploaded original (can be 4K); the file actually downloaded is described in `download.stream`.
- `ocr_burned_subtitles.swift` uses macOS AVFoundation + Vision (macOS 13+, no installs) on full-resolution frames. Raw JSONL starts with a `{"meta": ...}` line; each box's `bbox` is `[x, y, w, h]` normalized to the full frame, origin top-left.
- `clean_ocr_subtitles.py` keeps horizontally centered boxes, splits Chinese and Latin lines, drops static overlays (watermarks, diagram labels), demotes boxes a moving watermark passes over, groups consecutive frames into lines, and pairs bilingual lines by time. With `--screen` it instead lists the on-screen text of each card in reading order. It also reads raw files from the pre-2026-10 OCR script.
