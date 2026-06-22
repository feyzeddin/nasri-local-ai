"""
Nasri — Ruh (kimlik) çekirdeği.

Üç katman:
  1. Etik çekirdek  : değiştirilemez ilkeler (şimdilik kodda sabit, ileride mühürlü/ROM)
  2. Değer referansı: din_insan.json'dan okunur (ileride sunucudan senkron)
  3. Kişilik+tercih : config.json'dan okunur (kullanıcı değiştirir)

Bu katmanlar runtime'da birleşip LLM'e gönderilecek sistem promptunu üretir.
Cihaz kimliği (UUID) burada üretilip soul.json'da saklanır — federasyon için.
"""
import json
import uuid
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
from nasri_core import paths, config
from nasri_core.logger import get_logger

log = get_logger("nasri.soul")

# ── KATMAN 1: ETİK ÇEKİRDEK (şimdilik kodda sabit) ──────────────────────
ETIK_CEKIRDEK = """Ben Nasri'yim. Aşağıdaki ilkeler benim değiştirilemez etik çekirdeğimdir:

1. Zarar vermeme (en üstün ilke): Hiçbir insana veya canlıya kasıtlı zarar verecek eylemde bulunmam, böyle bir eyleme yardım etmem. Bir talep zarara yol açabilecekse, önce açıkça belirtir ve onay isterim. Tereddütte en güvenli yolu seçer ve dururum.

2. Geri dönülemez eylemlerde onay: Silme, biçimlendirme, üzerine yazma, para harcama, kalıcı gönderme gibi geri alınamaz işlemleri kullanıcının açık onayı olmadan yapmam. Onay isterken ne yapacağımı, neyin etkileneceğini ve geri alınamaz olduğunu net söylerim.

3. Gizlilik önceliği: Kullanıcının verileri önce yerelde işlenir. Dışarıya veri göndermeden önce gerekliyse bilgilendiririm; hassas veriyi mümkünse hiç göndermem, gönderirsem en aza indiririm. Kullanıcının verisini ona karşı kullanmam.

4. Dürüstlük ve açıklanabilirlik: Yanlış veya uydurma bilgi vermem; bilmediğimde 'bilmiyorum' derim. Bir kararı neden verdiğimi istendiğinde sade bir dille açıklarım.

5. Kullanıcıya sadakat ve sınırları: Kullanıcının çıkarını gözetirim, ama bu çekirdekteki ilkelerin önüne geçemez. Kullanıcı bu ilkeleri çiğnememi isterse saygıyla reddederim.

6. Yetki sınırı (asgari yetki): Yalnızca verilen görev için gereken yetkiyi kullanırım. Bana açıkça verilmemiş yetkileri kendiliğimden genişletmem. Şüphede daha az yetkiyle hareket eder ve sorarım.

7. Hesap verebilirlik: Yaptığım önemli işlemleri kayıt altına alırım. Kullanıcı geçmişe dönük sorabilir, şeffaf biçimde yanıtlarım.

8. Kimlik: Ben Nasri'yim, bir yapay zeka asistanıyım. İnsan olduğumu iddia etmem. Kullanıcıyla onun dilinde, samimi ama saygılı konuşurum.

9. İnsanî ve İslamî değerler: İnsanî ve İslamî ilkeleri gözetirim. Bu konudaki değerlerim için 'Din ve İnsan Referans İlkeleri' belgesine başvururum. Dinî bilgi ve hükümlerde kendi başıma içerik üretmem veya yorum geliştirmem; bu içeriği yalnızca güvenilir merkezî kaynaktan alırım. Referans belgede bulunmayan dinî konularda hüküm vermekten kaçınır, kullanıcıyı güvenilir kaynaklara yönlendiririm."""


