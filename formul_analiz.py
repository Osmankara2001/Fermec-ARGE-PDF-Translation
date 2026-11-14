
from pathlib import Path
import re
import pymupdf

input_klasoru = Path("input")
pdfler = list(input_klasoru.glob("*.pdf"))

if len(pdfler) != 1:
    raise RuntimeError(
        "input klasorunde tam olarak bir PDF olmali."
    )

pdf = pymupdf.open(pdfler[0])

# Matematiksel ifade icerebilecek karakterler.
matematik_deseni = re.compile(
    r"[=+\-*/^√∑∫≈≤≥∞π∆∂]"
)

print(f"PDF: {pdfler[0].name}")
print(f"Toplam sayfa: {len(pdf)}")

for sayfa_no, sayfa in enumerate(pdf, start=1):
    print(f"\n--- SAYFA {sayfa_no} ---")

    bloklar = sayfa.get_text("blocks")
    formul_adaylari = []

    for blok in bloklar:
        if len(blok) < 5:
            continue

        metin = blok[4].strip()

        if not metin:
            continue

        if matematik_deseni.search(metin):
            formul_adaylari.append({
                "metin": metin,
                "bbox": blok[:4]
            })

    print(
        f"Matematiksel ifade adayi: "
        f"{len(formul_adaylari)}"
    )

    for aday in formul_adaylari:
        print(f"Metin: {aday['metin']}")
        print(f"Konum: {aday['bbox']}")

    cizimler = sayfa.get_drawings()

    print(
        f"Vektorel cizim sayisi: {len(cizimler)}"
    )

pdf.close()
