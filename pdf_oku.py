
from pathlib import Path

import pymupdf

pdf_yolu = Path("ornek.pdf")

if not pdf_yolu.exists():
    print(f"HATA: PDF dosyasi bulunamadi: {pdf_yolu}")
    raise SystemExit(1)

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
