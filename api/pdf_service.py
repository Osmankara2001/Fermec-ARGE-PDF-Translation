

from pathlib import Path
import pymupdf
import subprocess
import tempfile
import re

PARCA_BOYUTU = 5


def pdf_analiz_et(pdf_yolu: Path) -> dict:
    if not pdf_yolu.is_file():
        raise FileNotFoundError(f"PDF dosyasi bulunamadi: {pdf_yolu}")

    sayfalar = []

    with pymupdf.open(pdf_yolu) as belge:
        for sayfa_no, sayfa in enumerate(belge, start=1):
            metin = sayfa.get_text().strip()

            sayfalar.append({
                "sayfa_no": sayfa_no,
                "metin": metin,
                "metin_blok_sayisi": len(sayfa.get_text("blocks")),
                "karakter_sayisi": len(metin),
                "gorsel_sayisi": len(sayfa.get_images()),
                "uyari": (
                    "Metin bulunamadi; sayfa bos veya taranmis olabilir."
                    if not metin else None
                ),
            })

        toplam_sayfa = len(belge)

    parcalar = []

    for baslangic in range(1, toplam_sayfa + 1, PARCA_BOYUTU):
        bitis = min(baslangic + PARCA_BOYUTU - 1, toplam_sayfa)

        parcalar.append({
            "parca_no": len(parcalar) + 1,
            "baslangic_sayfasi": baslangic,
            "bitis_sayfasi": bitis,
            "sayfa_sayisi": bitis - baslangic + 1,
        })

    return {
        "dosya": pdf_yolu.name,
        "toplam_sayfa": toplam_sayfa,
        "parca_boyutu": PARCA_BOYUTU,
        "toplam_parca": len(parcalar),
        "parcalar": parcalar,
        "sayfalar": sayfalar,
    }


def pdf_parca_metni_al(
    pdf_yolu: Path,
    baslangic_sayfasi: int,
    bitis_sayfasi: int,
) -> dict:
    if not pdf_yolu.is_file():
        raise FileNotFoundError(f"PDF dosyasi bulunamadi: {pdf_yolu}")

    if baslangic_sayfasi < 1 or bitis_sayfasi < baslangic_sayfasi:
        raise ValueError("Sayfa araligi gecersiz.")

    sayfalar = []

    with pymupdf.open(pdf_yolu) as belge:
        if bitis_sayfasi > len(belge):
            raise ValueError("Istenen sayfa PDF sinirlarini asiyor.")

        for sayfa_no in range(baslangic_sayfasi, bitis_sayfasi + 1):
            sayfa = belge[sayfa_no - 1]

            # Sayfanin metnini al
            metin = sayfa.get_text().strip()

            # Gorsel ve cizim sayilarini hesapla
            gorsel_sayisi = len(sayfa.get_images())
            cizim_sayisi = len(sayfa.get_drawings())

            # Sayfa turunu belirle
            if metin:
                sayfa_turu = "metinli"
            elif gorsel_sayisi > 0:
                sayfa_turu = "taranmis_adayi"
            elif cizim_sayisi > 0:
                sayfa_turu = "vektorel_grafik_adayi"
            else:
                sayfa_turu = "bos_adayi"

            sayfalar.append({
                "sayfa_no": sayfa_no,
                "metin": metin,
                "gorsel_sayisi": gorsel_sayisi,
                "cizim_sayisi": cizim_sayisi,
                "sayfa_turu": sayfa_turu,
            })

    return {
        "dosya": pdf_yolu.name,
        "baslangic_sayfasi": baslangic_sayfasi,
        "bitis_sayfasi": bitis_sayfasi,
        "sayfalar": sayfalar,
    }




