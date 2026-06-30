# Douyin Industry Video Skill

This repository contains a Codex skill for extracting subtitles and metadata from Douyin-style short videos, then analyzing Chinese investment and industry-chain claims.

Skill path:

```text
.agents/skills/douyin-industry-video
```

## What It Does

- Parses Douyin reflow pages for metadata and exposed video URLs.
- Extracts burned-in Chinese subtitles with macOS Vision OCR.
- Cleans repeated OCR frames into Markdown and JSON transcripts.
- Guides industry-chain analysis for AI hardware, memory, semiconductor equipment, capex, and "who pays" order-chain claims.

## Main Use Cases

- "Get the full subtitles from this Douyin video."
- "Analyze this video's AI industry-chain logic."
- "Who is the real payer behind all these AI orders?"
- "Is this semiconductor / memory / equipment rally early, middle, or late cycle?"

## Notes

- OCR subtitles are machine-derived, not official platform transcripts.
- macOS Speech may require privacy permissions and is not the default path.
- Audio transcription requires either a local Whisper CLI or an OpenAI-compatible provider that supports audio transcription.
- The skill is research support, not personalized investment advice.
