"""
Nasri — Çok turlu sohbet döngüsü.
Konuşma geçmişini bellekte tutar, her turda LLM'e bağlamla birlikte gönderir.
Geçmiş, son MAKS_TUR tur ile sınırlıdır (hız ve bellek için).
İsteğe bağlı sesli yanıt (tts) ve e-Paper durum göstergesi (display).
"""
from nasri_core import llm
from nasri_core.logger import get_logger

log = get_logger("nasri.chat")

# Sesli sohbette her tur girdi tokenlarina eklenir ve dogrudan gecikmeye
# yansir (Pi 5'te ~28 tok/s). 4 tur baglam icin yeterli, hiz icin gerekli.
MAKS_TUR = 4    # bellekte tutulacak en fazla konuşma turu (kullanıcı+asistan çifti)


class Sohbet:
    """Tek bir sohbet oturumunu ve geçmişini yönetir."""

    def __init__(self, sesli: bool = False, ekran=None):
        # gecmis: [{"role": "user"/"assistant", "content": "..."}]
        self.gecmis: list[dict] = []
        self.sesli = sesli      # True ise yanıtlar hoparlörden de okunur
        self.ekran = ekran      # Ekran nesnesi (None ise ekran kullanılmaz)

    def _gecmisi_kirp(self) -> None:
        """Geçmişi son MAKS_TUR tur ile sınırla (her tur = 2 mesaj)."""
        azami_mesaj = MAKS_TUR * 2
        if len(self.gecmis) > azami_mesaj:
            self.gecmis = self.gecmis[-azami_mesaj:]
            log.debug("Gecmis kirpildi: son %d mesaj tutuluyor.", azami_mesaj)

    def _durum(self, durum: str) -> None:
        """Ekran varsa durumu yazar. Ekran hatası sohbeti durdurmaz."""
        if self.ekran is None:
            return
        try:
            self.ekran.durum_yaz(durum)
        except Exception as e:
            log.warning("Ekran guncellenemedi (sohbet devam ediyor): %s", e)

    def mesaj_gonder(self, kullanici_mesaji: str) -> str:
        """Kullanıcı mesajını geçmişle birlikte gönderir, yanıtı döndürür ve geçmişe ekler."""
        self._durum("dusunuyor")
        yanit = llm.yanit_al(kullanici_mesaji, gecmis=self.gecmis)

        self.gecmis.append({"role": "user", "content": kullanici_mesaji})
        self.gecmis.append({"role": "assistant", "content": yanit})
        self._gecmisi_kirp()

        if self.sesli:
            self._durum("konusuyor")
            self._seslendir(yanit)

        self._durum("bekliyor")
        return yanit

    def mesaj_gonder_akis(self, kullanici_mesaji: str):
        """
        mesaj_gonder ile ayni, ama yaniti parca parca uretir (generator).
        Akis bitince tam yanit gecmise eklenir.
        """
        self._durum("dusunuyor")
        parcalar = []
        for parca in llm.yanit_akisi(kullanici_mesaji, gecmis=self.gecmis):
            parcalar.append(parca)
            yield parca
        yanit = "".join(parcalar).strip()
        if yanit:
            self.gecmis.append({"role": "user", "content": kullanici_mesaji})
            self.gecmis.append({"role": "assistant", "content": yanit})
            self._gecmisi_kirp()

    def _seslendir(self, metin: str) -> None:
        """Yanıtı sesli okur. TTS hatası sohbeti durdurmaz, sadece loglanır."""
        try:
            from nasri_core import tts
            tts.konus(metin)
        except Exception as e:
            log.warning("Seslendirme basarisiz (sohbet devam ediyor): %s", e)

    def sifirla(self) -> None:
        """Sohbet geçmişini temizler."""
        self.gecmis.clear()
        log.info("Sohbet gecmisi sifirlandi.")


# Doğrudan çalıştırılırsa: interaktif sohbet döngüsü
if __name__ == "__main__":
    import sys
    sesli = "--sesli" in sys.argv
    ekran_acik = "--ekran" in sys.argv

    ekran = None
    if ekran_acik:
        try:
            from nasri_core.modules.display import Ekran
            ekran = Ekran()
            ekran.baslat()
        except Exception as e:
            print("Ekran baslatilamadi, ekransiz devam:", e)
            ekran = None

    print("nasri ile sohbet (cikis: 'cik' veya bos Enter, sifirla: 'sifirla')")
    print("Sesli yanit:", "ACIK" if sesli else "kapali",
          "| Ekran:", "ACIK" if ekran else "kapali")
    print("-" * 55)
    oturum = Sohbet(sesli=sesli, ekran=ekran)
    try:
        while True:
            try:
                soru = input("\nSen: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGorusuruz!")
                break
            if not soru or soru.lower() in ("cik", "çık", "exit", "quit"):
                print("Gorusuruz!")
                break
            if soru.lower() in ("sifirla", "sıfırla", "reset"):
                oturum.sifirla()
                print("[Gecmis temizlendi.]")
                continue
            if ekran:
                oturum._durum("dinliyor")
            print("nasri dusunuyor...")
            try:
                print("nasri:", oturum.mesaj_gonder(soru))
            except llm.OllamaHatasi as e:
                print("HATA:", e)
    finally:
        if ekran:
            ekran.kapat()
