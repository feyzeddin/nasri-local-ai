# Changelog

## 0.2.0 - 2026-03-09

### Added
- Telegram messaging bridge (`/messaging/telegram/webhook`) with owner pairing flow.
- `nasri telegram-setup` command to collect Telegram bot settings, write them to `.env`, and optionally register webhook.
- Update manifest support (`UPDATE_MANIFEST.json`) to define dependency/install steps per release.

### Changed
- Auto-update now uses `git pull --ff-only origin main` (no hard reset).
- Auto-update syncs missing keys from `.env.example` into `.env`.
- Messaging replies now use model routing fallback: local -> free -> paid.
- Natural-language maintenance actions over messaging (e.g. run maintenance).

### Dependency / Requirement Notes
- Python dependencies are installed from `project/nasri-core/requirements.txt` during update.
- Editable package install is applied for `project/nasri-core`.
- Service process auto-restarts itself after successful update.
