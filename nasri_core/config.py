"""
Nasri — Yapılandırma yönetimi.
Genel ayarları config.json'dan okur. Dosya yoksa varsayılanlarla oluşturur.
Gizli anahtarlar burada DEĞİL, secrets.json'da tutulur (güvenlik ayrımı).
"""
import json
from nasri_core import paths
from nasri_core.logger import get_logger

log = get_logger("nasri.config")

# Varsayılan ayarlar — config.json yoksa bunlar yazılır
DEFAULTS = {
    "dil": "tr",                      # arayüz/yanıt dili
    "kullanici_adi": "Feyzeddin",     # kişiselleştirme
    "llm_saglayici": "ollama",        # ollama | (sonra: groq, anthropic...)
    "llm_model": "aya-expanse:8b",    # 8GB RAM için Türkçe odaklı model
    "ollama_url": "http://localhost:11434",
    "yanit_uzunlugu": "normal",       # kisa | normal | detayli
    "zaman_dilimi": "Europe/Istanbul",
}


def yukle() -> dict:
    """Ayarları döndürür. Dosya yoksa varsayılanlarla oluşturup döndürür."""
    paths.ensure_dirs()

    if not paths.CONFIG_FILE.exists():
        log.info("config.json bulunamadi, varsayilanlarla olusturuluyor.")
        kaydet(DEFAULTS)
        return dict(DEFAULTS)

    with open(paths.CONFIG_FILE, "r", encoding="utf-8") as f:
        veri = json.load(f)

    # Yeni varsayılan eklendiyse eski dosyaya tamamla (ileri uyumluluk)
    guncellendi = False
    for anahtar, deger in DEFAULTS.items():
        if anahtar not in veri:
            veri[anahtar] = deger
            guncellendi = True
    if guncellendi:
        kaydet(veri)
        log.info("config.json eksik anahtarlarla guncellendi.")

    return veri


def kaydet(veri: dict) -> None:
    """Ayarları config.json'a yazar."""
    paths.ensure_dirs()
    with open(paths.CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=2)


def deger_al(anahtar: str, varsayilan=None):
    """Tek bir ayar değerini okur."""
    return yukle().get(anahtar, varsayilan)
