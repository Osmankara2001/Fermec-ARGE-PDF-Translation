


from pathlib import Path
import pymupdf


def pdf_analiz_et(pdf_yolu: Path) -> dict:
    """PDF dosyasini analiz eder ve sonucunu sozluk olarak dondurur."""

    if not pdf_yolu.is_file():
        raise FileNotFoundError(
            f"PDF dosyasi bulunamadi: {pdf_yolu}"
        )

    sayfalar = []

    with pymupdf.open(pdf_yolu) as belge:
        for sayfa_no, sayfa in enumerate(belge, start=1):
            metin = sayfa.get_text().strip()
            bloklar = sayfa.get_text("blocks")
            gorsel_sayisi = len(sayfa.get_images())

            sayfalar.append({
                "sayfa_no": sayfa_no,
                "metin": metin,
                "metin_blok_sayisi": len(bloklar),
                "karakter_sayisi": len(metin),
                "gorsel_sayisi": gorsel_sayisi,
                "uyari": (
                    "Metin bulunamadi; sayfa bos veya taranmis olabilir."
                    if not metin else None
                ),
            })

        return {
            "dosya": pdf_yolu.name,
            "toplam_sayfa": len(belge),
            "sayfalar": sayfalar,
        }


def main():
    pdf_yolu = Path("input") / "fermec_ornek.pdf"

    try:
        sonuc = pdf_analiz_et(pdf_yolu)

        print("PDF basariyla analiz edildi!")
        print("Dosya:", sonuc["dosya"])
        print("Toplam sayfa:", sonuc["toplam_sayfa"])

        for sayfa in sonuc["sayfalar"]:
            print(f"\n--- SAYFA {sayfa['sayfa_no']} ---")
            print("Metin blogu:", sayfa["metin_blok_sayisi"])
            print("Karakter:", sayfa["karakter_sayisi"])
            print("Gorsel:", sayfa["gorsel_sayisi"])

            if sayfa["uyari"]:
                print("UYARI:", sayfa["uyari"])
            else:
                print("Ilk 200 karakter:")
                print(sayfa["metin"][:200])

    except Exception as hata:
        print("HATA: PDF analiz edilemedi.")
        print("Detay:", hata)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
