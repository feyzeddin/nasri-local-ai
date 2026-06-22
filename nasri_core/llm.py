"""
Nasri — LLM köprüsü.
Soul'un ürettiği sistem promptunu alır, kullanıcı mesajıyla birlikte
Ollama'ya (yerel) gönderir, yanıtı döndürür.
Şimdilik tek sağlayıcı: Ollama. İleride Tier 2/3 (bulut) buraya eklenecek.
"""
import requests
from nasri_core import config, soul
from nasri_core.logger import get_logger

log = get_logger("nasri.llm")


class OllamaHatasi(Exception):
    """Ollama ile iletişimde sorun olduğunda fırlatılır."""
    pass


def yanit_al(kullanici_mesaji: str, gecmis: list | None = None) -> str:
    """
    Kullanıcı mesajını Ollama'ya gönderir, Nasri'nin yanıtını döndürür.

    gecmis: önceki konuşma turları [{"role": "user/assistant", "content": "..."}]
            None ise tek seferlik (bağlamsız) sohbet.
    """
    cfg = config.yukle()
    url = f"{cfg['ollama_url']}/api/chat"
    model = cfg["llm_model"]

    # Mesaj listesi: önce sistem promptu (soul), sonra geçmiş, sonra yeni mesaj
    mesajlar = [{"role": "system", "content": soul.sistem_promptu_olustur()}]
    if gecmis:
        mesajlar.extend(gecmis)
    mesajlar.append({"role": "user", "content": kullanici_mesaji})

    govde = {
        "model": model,
        "messages": mesajlar,
        "stream": False,   # şimdilik tam yanıt bekle (streaming sonra)
    }

    log.debug("Ollama'ya istek: model=%s, mesaj_sayisi=%d", model, len(mesajlar))
    try:
        cevap = requests.post(url, json=govde, timeout=120)
        cevap.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise OllamaHatasi("Ollama'ya baglanilamadi. Servis calisiyor mu? (systemctl status ollama)")
    except requests.exceptions.Timeout:
        raise OllamaHatasi("Ollama 120 saniyede yanit vermedi (model cok yavas olabilir).")
    except requests.exceptions.HTTPError as e:
        raise OllamaHatasi(f"Ollama HTTP hatasi: {e}")

    veri = cevap.json()
    metin = veri.get("message", {}).get("content", "").strip()
    if not metin:
        raise OllamaHatasi("Ollama bos yanit dondurdu.")

    log.info("Yanit alindi (%d karakter).", len(metin))
    return metin


# Doğrudan çalıştırılırsa: tek seferlik test sohbeti
if __name__ == "__main__":
    print("Nasri'ye bir sey sor (cikis: bos birak + Enter):")
    soru = input("Sen: ").strip()
    if soru:
        print("\nNasri dusunuyor...\n")
        try:
            print("Nasri:", yanit_al(soru))
        except OllamaHatasi as e:
            print("HATA:", e)
