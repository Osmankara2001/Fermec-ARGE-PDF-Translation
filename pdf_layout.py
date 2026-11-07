import json
from pathlib import Path

import pymupdf


def cift_dilli_pdf_olustur(
    kaynak_yolu: Path,
    cikti_yolu: Path,
):
    rapor = {
        "kaynak": kaynak_yolu.name,
        "toplam_sayfa": 0,
        "sayfalar": [],
        "hatalar": [],
    }

    cikti_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with pymupdf.open(kaynak_yolu) as kaynak:
        with pymupdf.open() as sonuc:

            rapor["toplam_sayfa"] = len(kaynak)

            for sayfa_no, orijinal in enumerate(
                kaynak,
                start=1,
            ):
                genislik = orijinal.rect.width
                yukseklik = orijinal.rect.height

                yeni = sonuc.new_page(
                    width=genislik * 2,
                    height=yukseklik,
                )

                # Sol taraf: Turkce sayfa alani
                sol = pymupdf.Rect(
                    0, 0, genislik, yukseklik
                )

                # Sag taraf: orijinal PDF sayfasi
                sag = pymupdf.Rect(
                    genislik, 0,
                    genislik * 2, yukseklik
                )

                yeni.show_pdf_page(
                    sag,
                    kaynak,
                    sayfa_no - 1,
                )

                # Sayfa analizi
                metin = orijinal.get_text("text")
                tablolar = orijinal.find_tables()

                sayfa_raporu = {
                    "sayfa_no": sayfa_no,
                    "genislik": genislik,
                    "yukseklik": yukseklik,
                    "metin_karakter": len(metin),
                    "tablo_sayisi": len(tablolar.tables),
                    "gorsel_sayisi": len(
                        orijinal.get_images(full=True)
                    ),
                    "durum": "analiz_edildi",
                }

                if not metin.strip():
                    sayfa_raporu["durum"] = "ocr_gerekli"

                    rapor["hatalar"].append({
                        "sayfa_no": sayfa_no,
                        "tur": "ocr_gerekli",
                        "aciklama": (
                            "Sayfada secilebilir metin bulunamadi."
                        ),
                    })

                rapor["sayfalar"].append(
                    sayfa_raporu
                )

            sonuc.save(
                cikti_yolu,
                garbage=4,
                deflate=True,
            )

    rapor_yolu = Path("reports") / (
        cikti_yolu.stem + "_rapor.json"
    )

    rapor_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with rapor_yolu.open(
        "w",
        encoding="utf-8",
    ) as dosya:
        json.dump(
            rapor,
            dosya,
            ensure_ascii=False,
            indent=2,
        )

    return rapor

if __name__ == "__main__":
    kaynak = Path(
        "input/fermec_heavy_equipment_6page_pilot.pdf"
    )

    cikti = Path(
        "output/genel_cift_dilli_test.pdf"
    )

    rapor = cift_dilli_pdf_olustur(
        kaynak,
        cikti,
    )

    print("Islenen sayfa:", rapor["toplam_sayfa"])
    print("Tespit edilen sorun:", len(rapor["hatalar"]))
    print("PDF:", cikti)
    print(
        "Rapor:",
        "reports/genel_cift_dilli_test_rapor.json",
    )