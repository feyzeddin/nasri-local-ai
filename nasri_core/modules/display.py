"""
Nasri — Ekran (e-Paper) mantık katmanı.
Durumu (dinliyor/düşünüyor/konuşuyor) büyük puntoyla ortada,
saati altta küçük puntoyla gösterir. Kısmi yenileme kullanır (titremesiz).
Hayalet (ghosting) birikmemesi için periyodik sessiz tam yenileme yapar.

Kural: "nasri" adı HER ZAMAN küçük harf. Tüm metinler tam Türkçe karakterli.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont

from nasri_core import config
from nasri_core.drivers import epaper
from nasri_core.logger import get_logger

log = get_logger("nasri.display")

# Kaç kısmi yenilemede bir sessiz tam yenileme yapılsın (hayalet temizliği)
TAM_YENILEME_ESIGI = 30

# Durum metinleri — hepsi tam Türkçe karakterli
DURUMLAR = {
    "bekliyor":  "hazır",
    "dinliyor":  "dinliyor",
    "dusunuyor": "düşünüyor",
    "konusuyor": "konuşuyor",
}


class Ekran:
    """e-Paper üzerinde nasri'nin durumunu ve saati yönetir."""

    def __init__(self):
        self.epd = epaper.EPaper()
        self.font_buyuk = ImageFont.truetype(epaper.FONT_PATH, 42)
        self.font_kucuk = ImageFont.truetype(epaper.FONT_PATH, 18)
        self.font_marka = ImageFont.truetype(epaper.FONT_PATH, 22)
        self._durum = "bekliyor"
        self._kismi_sayac = 0
        self._tz = ZoneInfo(config.deger_al("zaman_dilimi", "Europe/Istanbul"))

    def baslat(self) -> None:
        """Ekranı açar ve ilk görüntüyü (tam yenileme + baz) kurar."""
        self.epd.baslat()
        img = self._cizim_olustur()
        self.epd.tam_goster(img)   # ilk kez tam yenileme
        self.epd.baz_kur(img)      # kısmi yenileme temeli
        log.info("Ekran baslatildi, durum: %s", self._durum)

    def _kalp_ciz(self, d, x, y, boy=10):
        """Küçük dolu kalp çizer (sol üst köşesi x,y). e-Paper için siyah."""
        r = boy / 4.0
        # İki üst yarım daire
        d.ellipse([x, y, x + 2 * r, y + 2 * r], fill=0)
        d.ellipse([x + 2 * r, y, x + 4 * r, y + 2 * r], fill=0)
        # Alt üçgen (uç)
        d.polygon([(x, y + r), (x + 4 * r, y + r), (x + 2 * r, y + boy)], fill=0)

    def _cizim_olustur(self) -> Image.Image:
        """Geçerli duruma ve saate göre tam bir ekran görüntüsü çizer."""
        img = Image.new("1", (self.epd.en, self.epd.boy), 255)  # beyaz zemin
        d = ImageDraw.Draw(img)

        # Üst sol: marka (her zaman küçük harf)
        d.text((6, 2), "nasri", font=self.font_marka, fill=0)
        # Marka yanına küçük kalp (logodaki gibi)
        marka_bbox = d.textbbox((6, 2), "nasri", font=self.font_marka)
        self._kalp_ciz(d, marka_bbox[2] + 4, 4, boy=12)

        # Orta: durum metni, büyük punto, ortalanmış
        durum_metni = DURUMLAR.get(self._durum, self._durum)
        bbox = d.textbbox((0, 0), durum_metni, font=self.font_buyuk)
        gen = bbox[2] - bbox[0]
        x = (self.epd.en - gen) // 2
        d.text((x, 40), durum_metni, font=self.font_buyuk, fill=0)

        # Alt: saat ve tarih, küçük punto
        simdi = datetime.now(self._tz).strftime("%H:%M   %d.%m.%Y")
        d.text((6, self.epd.boy - 22), simdi, font=self.font_kucuk, fill=0)

        return img

    def _yenile(self) -> None:
        """Ekranı kısmi yenilemeyle günceller; eşik dolduysa tam yeniler."""
        img = self._cizim_olustur()
        self._kismi_sayac += 1
        if self._kismi_sayac >= TAM_YENILEME_ESIGI:
            # Sessiz tam yenileme: hayaleti temizle, sonra bazı yeniden kur
            log.debug("Esik doldu, sessiz tam yenileme.")
            self.epd.tam_goster(img)
            self.epd.baz_kur(img)
            self._kismi_sayac = 0
        else:
            self.epd.kismi_goster(img)

    def durum_yaz(self, durum: str) -> None:
        """Durumu değiştirir ve ekranı günceller. (bekliyor/dinliyor/dusunuyor/konusuyor)"""
        if durum == self._durum:
            return
        self._durum = durum
        log.debug("Durum degisti: %s", durum)
        self._yenile()

    def saati_guncelle(self) -> None:
        """Sadece saati tazelemek için ekranı yeniler (dakikada bir çağrılır)."""
        self._yenile()

    def kapat(self) -> None:
        """Ekranı uyku moduna alır."""
        self.epd.uyut()


# Doğrudan çalıştırılırsa: durumları ve saati canlı test et
if __name__ == "__main__":
    import time
    ekran = Ekran()
    ekran.baslat()
    try:
        for durum in ("dinliyor", "dusunuyor", "konusuyor", "bekliyor"):
            ekran.durum_yaz(durum)
            print("Durum:", durum)
            time.sleep(3)
        print("Saat guncelleme testi (60 sn bekle)...")
        time.sleep(60)
        ekran.saati_guncelle()
        print("Tamam.")
    finally:
        ekran.kapat()