def pdf_parca_kalite_kontrol(
    pdf_yolu: Path,
    baslangic_sayfasi: int,
    bitis_sayfasi: int,
) -> dict:
    parca = pdf_parca_metni_al(
        pdf_yolu,
        baslangic_sayfasi,
        bitis_sayfasi,
    )

    kontroller = []
    ceviriye_hazir = True

    for sayfa in parca["sayfalar"]:
        uyarilar = []
        sayfa_turu = sayfa["sayfa_turu"]

        if sayfa_turu == "taranmis_adayi":
            uyarilar.append("OCR incelemesi gerekli.")
            ceviriye_hazir = False

        elif sayfa_turu == "vektorel_grafik_adayi":
            uyarilar.append("Vektorel grafik incelemesi gerekli.")
            ceviriye_hazir = False

        elif sayfa_turu == "bos_adayi":
            uyarilar.append("Bos sayfa adayi; orijinal sayfa kontrol edilmeli.")
            ceviriye_hazir = False

        if sayfa["gorsel_sayisi"] > 0:
            uyarilar.append("Gorsel bulundu; yerlesimi korunmali.")

        kontroller.append({
            "sayfa_no": sayfa["sayfa_no"],
            "sayfa_turu": sayfa_turu,
            "karakter_sayisi": len(sayfa["metin"]),
            "gorsel_sayisi": sayfa["gorsel_sayisi"],
            "cizim_sayisi": sayfa["cizim_sayisi"],
            "uyarilar": uyarilar,
        })

    return {
        "dosya": parca["dosya"],
        "baslangic_sayfasi": baslangic_sayfasi,
        "bitis_sayfasi": bitis_sayfasi,
        "ceviriye_hazir": ceviriye_hazir,
        "sayfa_kontrolleri": kontroller,
    }


