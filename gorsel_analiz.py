
from pathlib import Path
import pymupdf

input_klasoru = Path("input")
pdfler = list(input_klasoru.glob("*.pdf"))

if len(pdfler) != 1:
    raise RuntimeError(
        "input klasorunde tam olarak bir PDF olmali."
    )

pdf = pymupdf.open(pdfler[0])

print(f"PDF: {pdfler[0].name}")
print(f"Toplam sayfa: {len(pdf)}")

for sayfa_no, sayfa in enumerate(pdf, start=1):
    gorseller = sayfa.get_images(full=True)

    print(f"\nSayfa {sayfa_no}")
    print(f"Gomulu gorsel sayisi: {len(gorseller)}")

    for gorsel in gorseller:
        xref = gorsel[0]
        konumlar = sayfa.get_image_rects(xref)

        print(f"  Gorsel XREF: {xref}")
        print(f"  Konumlar: {konumlar}")

pdf.close()
