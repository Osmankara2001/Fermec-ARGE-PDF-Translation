import json
from pathlib import Path

import pymupdf
from api.pdf_service import (
    pdf_metin_bloklarini_al,
    ceviri_bloklarini_hazirla,
)

def sayfa_yerlesim_plani_olustur(
    pdf_yolu: Path,
    sayfa_no: int,
) -> dict:
    veri = pdf_metin_bloklarini_al(
        pdf_yolu,
        sayfa_no,
    )

    bloklar = ceviri_bloklarini_hazirla(
        veri["bloklar"]
    )

    plan = {
        "sayfa_no": sayfa_no,
        "bloklar": [],
        "sorunlar": [],
    }

    for blok in bloklar:
        x0, y0, x1, y1 = blok["bbox"]

        plan["bloklar"].append({
            "id": blok["id"],
            "tur": blok["tur"],
            "cevrilecek": blok["cevrilecek"],
            "kaynak_idler": blok["kaynak_idler"],
            "bbox": [x0, y0, x1, y1],
        })

        if x1 <= x0 or y1 <= y0:
            plan["sorunlar"].append({
                "blok_id": blok["id"],
                "tur": "gecersiz_koordinat",
            })

    return plan

def turkce_karakterleri_duzelt(metin: str) -> str:
    if "Ã" not in metin and "Ä" not in metin and "Å" not in metin:
        return metin

    try:
        return metin.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return metin

def sayfa_cevirilerini_yukle(
    ceviri_klasoru: Path,
    sayfa_no: int,
) -> dict:
    json_yolu = ceviri_klasoru / f"ceviri_sayfa_{sayfa_no}.json"

    if not json_yolu.is_file():
        return {}

    with json_yolu.open("r", encoding="utf-8-sig") as dosya:
        veri = json.load(dosya)

    # n8n ciktisi bazen tek elemanli liste olabilir.
    if isinstance(veri, list):
        if len(veri) != 1:
            raise ValueError(
                f"Beklenmeyen ceviri listesi: {json_yolu}"
            )
        veri = veri[0]

    if not isinstance(veri, dict):
        raise ValueError(f"Gecersiz JSON yapisi: {json_yolu}")

    bloklar = veri.get("ceviri_bloklari")

    if not isinstance(bloklar, list):
        raise ValueError(
            f"ceviri_bloklari bulunamadi: {json_yolu}"
        )

    ceviriler = {}

    for blok in bloklar:
        blok_id = blok["id"]
        ceviri = blok["ceviri"]

        if blok_id in ceviriler:
            raise ValueError(f"Tekrarlanan blok ID: {blok_id}")

        ceviriler[blok_id] = turkce_karakterleri_duzelt(ceviri)

    return ceviriler

def turkce_metinleri_yerlestir(
    yeni_sayfa,
    plan: dict,
    ceviriler: dict,
    font_yolu: Path,
) -> list[dict]:
    sorunlar = []

    yeni_sayfa.insert_font(
        fontname="arial_tr",
        fontfile=str(font_yolu),
    )

    for blok in plan["bloklar"]:
        if not blok["cevrilecek"]:
            # Formuller icin ayri koruma yontemi eklenecek.
            continue

        blok_id = blok["id"]
        metin = ceviriler.get(blok_id)

        if metin is None:
            sorunlar.append({
                "blok_id": blok_id,
                "tur": "eksik_ceviri",
            })
            continue

        alan = pymupdf.Rect(blok["bbox"])

        # Kaynak metnin koordinatlarini temel al.
        # Komsu bloklarla cakismamak icin kutuyu buyutme.
        yerlesti = False

        for boyut in (10, 9, 8, 7, 6):
            kalan = yeni_sayfa.insert_textbox(
                alan,
                metin,
                fontname="arial_tr",
                fontsize=boyut,
                lineheight=1.1,
            )

            if kalan >= 0:
                yerlesti = True
                break

        if not yerlesti:
            sorunlar.append({
                "blok_id": blok_id,
                "tur": "metin_tasmasi",
                "aciklama": "Turkce metin kaynak kutuya sigmadi.",
            })

    return sorunlar

