

from pathlib import Path
import pymupdf
import subprocess
import tempfile

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

        # OCR icin sayfayi gecici olarak yuksek cozunurlukte goruntuye cevir.
        pix = sayfa.get_pixmap(dpi=300, alpha=False)

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
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            if sonuc.returncode != 0:
                raise RuntimeError(
                    f"Tesseract OCR hatasi: {sonuc.stderr.strip()}"
                )

            ocr_metni = sonuc.stdout.strip()

    return {
        "dosya": pdf_yolu.name,
        "sayfa_no": sayfa_no,
        "ocr_dili": dil,
        "karakter_sayisi": len(ocr_metni),
        "metin": ocr_metni,
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