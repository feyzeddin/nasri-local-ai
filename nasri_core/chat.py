"""
Nasri — Çok turlu sohbet döngüsü.
Konuşma geçmişini bellekte tutar, her turda LLM'e bağlamla birlikte gönderir.
Geçmiş, son MAKS_TUR tur ile sınırlıdır (hız ve bellek için).
"""
from nasri_core import llm
from nasri_core.logger import get_logger

log = get_logger("nasri.chat")

MAKS_TUR = 10   # bellekte tutulacak en fazla konuşma turu (kullanıcı+asistan çifti)


class Sohbet:
    """Tek bir sohbet oturumunu ve geçmişini yönetir."""

    def __init__(self):
        # gecmis: [{"role": "user"/"assistant", "content": "..."}]
        self.gecmis: list[dict] = []

    def _gecmisi_kirp(self) -> None:
        """Geçmişi son MAKS_TUR tur ile sınırla (her tur = 2 mesaj)."""
        azami_mesaj = MAKS_TUR * 2
        if len(self.gecmis) > azami_mesaj:
            self.gecmis = self.gecmis[-azami_mesaj:]
            log.debug("Gecmis kirpildi: son %d mesaj tutuluyor.", azami_mesaj)

    def mesaj_gonder(self, kullanici_mesaji: str) -> str:
        """Kullanıcı mesajını geçmişle birlikte gönderir, yanıtı döndürür ve geçmişe ekler."""
        yanit = llm.yanit_al(kullanici_mesaji, gecmis=self.gecmis)
        # Hem soruyu hem yanıtı geçmişe ekle
        self.gecmis.append({"role": "user", "content": kullanici_mesaji})
        self.gecmis.append({"role": "assistant", "content": yanit})
        self._gecmisi_kirp()
        return yanit

    def sifirla(self) -> None:
        """Sohbet geçmişini temizler."""
        self.gecmis.clear()
        log.info("Sohbet gecmisi sifirlandi.")


# Doğrudan çalıştırılırsa: interaktif sohbet döngüsü
if __name__ == "__main__":
    print("Nasri ile sohbet (cikis: 'cik' veya bos Enter, sifirla: 'sifirla')")
    print("-" * 55)
    oturum = Sohbet()
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
        print("Nasri dusunuyor...")
        try:
            print("Nasri:", oturum.mesaj_gonder(soru))
        except llm.OllamaHatasi as e:
            print("HATA:", e)
