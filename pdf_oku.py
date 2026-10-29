
import pymupdf

pdf_yolu = "ornek.pdf"

belge = pymupdf.open(pdf_yolu)

print("PDF basariyla acildi!")
print("Toplam sayfa:", len(belge))

if len(belge) > 0:
    ilk_sayfa = belge[0]
    metin = ilk_sayfa.get_text()
    print("\nIlk sayfanin ilk 500 karakteri:")
    print(metin[:500])

belge.close()
