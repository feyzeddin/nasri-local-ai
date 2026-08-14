"""
Nasri — Sesli sohbet döngüsü (F1-10).

Akış:  tetikleme -> dinle (VAD) -> STT -> LLM -> TTS -> tekrar bekle

Sabit süreli kayıt yerine basit bir enerji tabanlı VAD (Voice Activity
Detection) kullanılır: konuşma başlayınca kaydeder, sen susunca durur.
Böylece "5 saniye konuş" dayatması olmaz ve Groq'a gereksiz sessizlik
gönderilmez (hem hız hem kota kazancı).

Tetikleme modları:
  varsayılan : Enter tuşuna basınca dinlemeye geçer (yanlış tetikleme yok)
  --surekli  : sürekli dinler, ses duyunca kaydeder (wake word gelene kadar
               geçici çözüm; gürültülü ortamda yanlış tetiklenebilir)

Her aşamanın süresi ölçülür ve tur sonunda yazdırılır — F1-23 (gecikme
iyileştirmesi) için darboğazın nerede olduğunu görmek amacıyla.

Kullanım:
    python -m nasri_core.modules.sesli_sohbet
    python -m nasri_core.modules.sesli_sohbet --surekli --ekransiz
"""
import os
import subprocess
import sys
import tempfile
import time
import wave
from collections import deque

import numpy as np

from nasri_core import config, llm, stt, tts
from nasri_core.chat import Sohbet
from nasri_core.logger import get_logger

log = get_logger("nasri.sesli")

# --- Ses kaydı biçimi (Whisper'ın beklediği format) ---
ORNEK_HIZI = 16000              # 16 kHz
PARCA_MS = 30                   # her okuma parçası 30 ms
PARCA_ORNEK = ORNEK_HIZI * PARCA_MS // 1000
PARCA_BAYT = PARCA_ORNEK * 2    # 16-bit mono = örnek başına 2 bayt

# --- Kayıt aygıtı ---
# ÖNEMLİ: ALSA varsayılanına güvenmiyoruz. Bu sistemde varsayılan capture aygıtı
# tanımsız (asym capture slave yok) ve nasrispk girişi sürekli kırpıyor.
# Aygıt config.json'daki "ses_giris_aygiti" ile değiştirilebilir.
VARSAYILAN_AYGIT = "plughw:respeaker"

# --- VAD (konuşma algılama) ayarları ---
# Bu değerler config.json'dan geçersiz kılınabilir.
VARSAYILAN_VAD = {
    # "otomatik" = açılışta ortam gürültüsü ölçülür, eşik ona göre hesaplanır.
    # Sayı verilirse (örn. 500) o değer sabit kullanılır.
    "vad_esik": "otomatik",
    "vad_esik_carpani": 3.5,    # otomatik modda: taban gürültü x bu katsayı
    "vad_esik_alt_sinir": 200,  # otomatik modda eşik bunun altına inmesin
    "vad_baslangic_bekleme": 8.0,   # kimse konuşmazsa kaç sn sonra vazgeçilsin
    "vad_sessizlik": 1.2,       # konuşma bitti saymak için gereken sessizlik (sn)
    "vad_azami_kayit": 20.0,    # tek turda en fazla kayıt süresi (sn)
    "vad_on_tampon": 8,         # konuşma tespitinden önceki kaç parça saklansın
}

CIKIS_KELIMELERI = (
    "çık", "cik", "çıkış", "kapat", "görüşürüz", "gorusuruz",
    "hoşça kal", "hosca kal", "kapan",
)
SIFIRLA_KELIMELERI = ("sıfırla", "sifirla", "unut", "baştan başla", "bastan basla")


class SesliHata(Exception):
    """Sesli döngüde toparlanamayan bir sorun olduğunda fırlatılır."""
    pass


# ---------------------------------------------------------------- yardımcılar

