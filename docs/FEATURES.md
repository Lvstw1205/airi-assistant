# Included functionality and setup requirements

| Area | Included in source | Additional setup |
| --- | --- | --- |
| Conversation and memory | Local chat, history, summaries and preferences | Ollama and a local model |
| Planner and agent roles | Tasks, registry, work records and review roles | Model for inference |
| Research desk | Evidence retrieval, source handling, reports and document tools | Internet for research; optional source APIs |
| PDF reports | Local output by default | Optional `AIRI_PDF_FONT` for an embeddable Unicode TTF |
| Voice | System speech, transcription and neural-voice workers | Apple Silicon for MLX; optional voice dependencies/models |
| Cameras | UVC/RTSP adapters, presence and hand logic | Device/FFmpeg; `requirements-camera.txt`; model installer |
| Telegram | Single-receiver command/status bridge | User-owned bot token and permitted chat setup |
| Stock101 | Full research/PAPER module and gated live adapter | Coinbase account/key only for private/live access |
| Distributed workers | Node discovery, job routing and local worker protocols | Explicit peer pairing; optional node requirements |
| Tim Works integration | Studio bridge | Separate Tim Works installation and explicit endpoint setup |
| Avatar | Original neutral SVG; VRM renderer | User-supplied licensed VRM/motion assets |
| Video/image production | Job contracts and provider adapters | Own tools/providers and licenses |

Optional voice setup on compatible Apple Silicon:

```bash
.venv/bin/python -m pip install -r requirements-voice.txt
.venv/bin/python scripts/download-voice.py
.venv/bin/python scripts/download-tts.py
```

These are explicit model downloads, separate from basic installation. Voice cloning reference
audio is never bundled. Distributed hardware, proprietary camera firmware and external provider
accounts are not included. Unsupported integrations should report unavailable, not completed.

Use `AIRI_TIMEZONE` for the local time zone. Weather is disabled until `AIRI_WEATHER_CITY`,
`AIRI_WEATHER_LAT` and `AIRI_WEATHER_LON` are set. Reports default to `data/reports`; configure
`AIRI_REPORTS_ROOT` and optionally `AIRI_REPORTS_MOUNT` for another destination. NAS/library
paths are opt-in via `AIRI_NAS_ROOT` and `AIRI_LIBRARY_ROOT`.
