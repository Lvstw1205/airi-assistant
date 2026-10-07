# Architecture

The loopback Python host serves the browser workspace and authenticated JSON routes.
Feature modules use a local data directory with SQLite records and configuration files.
The LLM client defaults to Ollama's OpenAI-compatible endpoint. Role prompts and schemas
describe agent responsibilities; code implements execution limits and permission boundaries.

Research modules retain evidence, reports and missing-data states. Stock101 has separate
paper/live stores and supervisors. Camera and voice workers are optional. Telegram and
node services operate only after their own connection setup. Shared databases must remain
on a suitable local filesystem; network peers exchange job requests rather than a live DB.

The community launcher defaults to port 8766 and an independent data directory. It does not
migrate another installation or read its account keys. Test mode is `run.py --standby`.
