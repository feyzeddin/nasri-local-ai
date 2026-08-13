"""
Nasri — Gizli anahtar yönetimi.
API anahtarları gibi hassas veriler secrets.json'da tutulur (git'e ASLA girmez).
config.py'den ayrıdır: genel ayarlar config.json'da, sırlar burada.
"""
import json
from nasri_core import paths
from nasri_core.logger import get_logger

log = get_logger("nasri.secrets")


class SecretsHatasi(Exception):
    """Gizli anahtar bulunamadığında veya okunamadığında fırlatılır."""
    pass


def yukle() -> dict:
    """secrets.json'u okur. Dosya yoksa boş sözlük döndürür (hata vermez)."""
    paths.ensure_dirs()
    if not paths.SECRETS_FILE.exists():
        log.debug("secrets.json bulunamadi, bos donduruluyor.")
        return {}
    with open(paths.SECRETS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def anahtar_al(isim: str, zorunlu: bool = False) -> str | None:
    """
    Tek bir gizli anahtarı okur (örn. 'groq_api_key').
    zorunlu=True ise ve anahtar yoksa SecretsHatasi fırlatır.
    """
    deger = yukle().get(isim)
    if zorunlu and not deger:
        raise SecretsHatasi(
            f"Gizli anahtar bulunamadi: '{isim}'. "
            f"{paths.SECRETS_FILE} dosyasina eklemelisin."
        )
    return deger