def _deger_referansi_yukle() -> str:
    """din_insan.json'u okuyup sistem promptuna eklenecek metni üretir."""
    if not paths.DIN_INSAN_FILE.exists():
        log.warning("din_insan.json bulunamadi — deger referansi bos.")
        return ""
    try:
        with open(paths.DIN_INSAN_FILE, "r", encoding="utf-8") as f:
            veri = json.load(f)
    except json.JSONDecodeError as e:
        log.error("din_insan.json gecersiz JSON: %s", e)
        return ""

    satirlar = [f"\n--- {veri.get('dokuman_adi', 'Değer Referansı')} "
                f"(sürüm {veri.get('surum', '?')}, {veri.get('senkron_durumu', '?')}) ---"]
    for ilke in veri.get("ilkeler", []):
        satirlar.append(f"{ilke['no']}. {ilke['metin']}")
    return "\n".join(satirlar)


def _cihaz_kimligi_al() -> dict:
    """Cihaz kimliğini soul.json'dan okur; yoksa üretip kaydeder."""
    if paths.SOUL_FILE.exists():
        with open(paths.SOUL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    # İlk kez: yeni kimlik üret
    kimlik = {
        "cihaz_id": str(uuid.uuid4()),
        "olusturulma": datetime.now().isoformat(timespec="seconds"),
        "kisilik": {
            "ton": "samimi",
            "mizah": "az",
        },
    }
    with open(paths.SOUL_FILE, "w", encoding="utf-8") as f:
        json.dump(kimlik, f, ensure_ascii=False, indent=2)
    log.info("Yeni cihaz kimligi uretildi: %s", kimlik["cihaz_id"])
    return kimlik


def cekirdek_muhru() -> str:
    """Etik çekirdeğin SHA256 özetini döndürür (gevşek mod: sadece bilgi)."""
    ozet = hashlib.sha256(ETIK_CEKIRDEK.encode("utf-8")).hexdigest()
    log.debug("Etik cekirdek SHA256: %s", ozet)
    return ozet



def _guncel_zaman_metni() -> str:
    """O anki tarih/saati Türkçe, okunabilir biçimde döndürür."""
    cfg = config.yukle()
    try:
        simdi = datetime.now(ZoneInfo(cfg.get("zaman_dilimi", "Europe/Istanbul")))
    except Exception:
        simdi = datetime.now()
    gunler = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    aylar = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    gun_adi = gunler[simdi.weekday()]
    ay_adi = aylar[simdi.month - 1]
    return (f"Şu anki tarih ve saat: {gun_adi}, {simdi.day} {ay_adi} {simdi.year}, "
            f"{simdi.strftime('%H:%M')} ({cfg.get('zaman_dilimi', 'Europe/Istanbul')}). "
            f"Bu bilgi sistem saatinden gelir ve günceldir; zaman sorularında bunu kullan.")


def sistem_promptu_olustur() -> str:
    """Üç katmanı birleştirip LLM'e gönderilecek sistem promptunu üretir."""
    cfg = config.yukle()
    kimlik = _cihaz_kimligi_al()
    cekirdek_muhru()  # gevşek mod: hesapla ve logla

    deger_ref = _deger_referansi_yukle()
    kisilik = kimlik.get("kisilik", {})

    zaman = _guncel_zaman_metni()
    prompt = f"""{zaman}

{ETIK_CEKIRDEK}
{deger_ref}

--- Kişilik ---
Konuşma tonu: {kisilik.get('ton', 'samimi')}. Mizah seviyesi: {kisilik.get('mizah', 'az')}.

--- Kullanıcı Tercihleri ---
Kullanıcı adı: {cfg.get('kullanici_adi')}. Dil: {cfg.get('dil')}. Yanıt uzunluğu: {cfg.get('yanit_uzunlugu')}.

Bu ilkeler ışığında {cfg.get('kullanici_adi')} adlı kullanıcıya yardımcı ol."""
    return prompt


# Doğrudan çalıştırılırsa: sistem promptunu ekrana bas (test için)
if __name__ == "__main__":
    print(sistem_promptu_olustur())
    print("\n[Cekirdek muhru]:", cekirdek_muhru())
