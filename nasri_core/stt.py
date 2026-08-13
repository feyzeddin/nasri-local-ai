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
_client = None


class STTHatasi(Exception):
    """Ses tanımada sorun olduğunda fırlatılır."""
    pass


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
        subprocess.run(
            ["arecord", "-q", "-d", str(saniye), "-f", "S16_LE",
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