def tablolari_yerlestir(yeni_sayfa, orijinal_sayfa):
    sorunlar = []

    ceviri_dosyasi = Path("output/tablo_cevirileri.json")

    with ceviri_dosyasi.open(encoding="utf-8-sig") as dosya:
        tablo_cevirileri = json.load(dosya)

    for tablo_no, tablo in enumerate(
        orijinal_sayfa.find_tables().tables, start=1
    ):
        for satir_no, satir in enumerate(tablo.rows, start=1):
            for sutun_no, hucre in enumerate(satir.cells, start=1):
                if hucre is None:
                    continue

                alan = pymupdf.Rect(hucre)

                yeni_sayfa.draw_rect(
                    alan, color=(0, 0, 0), width=0.6
                )

                metin = orijinal_sayfa.get_textbox(alan).strip()
                if not metin:
                    continue

                # PDF'deki satir sonlarini duzenle.
                metin = " ".join(metin.split())

                # JSON'dan Turkce karsiligini al.
                ceviri = tablo_cevirileri.get(metin, metin)
                
                # Cevrilmemis metinleri raporla.
                if ceviri == metin and metin.isascii() and any(
                    harf.isalpha() for harf in metin
                ):
                    if " " in metin or len(metin) > 4:
                        sorunlar.append({
                            "tur": "tablo_cevirisi_bulunamadi",
                            "tablo": tablo_no,
                            "satir": satir_no,
                            "sutun": sutun_no,
                            "metin": metin,
                        })

                metin_alani = pymupdf.Rect(
                    alan.x0 + 3,
                    alan.y0 + 2,
                    alan.x1 - 3,
                    alan.y1 - 2,
                )

                # Metin sigmazsa fontu kademeli kucult.
                yerlestirildi = False

                for boyut in (9, 8, 7, 6):
                    kalan = yeni_sayfa.insert_textbox(
                        metin_alani,
                        ceviri,
                        fontname="arial_tr",
                        fontsize=boyut,
                    )

                    if kalan >= 0:
                        yerlestirildi = True
                        break

                if not yerlestirildi:
                    sorunlar.append({
                        "tur": "tablo_hucresi_tasmasi",
                        "tablo": tablo_no,
                        "satir": satir_no,
                        "sutun": sutun_no,
                        "metin": ceviri,
                    })

    return sorunlar

def formulleri_yerlestir(yeni_sayfa, orijinal_sayfa, plan):
    sorunlar = []

    for blok in plan["bloklar"]:
        if blok["tur"] != "formul":
            continue

        alan = pymupdf.Rect(blok["bbox"])

        # Kaynak sayfanin yalnizca formul bolgesini
        # vektorel olarak aktar.
        yeni_sayfa.show_pdf_page(
            alan,
            orijinal_sayfa.parent,
            orijinal_sayfa.number,
            clip=alan,
            keep_proportion=False,
        )

    return sorunlar

def ocr_cevirisini_yerlestir(yeni_sayfa, orijinal_sayfa, ceviriler):
    sorunlar = []

    if not ceviriler:
        return [{
            "tur": "ocr_cevirisi_eksik",
        }]

    metin = "\n\n".join(ceviriler.values())

    genislik = orijinal_sayfa.rect.width
    yukseklik = orijinal_sayfa.rect.height

    alan = pymupdf.Rect(
        40,
        50,
        genislik - 40,
        yukseklik - 50,
    )

    yeni_sayfa.insert_font(
        fontname="arial_tr",
        fontfile="C:/Windows/Fonts/arial.ttf",
    )

    for boyut in (11, 10, 9, 8, 7):
        kalan = yeni_sayfa.insert_textbox(
            alan,
            metin,
            fontname="arial_tr",
            fontsize=boyut,
            lineheight=1.2,
        )

        if kalan >= 0:
            return sorunlar

    sorunlar.append({
        "tur": "ocr_metin_tasmasi",
        "aciklama": "OCR cevirisi sayfaya sigmadi.",
    })

    return sorunlar


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

                # Turkce cevirileri otomatik yerlestir
                plan = sayfa_yerlesim_plani_olustur(
                    kaynak_yolu,
                    sayfa_no,
                )

                ceviriler = sayfa_cevirilerini_yukle(
                    Path("output"),
                    sayfa_no,
                )

                if ceviriler:
                    if not plan["bloklar"]:
                        yerlesim_sorunlari = ocr_cevirisini_yerlestir(
                            yeni,
                            orijinal,
                            ceviriler,
                        )
                    else:
                        yerlesim_sorunlari = turkce_metinleri_yerlestir(
                            yeni,
                            plan,
                            ceviriler,
                            Path("C:/Windows/Fonts/arial.ttf"),
                        )
                else:
                    yerlesim_sorunlari = [{
                        "tur": "ceviri_bulunamadi",
                        "aciklama": "Bu sayfa icin ceviri dosyasi yok.",
                    }]

                for sorun in yerlesim_sorunlari:
                    rapor["hatalar"].append({
                        "sayfa_no": sayfa_no,
                        **sorun,
                    })


                if ceviriler:
                    tablo_sorunlari = tablolari_yerlestir(
                        yeni, orijinal
                    )

                    formul_sorunlari = formulleri_yerlestir(
                        yeni, orijinal, plan
                    )

                    for sorun in tablo_sorunlari + formul_sorunlari:
                        rapor["hatalar"].append({
                            "sayfa_no": sayfa_no,
                            **sorun,
                        })

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