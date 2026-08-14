"""
nasri — Model karşılaştırma aracı.

Aynı sistem promptu ve aynı sorularla birden çok Ollama modelini ölçer.
Amaç: model seçimini tahminle değil ölçümle yapmak.

Ölçülen değerler:
  ilk ses     : ilk token gelene kadar geçen süre. Kullanıcının sessizce
                beklediği süre budur — en önemli sayı.
  girdi tok/s : prompt işleme hızı (Pi 5'te asıl darboğaz).
  üretim tok/s: yanıt üretme hızı.

Türkçe kalitesini araç ölçmez; yanıtları okuyup siz değerlendirirsiniz.

Kullanım:
    cd ~/nasri && source venv/bin/activate
    python karsilastir.py
    python karsilastir.py --model gemma3:1b --model gemma3:4b
"""
import argparse
import json
import time

import requests

from nasri_core import config, soul

VARSAYILAN_MODELLER = [
    "gemma3:1b",
    "gemma3:4b",
    "qwen3:4b",
    "aya-expanse:8b",
]

# Sorular kasıtlı olarak farklı yetenekleri yokluyor:
#  1-2: kısa olgusal + kimlik (prompt'a uyuyor mu)
#  3  : bilgi doğruluğu
#  4  : açıklama kurma
#  5  : akıl yürütme + doğal Türkçe (kaliteyi en iyi bu ayırt eder)
SORULAR = [
    "Saat kaç?",
    "Adın ne?",
    "Türkiye'nin başkenti neresi?",
    "Raspberry Pi nedir, kısaca anlat.",
    "Buzdolabında sadece yumurta ve peynir var, ne yapabilirim?",
]


def sor(url: str, sistem: str, zaman: str, model: str, soru: str,
        keep_alive: str = "5m") -> dict:
    """Tek bir soruyu akış modunda sorar ve ölçümleri döndürür."""
    govde = {
        "model": model,
        "stream": True,
        "keep_alive": keep_alive,
        # qwen3 varsayilan olarak "dusunme" modunda; basit sorulara
        # 2000+ token uretip dakikalarca calisiyor. Kapatiyoruz.
        "think": False,
        "messages": [
            {"role": "system", "content": sistem},
            {"role": "user", "content": f"[{zaman}]\n\n{soru}"},
        ],
    }
    t0 = time.perf_counter()
    ilk = None
    parcalar = []
    son = {}

    with requests.post(url, json=govde, stream=True, timeout=600) as cevap:
        cevap.raise_for_status()
        for satir in cevap.iter_lines():
            if not satir:
                continue
            try:
                veri = json.loads(satir)
            except json.JSONDecodeError:
                continue
            parca = veri.get("message", {}).get("content", "")
            if parca:
                if ilk is None:
                    ilk = time.perf_counter() - t0
                parcalar.append(parca)
            if veri.get("done"):
                son = veri

    ns = 1e9
    return {
        "yanit": "".join(parcalar).strip().replace("\n", " "),
        "ilk": ilk or 0.0,
        "toplam": time.perf_counter() - t0,
        "girdi_tok": son.get("prompt_eval_count", 0),
        "girdi_sn": son.get("prompt_eval_duration", 0) / ns,
        "uretim_tok": son.get("eval_count", 0),
        "uretim_sn": son.get("eval_duration", 0) / ns,
    }


def bellegi_bosalt(url: str, model: str) -> None:
    """Modeli bellekten düşürür — 8GB RAM'de sonraki ölçüm adil olsun diye."""
    try:
        requests.post(url, json={"model": model, "messages": [],
                                 "keep_alive": 0}, timeout=60)
    except requests.exceptions.RequestException:
        pass


def main() -> None:
    ayristirici = argparse.ArgumentParser()
    ayristirici.add_argument("--model", action="append", dest="modeller",
                             help="Ölçülecek model (birden çok kez verilebilir)")
    args = ayristirici.parse_args()
    modeller = args.modeller or VARSAYILAN_MODELLER

    cfg = config.yukle()
    url = f"{cfg['ollama_url']}/api/chat"
    sistem = soul.sistem_promptu_olustur()
    zaman = soul.guncel_zaman_metni()

    print(f"Sistem promptu: {len(sistem)} karakter")
    print(f"Ölçülecek modeller: {', '.join(modeller)}")
    print(f"Soru sayısı: {len(SORULAR)}\n")

    ozet = []
    for model in modeller:
        cizgi = "=" * 68
        print(f"{cizgi}\nMODEL: {model}\n{cizgi}")

        try:
            sor(url, sistem, zaman, model, "merhaba")   # ısıtma, ölçüme katılmaz
        except requests.exceptions.RequestException as e:
            print(f"  ATLANDI (model yok veya hata): {e}\n")
            continue

        girdi_hizlari, uretim_hizlari, ilk_sesler = [], [], []
        for soru in SORULAR:
            try:
                s = sor(url, sistem, zaman, model, soru)
            except requests.exceptions.RequestException as e:
                print(f"  {soru} -> HATA: {e}")
                continue

            if s["girdi_sn"]:
                girdi_hizlari.append(s["girdi_tok"] / s["girdi_sn"])
            if s["uretim_sn"]:
                uretim_hizlari.append(s["uretim_tok"] / s["uretim_sn"])
            ilk_sesler.append(s["ilk"])

            print(f"\n  S: {soru}")
            print(f"  C: {s['yanit'][:240]}")
            print(f"     ilk ses {s['ilk']:.1f}s | toplam {s['toplam']:.1f}s"
                  f" | girdi {s['girdi_tok']} tok/{s['girdi_sn']:.1f}s"
                  f" | üretim {s['uretim_tok']} tok/{s['uretim_sn']:.1f}s")

        if ilk_sesler:
            ozet.append((
                model,
                sum(ilk_sesler) / len(ilk_sesler),
                sum(girdi_hizlari) / len(girdi_hizlari) if girdi_hizlari else 0,
                sum(uretim_hizlari) / len(uretim_hizlari) if uretim_hizlari else 0,
            ))

        bellegi_bosalt(url, model)
        print()

    if not ozet:
        print("Hiçbir model ölçülemedi.")
        return

    print("=" * 68)
    print(f"{'MODEL':<18}{'ort ilk ses':>14}{'girdi tok/s':>14}{'üretim tok/s':>14}")
    print("-" * 68)
    for model, ilk, girdi, uretim in sorted(ozet, key=lambda x: x[1]):
        print(f"{model:<18}{ilk:>13.1f}s{girdi:>14.1f}{uretim:>14.1f}")
    print("\nHız yukarıda. Türkçe kalitesini yanıtları okuyarak siz değerlendirin;")
    print("özellikle son sorunun yanıtı akıl yürütme ve doğal Türkçeyi ayırt eder.")


if __name__ == "__main__":
    main()
