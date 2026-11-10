import json
from pathlib import Path

import pymupdf

from api.pdf_service import (
    pdf_metin_bloklarini_al,
    ceviri_bloklarini_hazirla,
)

PDF_YOLU = Path("input/fermec_heavy_equipment_6page_pilot.pdf")
JSON_YOLU = Path("output/ceviri_sayfa_2.json")
CIKTI_YOLU = Path("output/cift_dilli_turkce_sayfa_2.pdf")
FONT_YOLU = Path("C:/Windows/Fonts/arial.ttf")

SAYFA_NO = 2

with JSON_YOLU.open("r", encoding="utf-8") as dosya:
    ceviri_verisi = json.load(dosya)

if isinstance(ceviri_verisi, list):
    if len(ceviri_verisi) != 1:
        raise ValueError("JSON dosyasinda tek bir ceviri sonucu bekleniyor.")
    ceviri_verisi = ceviri_verisi[0]

ceviriler = {
    blok["id"]: blok["ceviri"]
    for blok in ceviri_verisi["ceviri_bloklari"]
}

veri = pdf_metin_bloklarini_al(PDF_YOLU, SAYFA_NO)
bloklar = ceviri_bloklarini_hazirla(veri["bloklar"])

kaynak = pymupdf.open(PDF_YOLU)
sonuc = pymupdf.open()

try:
    orijinal = kaynak[SAYFA_NO - 1]

    genislik = orijinal.rect.width
    yukseklik = orijinal.rect.height

    yeni = sonuc.new_page(
        width=genislik * 2,
        height=yukseklik,
    )

    # Turkce karakterleri destekleyen font
    yeni.insert_font(
        fontname="arial_tr",
        fontfile=str(FONT_YOLU),
    )

    # Sol sayfaya metin ve formulleri yerlestir
    for blok in bloklar:
        bbox = blok["bbox"]
        alan = pymupdf.Rect(bbox)
                # Sayfanin altindaki dipnotu ayri yerlestir
        if blok["id"] == "P0002_B0003":
            dipnot = ceviriler.get(blok["id"])

            if dipnot is None:
                raise ValueError("Dipnot cevirisi bulunamadi.")

            # Orijinal dipnotun yatay konumunu koru
            dipnot_alani = pymupdf.Rect(
                44,
                yukseklik - 35,
                genislik - 35,
                yukseklik - 8,
            )

            kalan = yeni.insert_textbox(
                dipnot_alani,
                dipnot,
                fontname="arial_tr",
                fontsize=7,
                lineheight=1.0,
            )

            if kalan < 0:
                print("UYARI: Dipnot sigmadi!")

            continue

        if blok["cevrilecek"]:
            metin = ceviriler.get(blok["id"])

            if metin is None:
                raise ValueError(
                    f"Ceviri bulunamadi: {blok['id']}"
                )
        else:
            # Formulleri degistirmeden koru
            metin = blok["metin"]

        # Uzun Turkce metinler icin kutuyu biraz genislet
        alan.x1 = min(genislik - 30, alan.x1 + 60)
        alan.y1 = min(yukseklik - 30, alan.y1 + 20)

        # Metin kutuya sigmazsa fontu kucult
        yerlesti = False

        for font_boyutu in (10, 9, 8, 7, 6):
            kalan = yeni.insert_textbox(
                alan,
                metin,
                fontname="arial_tr",
                fontsize=font_boyutu,
                lineheight=1.15,
            )

            if kalan >= 0:
                yerlesti = True
                break

        if not yerlesti:
            print(
                "UYARI: Metin kutuya sigmadi:",
                blok["id"],
            )
        # Tablo metinleri icin Turkce karsiliklar
    tablo_cevirileri = {
        "Parameter": "Parametre",
        "Symbol": "Sembol",
        "Test value": "Test değeri",
        "Unit": "Birim",
        "System pressure": "Sistem basıncı",
        "Cylinder bore": "Silindir çapı",
        "Hydraulic flow": "Hidrolik debi",
        "Oil temperature": "Yağ sıcaklığı",
        "Volumetric efficiency": "Hacimsel verim",
    }

    # Sol sayfaya Turkce tabloyu yerlestir
    tablolar = orijinal.find_tables()

    for tablo in tablolar.tables:
        for satir_no, satir in enumerate(tablo.rows):
            for sutun_no, hucre in enumerate(satir.cells):
                if hucre is None:
                    continue

                alan = pymupdf.Rect(hucre)

                # Orijinal hucre sinirlarini koru
                yeni.draw_rect(
                    alan,
                    color=(0, 0, 0),
                    width=0.6,
                )

                # Metni PDF'nin asil metin katmanindan oku
                orijinal_metin = orijinal.get_textbox(alan).strip()

                if not orijinal_metin:
                    continue

                # Yalnizca tanimli metinleri cevir
                metin = tablo_cevirileri.get(
                    orijinal_metin,
                    orijinal_metin,
                )

                metin_alani = pymupdf.Rect(
                    alan.x0 + 4,
                    alan.y0 + 4,
                    alan.x1 - 4,
                    alan.y1 - 4,
                )

                kalan = yeni.insert_textbox(
                    metin_alani,
                    metin,
                    fontname="arial_tr",
                    fontsize=9,
                    lineheight=1.1,
                )

                if kalan < 0:
                    print(
                        "UYARI: Tablo hucresi sigmadi:",
                        satir_no + 1,
                        sutun_no + 1,
                    )
    # Sag sayfaya orijinal PDF'yi vektorel yerlestir
    sag = pymupdf.Rect(
        genislik, 0,
        genislik * 2, yukseklik,
    )

    yeni.show_pdf_page(
        sag,
        kaynak,
        SAYFA_NO - 1,
    )

    sonuc.save(
        CIKTI_YOLU,
        garbage=4,
        deflate=True,
    )

finally:
    sonuc.close()
    kaynak.close()

print("PDF olusturuldu:", CIKTI_YOLU)