def pdf_sayfa_ocr(
    pdf_yolu: Path,
    sayfa_no: int,
    dil: str = "eng",
) -> dict:
    if not pdf_yolu.is_file():
        raise FileNotFoundError(f"PDF dosyasi bulunamadi: {pdf_yolu}")

    if dil not in {"eng", "tur"}:
        raise ValueError("Desteklenmeyen OCR dili.")

    with pymupdf.open(pdf_yolu) as belge:
        if sayfa_no < 1 or sayfa_no > len(belge):
            raise ValueError("Sayfa numarasi PDF sinirlarinin disinda.")

        sayfa = belge[sayfa_no - 1]
        sayfa_genisligi = sayfa.rect.width
        sayfa_yuksekligi = sayfa.rect.height

        dpi = 300
        pix = sayfa.get_pixmap(dpi=dpi, alpha=False)

        with tempfile.TemporaryDirectory() as gecici_klasor:
            png_yolu = Path(gecici_klasor) / "sayfa.png"
            pix.save(str(png_yolu))

            sonuc = subprocess.run(
                [
                    "tesseract",
                    str(png_yolu),
                    "stdout",
                    "-l",
                    dil,
                    "tsv",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            if sonuc.returncode != 0:
                raise RuntimeError(
                    f"Tesseract OCR hatasi: {sonuc.stderr.strip()}"
                )

            satirlar = {}

            for satir in sonuc.stdout.splitlines()[1:]:
                alanlar = satir.split("\t", 11)

                if len(alanlar) != 12:
                    continue

                (
                    level, page_num, block_num, par_num,
                    line_num, word_num, left, top,
                    width, height, conf, text
                ) = alanlar

                text = text.strip()

                if level != "5" or not text:
                    continue

                try:
                    guven = float(conf)
                except ValueError:
                    continue

                if guven < 0:
                    continue

                anahtar = (
                    block_num,
                    par_num,
                    line_num,
                )

                satirlar.setdefault(anahtar, []).append({
                    "metin": text,
                    "bbox": [
                        float(left),
                        float(top),
                        float(left) + float(width),
                        float(top) + float(height),
                    ],
                })

            bloklar = []

            olcek_x = sayfa_genisligi / pix.width
            olcek_y = sayfa_yuksekligi / pix.height

            for kelimeler in satirlar.values():
                x0 = min(k["bbox"][0] for k in kelimeler) * olcek_x
                y0 = min(k["bbox"][1] for k in kelimeler) * olcek_y
                x1 = max(k["bbox"][2] for k in kelimeler) * olcek_x
                y1 = max(k["bbox"][3] for k in kelimeler) * olcek_y

                bloklar.append({
                    "id": f"P{sayfa_no:04d}_OCR{len(bloklar) + 1:04d}",
                    "sayfa_no": sayfa_no,
                    "tur": "metin",
                    "bbox": [
                        round(x0, 2),
                        round(y0, 2),
                        round(x1, 2),
                        round(y1, 2),
                    ],
                    "metin": " ".join(
                        k["metin"] for k in kelimeler
                    ),
                })
                # OCR satirlarini paragraflar halinde birlestir.
                paragraflar = []

                for blok in bloklar:
                    if paragraflar:
                        onceki = paragraflar[-1]

                        onceki_bbox = onceki["bbox"]
                        mevcut_bbox = blok["bbox"]

                        yatay_yakin = abs(
                            onceki_bbox[0] - mevcut_bbox[0]
                        ) < 25

                        satir_yuksekligi = max(
                            1,
                            mevcut_bbox[3] - mevcut_bbox[1]
                        )

                        dikey_bosluk = (
                            mevcut_bbox[1] - onceki_bbox[3]
                        )

                        dikey_yakin = (
                            0 <= dikey_bosluk < satir_yuksekligi * 1.5
                        )

                        if yatay_yakin and dikey_yakin:
                            onceki["metin"] += " " + blok["metin"]

                            onceki["bbox"] = [
                                min(onceki_bbox[0], mevcut_bbox[0]),
                                min(onceki_bbox[1], mevcut_bbox[1]),
                                max(onceki_bbox[2], mevcut_bbox[2]),
                                max(onceki_bbox[3], mevcut_bbox[3]),
                            ]

                            continue

                    paragraflar.append(blok.copy())

                # Birlesmis paragraflara yeni ve benzersiz kimlik ver.
                for indeks, paragraf in enumerate(paragraflar, start=1):
                    paragraf["id"] = (
                        f"P{sayfa_no:04d}_OCR{indeks:04d}"
                    )

                bloklar = paragraflar

            ocr_metni = "\n".join(
                blok["metin"] for blok in bloklar
            )

    return {
        "dosya": pdf_yolu.name,
        "sayfa_no": sayfa_no,
        "ocr_dili": dil,
        "karakter_sayisi": len(ocr_metni),
        "metin": ocr_metni,
        "blok_sayisi": len(bloklar),
        "bloklar": bloklar,
    }


def pdf_parca_metin_hazirla(
    pdf_yolu: Path,
    baslangic_sayfasi: int,
    bitis_sayfasi: int,
) -> dict:
    parca = pdf_parca_metni_al(
        pdf_yolu,
        baslangic_sayfasi,
        bitis_sayfasi,
    )

    hazir_sayfalar = []

    for sayfa in parca["sayfalar"]:
        sayfa_turu = sayfa["sayfa_turu"]
        kaynak = "pdf_metin"
        metin = sayfa["metin"]
        ocr_kullanildi = False

        if sayfa_turu == "taranmis_adayi":
            ocr_sonucu = pdf_sayfa_ocr(
                pdf_yolu,
                sayfa["sayfa_no"],
                dil="eng",
            )

            metin = ocr_sonucu["metin"]
            kaynak = "ocr"
            ocr_kullanildi = True

        hazir_sayfalar.append({
            "sayfa_no": sayfa["sayfa_no"],
            "sayfa_turu": sayfa_turu,
            "metin_kaynagi": kaynak,
            "ocr_kullanildi": ocr_kullanildi,
            "karakter_sayisi": len(metin),
            "metin": metin,
        })

    return {
        "dosya": parca["dosya"],
        "baslangic_sayfasi": baslangic_sayfasi,
        "bitis_sayfasi": bitis_sayfasi,
        "sayfalar": hazir_sayfalar,
    }

def dikdortgenler_cakisiyor(
    bbox1: tuple,
    bbox2: tuple,
) -> bool:
    x0_1, y0_1, x1_1, y1_1 = bbox1
    x0_2, y0_2, x1_2, y1_2 = bbox2

    return not (
        x1_1 <= x0_2
        or x1_2 <= x0_1
        or y1_1 <= y0_2
        or y1_2 <= y0_1
    )

def pdf_metin_bloklarini_al(
    pdf_yolu: Path,
    sayfa_no: int,
) -> dict:
    if not pdf_yolu.is_file():
        raise FileNotFoundError(f"PDF dosyasi bulunamadi: {pdf_yolu}")

    with pymupdf.open(pdf_yolu) as belge:
        if sayfa_no < 1 or sayfa_no > len(belge):
            raise ValueError("Sayfa numarasi PDF sinirlarinin disinda.")

        sayfa = belge[sayfa_no - 1]

        # Sayfadaki tablo alanlarini bul.
        bulunan_tablolar = sayfa.find_tables()

        tablo_bboxlari = [
            tuple(tablo.bbox)
            for tablo in bulunan_tablolar.tables
        ]

        ham_bloklar = sayfa.get_text("blocks")

        bloklar = []
        tablo_ici_blok_sayisi = 0
        # Sayfada okunabilir metin yoksa OCR kullan.
        # Sayfadaki secilebilir metin miktarini hesapla.
        secilebilir_metin = " ".join(
            str(blok[4]).strip()
            for blok in ham_bloklar
            if len(blok) > 6 and blok[6] == 0
        )

        # Sayfada goruntu olup olmadigini kontrol et.
        gorsel_var = bool(sayfa.get_images(full=True))

        # Az miktarda secilebilir metin + goruntu varsa
        # sayfanin asil icerigi taranmis olabilir.
        ocr_gerekli = (
            not secilebilir_metin
            or (
                gorsel_var
                and len(secilebilir_metin) < 150
            )
        )

        
        if ocr_gerekli:
            ocr_sonucu = pdf_sayfa_ocr(
                pdf_yolu=pdf_yolu,
                sayfa_no=sayfa_no,
                dil="eng",
            )

            print(
                f"Sayfa {sayfa_no}: OCR kullanildi. "
                f"{ocr_sonucu['blok_sayisi']} metin satiri bulundu."
            )

            return {
                "dosya": pdf_yolu.name,
                "sayfa_no": sayfa_no,
                "blok_sayisi": ocr_sonucu["blok_sayisi"],
                "tablo_ici_blok_sayisi": 0,
                "bloklar": ocr_sonucu["bloklar"],
            }

        for blok in ham_bloklar:
            x0, y0, x1, y1, metin = blok[:5]
            metin = metin.strip()

            if not metin:
                continue

            blok_bbox = (x0, y0, x1, y1)

            tablo_ile_cakisiyor = any(
                dikdortgenler_cakisiyor(
                    blok_bbox,
                    tablo_bbox,
                )
                for tablo_bbox in tablo_bboxlari
            )

            if tablo_ile_cakisiyor:
                # Yalnizca tamamen tablo sinirlari icinde kalan
                # metin bloklarini tablo isleme sistemine birak.
                tamamen_tablo_icinde = any(
                    tablo_bbox[0] <= x0
                    and tablo_bbox[1] <= y0
                    and x1 <= tablo_bbox[2]
                    and y1 <= tablo_bbox[3]
                    for tablo_bbox in tablo_bboxlari
                )

                if tamamen_tablo_icinde:
                    tablo_ici_blok_sayisi += 1
                    continue

                print(
                    f"UYARI: Sayfa {sayfa_no}: "
                    "Tabloyla kismen cakisan metin blogu korundu."
                )

            blok_id = (
                f"P{sayfa_no:04d}_"
                f"B{len(bloklar) + 1:04d}"
            )

            bloklar.append({
                "id": blok_id,
                "sayfa_no": sayfa_no,
                "tur": "metin",
                "bbox": [
                    round(x0, 2),
                    round(y0, 2),
                    round(x1, 2),
                    round(y1, 2),
                ],
                "metin": metin,
            })

    return {
        "dosya": pdf_yolu.name,
        "sayfa_no": sayfa_no,
        "blok_sayisi": len(bloklar),
        "tablo_ici_blok_sayisi": tablo_ici_blok_sayisi,
        "bloklar": bloklar,
    }


def pdf_tablolarini_cikar(
    pdf_yolu: Path,
    sayfa_no: int,
) -> dict:
    if not pdf_yolu.is_file():
        raise FileNotFoundError(f"PDF dosyasi bulunamadi: {pdf_yolu}")

    with pymupdf.open(pdf_yolu) as belge:
        if sayfa_no < 1 or sayfa_no > len(belge):
            raise ValueError("Sayfa numarasi PDF sinirlarinin disinda.")

        sayfa = belge[sayfa_no - 1]

        bulunan = sayfa.find_tables()
        sayfa_kelimeleri = sayfa.get_text("words")

        tablolar = []

        for tablo_no, tablo in enumerate(bulunan.tables, start=1):
            satir_sayisi = tablo.row_count
            sutun_sayisi = tablo.col_count

            hucre_verileri = []

            for hucre in tablo.cells:
                if hucre is None:
                    hucre_verileri.append(None)
                    continue

                x0, y0, x1, y1 = hucre

                kelimeler = []

                for kelime in sayfa_kelimeleri:
                    wx0, wy0, wx1, wy1, metin = kelime[:5]

                    merkez_x = (wx0 + wx1) / 2
                    merkez_y = (wy0 + wy1) / 2

                    if (
                        x0 <= merkez_x <= x1
                        and y0 <= merkez_y <= y1
                    ):
                        kelimeler.append({
                            "metin": metin,
                            "x": wx0,
                            "y": wy0,
                        })

                kelimeler.sort(
                    key=lambda k: (round(k["y"], 1), k["x"])
                )

                metin = " ".join(
                    kelime["metin"]
                    for kelime in kelimeler
                )

                hucre_verileri.append({
                    "bbox": [
                        round(x0, 2),
                        round(y0, 2),
                        round(x1, 2),
                        round(y1, 2),
                    ],
                    "metin": metin,
                })

            satirlar = []

            for satir_no in range(satir_sayisi):
                hucreler = []

                for sutun_no in range(sutun_sayisi):
                    indeks = (
                        satir_no * sutun_sayisi
                        + sutun_no
                    )

                    if indeks >= len(hucre_verileri):
                        print(
                            f"UYARI: Sayfa {sayfa_no}, "
                            f"tablo {tablo_no}, "
                            f"satir {satir_no + 1}, "
                            f"sutun {sutun_no + 1}: "
                            "Hucre verisi eksik."
                        )
                        continue

                    hucre = hucre_verileri[indeks]

                    if hucre is None:
                        continue

                    hucre_id = (
                        f"P{sayfa_no:04d}_"
                        f"T{tablo_no:04d}_"
                        f"R{satir_no + 1:04d}_"
                        f"C{sutun_no + 1:04d}"
                    )

                    hucreler.append({
                        "id": hucre_id,
                        "satir": satir_no + 1,
                        "sutun": sutun_no + 1,
                        "bbox": hucre["bbox"],
                        "metin": hucre["metin"],
                    })

                satirlar.append({
                    "satir": satir_no + 1,
                    "hucreler": hucreler,
                })

            tablolar.append({
                "id": f"P{sayfa_no:04d}_T{tablo_no:04d}",
                "sayfa_no": sayfa_no,
                "tablo_no": tablo_no,
                "satir_sayisi": satir_sayisi,
                "sutun_sayisi": sutun_sayisi,
                "satirlar": satirlar,
            })

    return {
        "dosya": pdf_yolu.name,
        "sayfa_no": sayfa_no,
        "tablo_sayisi": len(tablolar),
        "tablolar": tablolar,
    }

def pdf_sayfa_yapisini_cikar(
    pdf_yolu: Path,
    sayfa_no: int,
) -> dict:
    metin_sonucu = pdf_metin_bloklarini_al(
        pdf_yolu=pdf_yolu,
        sayfa_no=sayfa_no,
    )

    tablo_sonucu = pdf_tablolarini_cikar(
        pdf_yolu=pdf_yolu,
        sayfa_no=sayfa_no,
    )
    # Tablo icine aktarilan metin bloklarini kontrol et.
    with pymupdf.open(pdf_yolu) as belge:
        sayfa = belge[sayfa_no - 1]

        tablo_bboxlari = [
            tuple(tablo.bbox)
            for tablo in sayfa.find_tables().tables
        ]

        for ham_blok in sayfa.get_text("blocks"):
            x0, y0, x1, y1, metin = ham_blok[:5]
            metin = metin.strip()

            if not metin:
                continue

            tamamen_tablo_icinde = any(
                tx0 <= x0
                and ty0 <= y0
                and x1 <= tx1
                and y1 <= ty1
                for tx0, ty0, tx1, ty1 in tablo_bboxlari
            )

            if not tamamen_tablo_icinde:
                continue

            tablo_metinleri = [
                hucre["metin"]
                for tablo in tablo_sonucu["tablolar"]
                for satir in tablo["satirlar"]
                for hucre in satir["hucreler"]
            ]

            kaynak_kelimeler = metin.split()
            tablo_kelimeleri = " ".join(tablo_metinleri).split()

            eksik_kelimeler = [
                kelime
                for kelime in kaynak_kelimeler
                if kelime not in tablo_kelimeleri
            ]

            if eksik_kelimeler:
                print(
                    f"UYARI: Sayfa {sayfa_no}: "
                    f"Tabloya aktarilmayan kelimeler: "
                    f"{eksik_kelimeler}"
            )

    return {
        "dosya": pdf_yolu.name,
        "sayfa_no": sayfa_no,
        "metin_blok_sayisi": metin_sonucu["blok_sayisi"],
        "tablo_sayisi": tablo_sonucu["tablo_sayisi"],
        "metin_bloklari": metin_sonucu["bloklar"],
        "tablolar": tablo_sonucu["tablolar"],
    }

def ceviri_icin_paragraflari_birlestir(bloklar: list[dict]) -> list[dict]:
    sonuc = []

    for blok in bloklar:
        metin = " ".join(blok["metin"].split())

        if not metin:
            continue

        yeni_blok = {
            **blok,
            "metin": metin,
            "kaynak_idler": [blok["id"]],
        }

        if sonuc:
            onceki = sonuc[-1]

            onceki_metin = onceki["metin"]
            onceki_bbox = onceki["bbox"]
            mevcut_bbox = blok["bbox"]

            yatay_hizali = abs(
                onceki_bbox[0] - mevcut_bbox[0]
            ) < 15

            dikey_yakin = (
                0 <= mevcut_bbox[1] - onceki_bbox[3] < 18
            )

            onceki_devam_ediyor = not onceki_metin.endswith(
                (".", "!", "?", ":", ";")
            )
            onceki_baslik = (
            onceki_metin.isupper()
            and len(onceki_metin) < 100
            )

            if (
           yatay_hizali
           and dikey_yakin
           and onceki_devam_ediyor
           and not onceki_baslik
             ):
                onceki["metin"] += " " + metin
                onceki["bbox"] = [
                    min(onceki_bbox[0], mevcut_bbox[0]),
                    min(onceki_bbox[1], mevcut_bbox[1]),
                    max(onceki_bbox[2], mevcut_bbox[2]),
                    max(onceki_bbox[3], mevcut_bbox[3]),
                ]
                onceki["kaynak_idler"].append(blok["id"])
                continue

        sonuc.append(yeni_blok)

    return sonuc

def matematiksel_formul_mu(metin: str) -> bool:
    metin = metin.strip()

    if not metin or "\n" in metin:
        return False

    if "=" not in metin:
        return False

    # Aciklama iceren satirlari formul olarak eleme.
    # Ornek: Calculated Input Power Requirement: Phyd = ...
    if ":" in metin:
        return False

    # Saf matematiksel ifadeler korunsun.
    return bool(
        re.fullmatch(
            r"[\w\s=+\-*/^().,×÷√∑∫≈≤≥∞πηρ%]+",
            metin,
            flags=re.UNICODE
        )
    )

def ceviri_bloklarini_hazirla(bloklar: list[dict]) -> list[dict]:
    hazir_bloklar = ceviri_icin_paragraflari_birlestir(bloklar)

    for blok in hazir_bloklar:
        if matematiksel_formul_mu(blok["metin"]):
            blok["tur"] = "formul"
            blok["cevrilecek"] = False
        else:
            blok["cevrilecek"] = True

    return hazir_bloklar