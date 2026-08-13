"""
Nasri — e-Paper donanım sürücüsü (sarmalayıcı).
Waveshare 2.13" V4 (siyah/beyaz, 250x122) için ince bir katman.
Sürücü kütüphanesi ~/nasri/e-Paper/.../lib altından yüklenir.
Bu modül yalnızca DONANIMI yönetir; ne yazılacağına modules/display.py karar verir.
"""
import os
import sys
from nasri_core.logger import get_logger

log = get_logger("nasri.epaper")

# Waveshare sürücü kütüphanesinin yolu (venv'e kurulu değil, klasörden import)
_LIB_PATH = os.path.expanduser("~/nasri/e-Paper/RaspberryPi_JetsonNano/python/lib")
if os.path.isdir(_LIB_PATH) and _LIB_PATH not in sys.path:
    sys.path.append(_LIB_PATH)

# Waveshare ile gelen font dosyası
FONT_PATH = os.path.expanduser("~/nasri/e-Paper/RaspberryPi_JetsonNano/python/pic/Font.ttc")


class EPaperHatasi(Exception):
    """e-Paper donanımıyla ilgili sorunlarda fırlatılır."""
    pass


class EPaper:
    """2.13in V4 ekranın donanım arayüzü. Yatay kullanım: 250 (en) x 122 (boy)."""

    def __init__(self):
        try:
            from waveshare_epd import epd2in13_V4
        except ImportError as e:
            raise EPaperHatasi(f"waveshare_epd yuklenemedi (lib yolu: {_LIB_PATH}): {e}")

        self._epd = epd2in13_V4.EPD()
        # Yatay yerleşim: sürücüde width=122 (kısa), height=250 (uzun)
        self.en = self._epd.height   # 250
        self.boy = self._epd.width   # 122
        self._baz_kuruldu = False
        log.info("e-Paper nesnesi olusturuldu (%dx%d).", self.en, self.boy)

    def baslat(self) -> None:
        """Ekranı başlatır ve beyaza temizler."""
        self._epd.init()
        self._epd.Clear(0xFF)
        log.info("e-Paper baslatildi ve temizlendi.")

    def tam_goster(self, image) -> None:
        """Tüm ekranı tam yenileme ile çizer (titrer, ~2-3 sn). Seyrek kullan."""
        self._epd.display(self._epd.getbuffer(image))
        log.debug("Tam yenileme yapildi.")

    def baz_kur(self, image) -> None:
        """Kısmi yenileme için temel görüntüyü kurar. Kısmi yenilemeden önce şart."""
        self._epd.displayPartBaseImage(self._epd.getbuffer(image))
        self._baz_kuruldu = True
        log.debug("Kismi yenileme temel goruntusu kuruldu.")

    def kismi_goster(self, image) -> None:
        """Sadece değişen bölgeleri titremeden günceller. Önce baz_kur() çağrılmalı."""
        if not self._baz_kuruldu:
            # Güvenlik: baz kurulmadan kısmi çağrılırsa önce onu kur
            self.baz_kur(image)
            return
        self._epd.displayPartial(self._epd.getbuffer(image))
        log.debug("Kismi yenileme yapildi.")

    def uyut(self) -> None:
        """Ekranı düşük güç moduna alır. Program biterken çağrılmalı (ömür için)."""
        self._epd.sleep()
        log.info("e-Paper uyku moduna alindi.")
