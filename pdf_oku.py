
from pathlib import Path

import pymupdf

girdi_klasoru = Path("input")

pdf_dosyalari = sorted(girdi_klasoru.glob("*.pdf"))

if not pdf_dosyalari:
    print("HATA: input klasorunde PDF dosyasi bulunamadi.")
    raise SystemExit(1)

pdf_yolu = pdf_dosyalari[0]

print("Okunacak PDF:", pdf_yolu.name)

with pymupdf.open(pdf_yolu) as belge:
    print("PDF basariyla acildi!")
    print("Toplam sayfa:", len(belge))

    for sayfa_no, sayfa in enumerate(belge, start=1):
        print(f"\n--- SAYFA {sayfa_no} ---")

        bloklar = sayfa.get_text("blocks")
        print("Metin blogu sayisi:", len(bloklar))

        for blok_no, blok in enumerate(bloklar, start=1):
            x0, y0, x1, y1, metin = blok[:5]
            metin = metin.strip()

            if metin:
                print(f"Blok {blok_no}: {metin}")
                print(
                    f"Konum: sol={x0:.1f}, ust={y0:.1f}, "
                    f"sag={x1:.1f}, alt={y1:.1f}"
                )
