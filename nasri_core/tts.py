"""
Nasri — TTS (metinden sese) köprüsü.
Piper'ın yerel Python API'siyle metni sese çevirir, hoparlörden çalar.
Model bir kez belleğe yüklenir (singleton), sonraki çağrılar hızlıdır.
Ses çıkışı: ALSA varsayılan aygıtı (.asoundrc -> nasrispk).
"""
import os
import subprocess
from nasri_core import config, paths
from nasri_core.logger import get_logger

log = get_logger("nasri.tts")

# Piper'ın açılışta ürettiği zararsız GPU/drm uyarılarını bastır
os.environ.setdefault("ORT_LOGGING_LEVEL", "3")

# ALSA varsayilani bu sistemde bozuk (asym); cikis aygiti da acikca verilir.
VARSAYILAN_CIKIS = "plughw:nasrispk"

_voice = None  # yüklü PiperVoice (bellekte tutulur)


class TTSHatasi(Exception):
    """Ses sentezinde sorun olduğunda fırlatılır."""
    pass


def _model_yolu() -> str:
    """config'teki model adından .onnx dosya yolunu üretir."""
    cfg = config.yukle()
    model_adi = cfg["tts_model"]
    yol = paths.VOICES_DIR / f"{model_adi}.onnx"
    if not yol.exists():
        raise TTSHatasi(
            f"Ses modeli bulunamadi: {yol}\n"
            f"Indirmek icin: python -m piper.download_voices {model_adi} "
            f"--data-dir {paths.VOICES_DIR}"
        )
    return str(yol)


def _sesi_yukle():
    """PiperVoice'u belleğe yükler (yalnızca ilk çağrıda)."""
    global _voice
    if _voice is not None:
        return _voice
    try:
        from piper import PiperVoice
    except ImportError:
        raise TTSHatasi("piper-tts kurulu degil. (pip install piper-tts)")

    yol = _model_yolu()
    log.info("Piper ses modeli yukleniyor: %s", yol)
    _voice = PiperVoice.load(yol)
    log.info("Ses modeli hazir.")
    return _voice


def konus(metin: str) -> None:
    """Metni sese çevirir ve hoparlörden çalar (bloklar; bitince döner)."""
    metin = (metin or "").strip()
    if not metin:
        return

    from piper import SynthesisConfig
    cfg = config.yukle()
    voice = _sesi_yukle()

    syn = SynthesisConfig(
        length_scale=float(cfg.get("tts_hiz", 1.0)),
        volume=float(cfg.get("tts_ses_seviyesi", 1.0)),
    )

    log.debug("Seslendiriliyor (%d karakter).", len(metin))

    # aplay'i ham 16-bit mono akış için aç; Piper parçalarını borudan besle
    try:
        cikis = cfg.get("ses_cikis_aygiti", VARSAYILAN_CIKIS)
        aplay = subprocess.Popen(
            ["aplay", "-D", cikis, "-r", "22050", "-f", "S16_LE",
             "-t", "raw", "-q", "-"],
            stdin=subprocess.PIPE,
        )
    except FileNotFoundError:
        raise TTSHatasi("aplay bulunamadi (alsa-utils kurulu mu?).")

    try:
        for chunk in voice.synthesize(metin, syn_config=syn):
            aplay.stdin.write(chunk.audio_int16_bytes)
        aplay.stdin.close()
        aplay.wait()
    except BrokenPipeError:
        raise TTSHatasi("Ses cikisi kesildi (aplay kapandi).")
    finally:
        if aplay.poll() is None:
            aplay.terminate()

    log.info("Seslendirme tamam.")


def hazirla() -> None:
    """Ses modelini önceden belleğe yükler (ilk konuşmadaki gecikmeyi önler)."""
    _sesi_yukle()


# Doğrudan çalıştırılırsa: hızlı test
if __name__ == "__main__":
    konus("Merhaba. Ben Nasrî. Ses modülüm çalışıyor.")
