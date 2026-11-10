
from pathlib import Path

import pymupdf

girdi = Path("input/fermec_heavy_equipment_6page_pilot.pdf")
cikti_klasoru = Path("output")
cikti = cikti_klasoru / "cift_dilli_test.pdf"

cikti_klasoru.mkdir(exist_ok=True)

try:
    with pymupdf.open(girdi) as kaynak:
        sonuc = pymupdf.open()

        for sayfa_no in [2]:
            orijinal = kaynak[sayfa_no - 1]
            genislik = orijinal.rect.width
            yukseklik = orijinal.rect.height

            # Orijinal sayfanin iki kati genisliginde yeni sayfa
            yeni = sonuc.new_page(
                width=genislik * 2,
                height=yukseklik,
            )

            # Sol taraf: simdilik Turkce metin alani
            sol = pymupdf.Rect(
                0, 0, genislik, yukseklik
            )
            yeni.draw_rect(sol, color=(0.7, 0.7, 0.7), width=1)
            yeni.insert_text(
                (40, 50),
                f"Turkce ceviri alani - Orijinal s. {sayfa_no}",
                fontsize=14,
                fontname="helv",
            )
            yeni.insert_text(
                (40, 80),
                "Ceviri bu alana yerlestirilecek.",
                fontsize=11,
                fontname="helv",
            )

            # Sag taraf: orijinal PDF sayfasini yerlestir
            sag = pymupdf.Rect(
                genislik, 0, genislik * 2, yukseklik
            )
            yeni.show_pdf_page(
                sag,
                kaynak,
                sayfa_no - 1,
            )

        sonuc.save(cikti, garbage=4, deflate=True)
        sonuc.close()

    print("Basarili! Cift dilli test PDF'si olusturuldu.")
    print("Dosya:", cikti)
    print("Sayfa sayisi:", len(pymupdf.open(cikti)))

except Exception as hata:
    print("HATA:", hata)
    raise
