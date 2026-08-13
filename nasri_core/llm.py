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
    # Tarih/saat sistem promptunda DEGIL, mesajin yaninda gonderilir.
    # Sistem promptu sabit kalinca Ollama onek onbellegi tutuyor (F1-23):
    # ~990 tokenlik girdi her turda yeniden islenmiyor.
    mesajlar.append({
        "role": "user",
        "content": f"[{soul.guncel_zaman_metni()}]\n\n{kullanici_mesaji}",
    })

    govde = {
        "model": model,
        "messages": mesajlar,
        "stream": False,   # şimdilik tam yanıt bekle (streaming sonra)
        # Model bellekte kalsın; her turda yeniden yüklenmesi 5-10 sn kaybettirir
        "keep_alive": cfg.get("llm_keep_alive", "30m"),
    }

    log.debug("Ollama'ya istek: model=%s, mesaj_sayisi=%d", model, len(mesajlar))
    try:
        cevap = requests.post(url, json=govde, timeout=180)
        cevap.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise OllamaHatasi("Ollama'ya baglanilamadi. Servis calisiyor mu? (systemctl status ollama)")
    except requests.exceptions.Timeout:
        raise OllamaHatasi("Ollama 180 saniyede yanit vermedi (model cok yavas olabilir).")
    except requests.exceptions.HTTPError as e:
        raise OllamaHatasi(f"Ollama HTTP hatasi: {e}")

    veri = cevap.json()
    _olcumleri_logla(veri)
    metin = veri.get("message", {}).get("content", "").strip()
    if not metin:
        raise OllamaHatasi("Ollama bos yanit dondurdu.")

    log.info("Yanit alindi (%d karakter).", len(metin))
    return metin


def isit() -> None:
    """
    Modeli Ollama'nın belleğine önceden yükler (ön ısıtma).
    Açılışta çağrılır ki ilk gerçek istek model yüklemesini beklemesin.
    """
    cfg = config.yukle()
    url = f"{cfg['ollama_url']}/api/chat"
    model = cfg["llm_model"]
    tutma = cfg.get("llm_keep_alive", "30m")
    log.info("Model on isitiliyor: %s (keep_alive=%s)", model, tutma)
    try:
        cevap = requests.post(
            url,
            json={
                # Gercek sistem promptuyla isitiyoruz ki onek onbellegi dolsun;
                # bos promptla isitmak ilk turu hizlandirmiyordu.
                "model": model,
                "messages": [
                    {"role": "system", "content": soul.sistem_promptu_olustur()},
                    {"role": "user", "content": "merhaba"},
                ],
                "stream": False,
                "keep_alive": tutma,
                "options": {"num_predict": 1},
            },
            timeout=300,
        )
        cevap.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise OllamaHatasi(f"Model on isitilamadi: {e}")
    log.info("Model bellekte hazir.")


def _olcumleri_logla(veri: dict) -> None:
    """Ollama'nin dondurdugu sureleri ayristirir (F1-23 teshisi icin)."""
    ns = 1_000_000_000
    yuk = veri.get("load_duration", 0) / ns
    g_say = veri.get("prompt_eval_count", 0)
    g_sure = veri.get("prompt_eval_duration", 0) / ns
    u_say = veri.get("eval_count", 0)
    u_sure = veri.get("eval_duration", 0) / ns
    log.info(
        "OLCUM | yukleme %.1fs | girdi %d tok / %.1fs (%.1f tok/s) | "
        "uretim %d tok / %.1fs (%.1f tok/s)",
        yuk,
        g_say, g_sure, (g_say / g_sure) if g_sure else 0.0,
        u_say, u_sure, (u_say / u_sure) if u_sure else 0.0,
    )


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
