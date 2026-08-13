"""
Nasri — STT (sesten metne) köprüsü.
Mikrofondan ses kaydeder, Groq Whisper (large-v3-turbo) ile Türkçe metne çevirir.
Kayıt: arecord (ALSA varsayılan giriş = respeaker). Bulut tabanlı, internet gerekir.
"""
import subprocess
import tempfile
import os
from nasri_core import config, secrets
from nasri_core.logger import get_logger

log = get_logger("nasri.stt")

GROQ_MODEL = "whisper-large-v3-turbo"
# ALSA varsayilan capture aygiti bu sistemde tanimsiz; aygit acikca verilir.
VARSAYILAN_AYGIT = "plughw:respeaker"
_client = None


class STTHatasi(Exception):
    """Ses tanımada sorun olduğunda fırlatılır."""
    pass


# Whisper sessizlikte/gurultude egitim verisindeki altyazi imzalarini uydurur.
# Bunlar kullaniciya ait degil; LLM'e gonderilmemeli.
HALUSINASYONLAR = (
    "altyazi m.k.", "altyazi mk", "altyazi", "altyazilar",
    "abone olmayi unutmayin", "izlediginiz icin tesekkurler",
    "izlediginiz icin tesekkur ederim", "bu videoda",
    "kanalima abone olun", "bir sonraki videoda gorusmek uzere",
    "altyazi ve ceviri", "turkce altyazi", "betimleme",
    "thanks for watching", "thank you", "you",
)


def _sadelestir(metin: str) -> str:
    """Karsilastirma icin metni sadelestirir (Turkce harfler ASCII'ye)."""
    esle = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosuCGIOSUaiu")
    sade = metin.translate(esle).lower().strip()
    return "".join(k for k in sade if k.isalnum() or k.isspace()).strip()


def halusinasyon_mu(metin: str) -> bool:
    """Tanınan metnin Whisper uydurmasi olup olmadigini soyler."""
    sade = _sadelestir(metin)
    # "Ne?", "Kim?" gibi kisa ama gecerli sorular elenmemeli;
    # yalnizca tek harf/bos ciktiyi gurultu sayiyoruz.
    if len(sade) < 2:
        return True
    return any(sade == h or sade.startswith(h) for h in
               (_sadelestir(x) for x in HALUSINASYONLAR))


def _istemci():
    """Groq istemcisini döndürür (ilk çağrıda oluşturur)."""
    global _client
    if _client is not None:
        return _client
    try:
        from groq import Groq
    except ImportError:
        raise STTHatasi("groq paketi kurulu degil. (pip install groq)")
    anahtar = secrets.anahtar_al("groq_api_key", zorunlu=True)
    _client = Groq(api_key=anahtar)
    return _client


def kaydet(saniye: int = 5, dosya: str | None = None) -> str:
    """Mikrofondan `saniye` kadar kayıt alır, WAV dosya yolunu döndürür."""
    if dosya is None:
        fd, dosya = tempfile.mkstemp(suffix=".wav", prefix="nasri_stt_")
        os.close(fd)
    log.debug("Kayit basliyor (%d sn): %s", saniye, dosya)
    # 16kHz mono — Whisper'ın beklediği format (gereksiz veri göndermeyiz)
    try:
        aygit = config.deger_al("ses_giris_aygiti", VARSAYILAN_AYGIT)
        subprocess.run(
            ["arecord", "-q", "-D", aygit, "-d", str(saniye), "-f", "S16_LE",
             "-r", "16000", "-c", "1", dosya],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise STTHatasi(f"arecord kayit hatasi: {e}")
    except FileNotFoundError:
        raise STTHatasi("arecord bulunamadi (alsa-utils kurulu mu?).")
    return dosya


def cevir(wav_yolu: str, dil: str = "tr") -> str:
    """WAV dosyasını Groq Whisper ile metne çevirir."""
    client = _istemci()
    log.debug("Groq'a gonderiliyor: %s", wav_yolu)
    try:
        with open(wav_yolu, "rb") as f:
            sonuc = client.audio.transcriptions.create(
                file=(os.path.basename(wav_yolu), f.read()),
                model=GROQ_MODEL,
                language=dil,
                temperature=0.0,
            )
    except Exception as e:
        raise STTHatasi(f"Groq ses tanima hatasi: {e}")
    metin = (sonuc.text or "").strip()
    log.info("Tanindi (%d karakter): %s", len(metin), metin[:60])
    if halusinasyon_mu(metin):
        log.info("Halusinasyon filtresi elendi: %r", metin)
        return ""
    return metin


def dinle(saniye: int = 5) -> str:
    """Kaydet + çevir tek adımda. Geçici dosyayı siler. Tanınan metni döndürür."""
    cfg = config.yukle()
    dil = cfg.get("dil", "tr")
    wav = kaydet(saniye)
    try:
        return cevir(wav, dil=dil)
    finally:
        try:
            os.remove(wav)
        except OSError:
            pass


# Doğrudan çalıştırılırsa: 5 saniye kaydet ve metni göster
if __name__ == "__main__":
    print("5 saniye konus...")
    print("Tanindi:", dinle(5))
