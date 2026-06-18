"""
Nasri — Merkezi loglama.
Hem ekrana (konsol) hem dosyaya yazar. Tüm modüller bunu kullanır.
Felsefe: yapılan her önemli işlem iz bırakmalı (hesap verebilirlik).
"""
import logging
import sys
from nasri_core import paths


def get_logger(name: str = "nasri") -> logging.Logger:
    """İsimli bir logger döndürür. Aynı isimle tekrar çağrılırsa aynı logger gelir."""
    paths.ensure_dirs()  # logs/ klasörü var olsun

    logger = logging.getLogger(name)
    if logger.handlers:          # zaten kurulduysa tekrar kurma
        return logger

    logger.setLevel(logging.DEBUG)

    # Biçim: zaman - modül - seviye - mesaj
    fmt = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1) Konsola yaz (INFO ve üstü)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # 2) Dosyaya yaz (her şey — DEBUG dahil)
    file_handler = logging.FileHandler(paths.LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger
