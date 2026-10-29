

from pathlib import Path

import pymupdf

girdi_klasoru = Path("input")
pdf_dosyalari = sorted(girdi_klasoru.glob("*.pdf"))

if not pdf_dosyalari:
    print("HATA: input klasorunde PDF dosyasi bulunamadi.")
    raise SystemExit(1)

pdf_yolu = pdf_dosyalari[0]
print("Okunacak PDF:", pdf_yolu.name)

try:
    with pymupdf.open(pdf_yolu) as belge:
        print("PDF basariyla acildi!")
        print("Toplam sayfa:", len(belge))

        if len(belge) == 0:
            print("UYARI: PDF dosyasinda sayfa yok.")

        for sayfa_no, sayfa in enumerate(belge, start=1):
            metin = sayfa.get_text().strip()
            bloklar = sayfa.get_text("blocks")

            print(f"\n--- SAYFA {sayfa_no} ---")
            print("Metin blogu sayisi:", len(bloklar))
            print("Metin karakter sayisi:", len(metin))

            if not metin:
                print(
                    "UYARI: Metin bulunamadi. "
                    "Sayfa bos veya taranmis olabilir."
                )
            else:
                print("Metnin ilk 200 karakteri:")
                print(metin[:200])

except Exception as hata:
    print("HATA: PDF okunamadi.")
    print("Detay:", hata)
    raise SystemExit(1)