def _vad_ayarlari() -> dict:
    """config.json'daki vad_* anahtarlarıyla varsayılanları birleştirir."""
    cfg = config.yukle()
    ayar = dict(VARSAYILAN_VAD)
    for anahtar in VARSAYILAN_VAD:
        if anahtar in cfg:
            ayar[anahtar] = cfg[anahtar]
    ayar["aygit"] = cfg.get("ses_giris_aygiti", VARSAYILAN_AYGIT)
    return ayar


def _rms(parca: bytes) -> float:
    """Ham 16-bit PCM parçasının ortalama enerjisini (RMS) döndürür."""
    if len(parca) < 2:
        return 0.0
    # float32'ye çeviriyoruz; int16 karesi alınırsa taşma olur
    ornekler = np.frombuffer(parca, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(ornekler ** 2)))


def _wav_yaz(pcm: bytes) -> str:
    """Ham PCM veriyi geçici bir WAV dosyasına yazar, yolunu döndürür."""
    fd, yol = tempfile.mkstemp(suffix=".wav", prefix="nasri_vad_")
    os.close(fd)
    with wave.open(yol, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(ORNEK_HIZI)
        w.writeframes(pcm)
    return yol


def _kayit_akisi(aygit: str) -> subprocess.Popen:
    """arecord'u ham akış modunda açar (stdout'tan parça parça okunur)."""
    komut = ["arecord", "-q", "-D", aygit, "-f", "S16_LE",
             "-r", str(ORNEK_HIZI), "-c", "1", "-t", "raw", "-"]
    try:
        return subprocess.Popen(
            komut, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        raise SesliHata("arecord bulunamadı (alsa-utils kurulu mu?).")


def taban_gurultu_olc(aygit: str, sn: float = 1.2) -> float:
    """
    Ortamın sessizlik seviyesini (taban gürültü RMS) ölçer.
    Otomatik eşik hesabı için açılışta bir kez çağrılır.
    """
    p = _kayit_akisi(aygit)
    seviyeler = []
    hedef = int(sn * 1000 / PARCA_MS)
    try:
        for _ in range(hedef):
            parca = p.stdout.read(PARCA_BAYT)
            if not parca or len(parca) < PARCA_BAYT:
                break
            seviyeler.append(_rms(parca))
    finally:
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                p.kill()
        if p.stdout:
            p.stdout.close()
        if p.stderr:
            p.stderr.close()

    if not seviyeler:
        raise SesliHata(
            f"'{aygit}' aygıtından veri okunamadı. "
            f"Aygıt adını kontrol edin (arecord -l)."
        )
    # Ortanca kullanıyoruz: tek tük çıt/tık sesleri ortalamayı bozmasın
    return float(np.median(seviyeler))


def esik_belirle(ayar: dict) -> float:
    """
    Kullanılacak RMS eşiğini döndürür.
    "otomatik" ise ortam gürültüsünü ölçüp hesaplar, değilse sabit değeri alır.
    """
    ham = ayar["vad_esik"]
    if isinstance(ham, (int, float)):
        return float(ham)

    taban = taban_gurultu_olc(ayar["aygit"])
    esik = max(
        float(ayar["vad_esik_alt_sinir"]),
        taban * float(ayar["vad_esik_carpani"]),
    )
    log.info("Taban gürültü RMS=%.0f -> eşik=%.0f", taban, esik)
    print(f"  Ortam gürültüsü: {taban:.0f} -> konuşma eşiği: {esik:.0f}")
    return esik


def dinle_vad(ayar: dict, sonsuz_bekle: bool = False,
              hazir_geri_cagirma=None) -> str | None:
    """
    Mikrofonu dinler; konuşma başlayınca kaydeder, sessizlik olunca durur.

    sonsuz_bekle=True ise konuşma başlayana kadar süresiz bekler
    (--surekli modu). False ise vad_baslangic_bekleme sonunda None döner.
    hazir_geri_cagirma: mikrofondan ilk veri geldiğinde çağrılır — arecord'un
    açılması ~250ms sürüyor ve o aralıkta konuşulursa ilk hece kaçıyor.

    Dönüş: WAV dosya yolu, ya da konuşma algılanmadıysa None.
    """
    esik = float(ayar["esik"])          # esik_belirle() tarafından hesaplanmış
    sessizlik_gerekli = float(ayar["vad_sessizlik"])
    azami = float(ayar["vad_azami_kayit"])
    baslangic_limiti = float(ayar["vad_baslangic_bekleme"])

    # Konuşmanın ilk hecesi kesilmesin diye tespitten önceki parçaları da tutarız
    on_tampon = deque(maxlen=int(ayar["vad_on_tampon"]))
    toplanan = bytearray()

    konusma_basladi = False
    sessiz_parca = 0
    sessiz_gereken_parca = int(sessizlik_gerekli * 1000 / PARCA_MS)
    azami_parca = int(azami * 1000 / PARCA_MS)
    baslangic_limit_parca = int(baslangic_limiti * 1000 / PARCA_MS)
    okunan_parca = 0

    p = _kayit_akisi(ayar["aygit"])
    try:
        while True:
            parca = p.stdout.read(PARCA_BAYT)
            if not parca or len(parca) < PARCA_BAYT:
                break
            okunan_parca += 1
            if okunan_parca == 1 and hazir_geri_cagirma:
                hazir_geri_cagirma()      # mikrofon gerçekten açıldı
            seviye = _rms(parca)

            if not konusma_basladi:
                on_tampon.append(parca)
                if seviye >= esik:
                    konusma_basladi = True
                    log.debug("Konuşma algılandı (RMS=%.0f).", seviye)
                    for onceki in on_tampon:
                        toplanan.extend(onceki)
                    on_tampon.clear()
                elif not sonsuz_bekle and okunan_parca >= baslangic_limit_parca:
                    log.debug("Başlangıç süresi doldu, konuşma yok.")
                    return None
                continue

            # Konuşma sürüyor
            toplanan.extend(parca)
            if seviye < esik:
                sessiz_parca += 1
                if sessiz_parca >= sessiz_gereken_parca:
                    log.debug("Sessizlik eşiği doldu, kayıt bitti.")
                    break
            else:
                sessiz_parca = 0

            if len(toplanan) // PARCA_BAYT >= azami_parca:
                log.info("Azami kayıt süresine ulaşıldı (%.0f sn).", azami)
                break
    finally:
        # arecord'u kesin olarak kapat — yoksa mikrofon meşgul kalır
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                p.kill()
        if p.stdout:
            p.stdout.close()
        if p.stderr:
            p.stderr.close()

    if not konusma_basladi or len(toplanan) < PARCA_BAYT * 5:
        return None
    return _wav_yaz(bytes(toplanan))


# Cümle sonu sayılan işaretler. Akışta bunlardan biri görülünce parça
# seslendirmeye gönderilir — böylece ses, yanıtın tamamı beklenmeden başlar.
CUMLE_SONU = ".!?…\n"


def _kesim_bul(metin: str) -> int | None:
    """Metindeki ilk cümle sonu konumunu döndürür (yoksa None)."""
    for i, karakter in enumerate(metin):
        if karakter not in CUMLE_SONU:
            continue
        # "14.46" gibi sayı/nokta birleşimlerini bölme
        if karakter == "." and i + 1 < len(metin) and metin[i + 1].isdigit():
            continue
        return i
    return None


def cumlelere_bol(parcalar):
    """
    LLM'den gelen metin parçalarını cümlelere böler (generator).
    Amaç ilk cümleyi mümkün olan en kısa sürede çıkarmak: seslendirme
    böylece üretim sürerken başlayabilir.
    """
    tampon = ""
    for parca in parcalar:
        tampon += parca
        while True:
            kesim = _kesim_bul(tampon)
            if kesim is None:
                break
            cumle = tampon[:kesim + 1].strip()
            tampon = tampon[kesim + 1:]
            if cumle:
                yield cumle
    if tampon.strip():
        yield tampon.strip()


def _durum(ekran, durum: str) -> None:
    """Ekran varsa durumu yazar. Ekran hatası döngüyü durdurmaz."""
    if ekran is None:
        return
    try:
        ekran.durum_yaz(durum)
    except Exception as e:
        log.warning("Ekran güncellenemedi (döngü devam ediyor): %s", e)


def _sureleri_yazdir(sureler: dict) -> None:
    """
    Aşama sürelerini tek satırda gösterir (F1-23 ölçümü).
    'düşünme' = konuşmaya başlayana kadar geçen bekleme; kullanıcının
    algıladığı gecikme budur, asıl iyileştirilmesi gereken sayı.
    """
    parcalar = [f"{ad} {sn:.1f}s" for ad, sn in sureler.items()]
    toplam = sum(sureler.values())
    satir = "  ⏱  " + " | ".join(parcalar) + f" | TOPLAM {toplam:.1f}s"
    print(satir)
    log.info("Süreler: %s", satir.strip())


def _isit(ekran) -> None:
    """
    Ollama modelini ve Piper sesini önceden belleğe alır.
    Yapılmazsa ilk tur 10+ saniye sürer ve kullanıcı 'bozuk' sanır.
    """
    print("Hazırlanıyor: model ve ses yükleniyor...")
    t0 = time.perf_counter()
    try:
        llm.isit()
    except Exception as e:
        print(f"  ! LLM ön ısıtma başarısız: {e}")
    try:
        tts.hazirla()
    except Exception as e:
        print(f"  ! TTS ön ısıtma başarısız: {e}")
    print(f"Hazır ({time.perf_counter() - t0:.1f}s).\n")


# ------------------------------------------------------------------- ana akış

def bir_tur(oturum: Sohbet, ekran, ayar: dict, surekli: bool) -> bool:
    """
    Tek bir konuşma turu yürütür.
    Dönüş: döngü devam edecekse True, kullanıcı çıkmak istediyse False.
    """
    sureler = {}

    # 1) Dinle
    _durum(ekran, "dinliyor")
    t0 = time.perf_counter()
    wav = dinle_vad(
        ayar, sonsuz_bekle=surekli,
        hazir_geri_cagirma=lambda: print("  ● dinliyorum", flush=True),
    )
    sureler["kayıt"] = time.perf_counter() - t0

    if wav is None:
        _durum(ekran, "bekliyor")
        if not surekli:
            print("  (ses algılanmadı)")
        return True

    # 2) Metne çevir
    _durum(ekran, "dusunuyor")
    print("  ...çözümleniyor", flush=True)
    t0 = time.perf_counter()
    try:
        metin = stt.cevir(wav, dil=config.deger_al("dil", "tr"))
    except stt.STTHatasi as e:
        print(f"  ! Ses tanıma hatası: {e}")
        _durum(ekran, "bekliyor")
        return True
    finally:
        try:
            os.remove(wav)
        except OSError:
            pass
    sureler["stt"] = time.perf_counter() - t0

    metin = (metin or "").strip()
    if not metin:
        print("  (boş çıktı — tekrar deneyin)")
        _durum(ekran, "bekliyor")
        return True

    print(f"\nSen: {metin}")

    # Sesli komutlar — LLM'e gitmeden yakalanır
    kucuk = metin.lower().rstrip(".!?")
    if any(k in kucuk for k in CIKIS_KELIMELERI):
        _durum(ekran, "konusuyor")
        try:
            tts.konus("Görüşürüz.")
        except Exception:
            pass
        return False
    if any(k in kucuk for k in SIFIRLA_KELIMELERI):
        oturum.sifirla()
        _durum(ekran, "konusuyor")
        try:
            tts.konus("Sohbet geçmişini temizledim.")
        except Exception:
            pass
        _durum(ekran, "bekliyor")
        print("  [geçmiş temizlendi]")
        return True

    # 3+4) Düşün ve seslendir — akış hâlinde, üst üste binerek.
    # İlk cümle hazır olur olmaz ses başlar; model geri kalanını üretmeye
    # devam ederken nasri çoktan konuşuyor olur.
    _durum(ekran, "dusunuyor")
    print("nasri: ", end="", flush=True)
    t0 = time.perf_counter()
    ilk_ses = {"sure": None}
    toplanan = []

    def _cumle_uretici():
        """Akıştan cümle üretir; ilk cümlede durumu 'konuşuyor'a çevirir."""
        for cumle in cumlelere_bol(oturum.mesaj_gonder_akis(metin)):
            if ilk_ses["sure"] is None:
                ilk_ses["sure"] = time.perf_counter() - t0
                _durum(ekran, "konusuyor")
            toplanan.append(cumle)
            print(cumle + " ", end="", flush=True)
            yield cumle

    try:
        tts.konus_akisi(_cumle_uretici())
    except llm.OllamaHatasi as e:
        print(f"\n  ! LLM hatası: {e}")
        _durum(ekran, "bekliyor")
        return True
    except tts.TTSHatasi as e:
        print(f"\n  ! Seslendirme hatası: {e}")
    print()

    if not toplanan:
        print("  (yanıt alınamadı)")
        _durum(ekran, "bekliyor")
        return True

    toplam = time.perf_counter() - t0
    dusunme = ilk_ses["sure"] if ilk_ses["sure"] is not None else toplam
    sureler["düşünme"] = dusunme        # ilk sese kadar geçen süre
    sureler["konuşma"] = toplam - dusunme

    _durum(ekran, "bekliyor")
    _sureleri_yazdir(sureler)
    return True


def calistir(surekli: bool = False, ekran_acik: bool = True) -> None:
    """Sesli sohbet döngüsünü başlatır."""
    ayar = _vad_ayarlari()

    ekran = None
    if ekran_acik:
        try:
            from nasri_core.modules.display import Ekran
            ekran = Ekran()
            ekran.baslat()
        except Exception as e:
            print(f"Ekran başlatılamadı, ekransız devam ediliyor: {e}")
            ekran = None

    # sesli=False: seslendirmeyi bu modül yapıyor (süre ölçümü ve durum kontrolü için)
    oturum = Sohbet(sesli=False, ekran=None)

    print("=" * 55)
    print("nasri — sesli sohbet")
    print(f"Mod: {'sürekli dinleme' if surekli else 'Enter ile tetikleme'}"
          f" | Ekran: {'açık' if ekran else 'kapalı'}")
    print(f"Mikrofon: {ayar['aygit']}")
    print("Çıkmak için 'görüşürüz' deyin veya Ctrl+C'ye basın.")
    print("=" * 55)

    _isit(ekran)

    # Eşiği ortama göre kalibre et (sessiz durun)
    print("Ortam gürültüsü ölçülüyor, bir saniye sessiz kalın...")
    try:
        ayar["esik"] = esik_belirle(ayar)
    except SesliHata as e:
        print(f"\nHATA: {e}")
        if ekran:
            ekran.kapat()
        return
    print()

    _durum(ekran, "bekliyor")

    try:
        while True:
            if not surekli:
                try:
                    girdi = input("\n[Enter] konuşmak için, 'q' çıkmak için: ").strip()
                except EOFError:
                    break
                if girdi.lower() in ("q", "cik", "çık", "exit"):
                    break
            if not bir_tur(oturum, ekran, ayar, surekli):
                break
    except KeyboardInterrupt:
        print("\n\nDurduruldu.")
    finally:
        _durum(ekran, "bekliyor")
        if ekran:
            try:
                ekran.kapat()
            except Exception as e:
                log.warning("Ekran kapatılamadı: %s", e)
        print("Görüşürüz!")


if __name__ == "__main__":
    calistir(
        surekli="--surekli" in sys.argv,
        ekran_acik="--ekransiz" not in sys.argv,
    )
