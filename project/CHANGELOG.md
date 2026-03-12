# Changelog

## 0.3.24 - 2026-03-12

### Added
- `model_manager.py`: Adaptif model araştırma zamanlayıcısı — güncelleme bulunamazsa aralık uzar (1g→4g→7g→14g), güncelleme bulununca 1 güne sıfırlanır.
- `model_manager.py`: `record_research_result()` — araştırma sonucunu ve bir sonraki aralığı `model_research_state.json`'a yazar.
- `model_manager.py`: `get_next_check_info()` — bir sonraki kontrolün zamanını döner.
- `model_manager.py`: `_detect_user_language()` artık konum önbelleğinden ülke kodunu okuyarak dili tahmin ediyor (50+ ülke→dil eşleştirmesi).
- `model_manager.py`: `_available_ram_gb()` artık Linux/macOS/Windows cross-platform.
- `model_manager.py`: OLLAMA_MODELS listesine `qwen3:4b`, `aya-expanse:8b`, `gemma3:4b` eklendi.
- `model_manager.py`: `_ollama_pull()` artık timeout yok — model boyutu ne olursa olsun bekler.
- `service.py`: Sabit 24h interval yerine `should_research_models()` adaptive interval kullanıyor.
- `install.sh`: Varsayılan model `llama3` → `qwen3:4b` (2.5GB, 119 dil, Türkçe 9/10).
- `install.sh`: `ollama pull` zaman aşımı yok; başarısız olursa 3 kez 30s arayla tekrar dener.


## 0.3.23 - 2026-03-12

### Added
- `install.sh`: Root/sudo zorunluluğu — root değilse `exec sudo -E` ile otomatik yeniden başlatır; sudo yoksa kullanıcıyı yönlendirir.
- `install.sh`: Sudoers kuralına `timedatectl set-timezone/set-ntp`, `ntpdate`, `chronyc makestep` eklendi (şifresiz saat senkronu).
- `install.sh`: Kurulum sonu "Saat dilimi ve sistem saati doğrulama" adımı — saat dilimi UTC kalırsa Nasri'nin konum tespiti tamamlanana kadar bekler ve otomatik uygular.
- `device_auth.py`: `_sudoers_content()` aynı zaman senkronu komutlarını içerecek şekilde güncellendi.
- `time_sync.py`: `_sudo_run()` yardımcı fonksiyonu — her komutu önce doğrudan, başarısız olursa `sudo -n` ile dener.
- `time_sync.py`: `_try_fix_timezone()` artık parametrik (IANA timezone adı alır), cross-platform (Linux/macOS/Windows), 50+ timezone için IANA→Windows eşleştirme tablosu eklendi.
- `location.py`: `_apply_timezone()` artık OS sistem saat dilimini de `_try_fix_timezone()` ile güncelliyor.

### Changed
- `time_sync.py`: `_try_fix_system_clock()` artık `_sudo_run()` kullanıyor — `timedatectl`, `ntpdate`, `chronyc` komutları root olmadan da denenebiliyor.
- `time_sync.py`: `ensure_time_accurate()` UTC tespitinde konum önbelleğinden timezone okuyarak hardcoded "Europe/Istanbul" yerine gerçek konuma göre düzeltiyor.


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
