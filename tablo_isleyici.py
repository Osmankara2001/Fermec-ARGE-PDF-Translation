
import re
from copy import deepcopy

import requests
import os


API = os.getenv("PDF_API_URL", "http://localhost:8000")
CEVIRI = os.getenv("CEVIRI_URL", "http://localhost:8001")


def sadece_sayisal_deger(metin):
    """
    Yalnizca sayisal degerlerden olusan hucreleri belirler.
    Metin iceren hucreler ceviriye gonderilir.
    """
    metin = metin.strip()

    if not metin:
        return True

    return bool(
        re.fullmatch(r"[\d\s.,+\-–−/%°@]+", metin)
    )


def teknik_degerleri_al(metin):
    """
    Sayilari ve sayilarla birlikte yazilan birimleri bulur.
    """
    sayilar = re.findall(
        r"(?<![\w])[-+]?\d+(?:[.,]\d+)*",
        metin
    )

    return sorted(sayilar)


def tablo_yapisini_dogrula(tablo):
    """
    Satir, sutun ve hucre koordinatlarini kontrol eder.
    """
    satirlar = tablo["satirlar"]

    if len(satirlar) != tablo["satir_sayisi"]:
        raise ValueError(
            f'{tablo["id"]}: Satir sayisi uyusmuyor.'
        )

    gorulen_konumlar = set()

    for satir in satirlar:
        for hucre in satir["hucreler"]:
            konum = (
                hucre["satir"],
                hucre["sutun"]
            )

            if konum in gorulen_konumlar:
                raise ValueError(
                    f'{tablo["id"]}: Tekrarlanan hucre {konum}'
                )

            gorulen_konumlar.add(konum)

            if not (
                1 <= hucre["satir"] <= tablo["satir_sayisi"]
                and
                1 <= hucre["sutun"] <= tablo["sutun_sayisi"]
            ):
                raise ValueError(
                    f'{hucre["id"]}: Gecersiz hucre konumu.'
                )

            bbox = hucre.get("bbox")

            if (
                not bbox
                or len(bbox) != 4
                or bbox[0] >= bbox[2]
                or bbox[1] >= bbox[3]
            ):
                raise ValueError(
                    f'{hucre["id"]}: Gecersiz koordinat.'
                )


def sayfa_tablolarini_al(sayfa_no):
    """
    Mevcut PDF API'sinden tablo verilerini alir.
    """
    yanit = requests.get(
        f"{API}/pdf/page/{sayfa_no}/tables",
        timeout=120
    )

    yanit.raise_for_status()

    return yanit.json()


def sayfa_tablolarini_cevir(sayfa_no):
    """
    Bir sayfadaki tum tablolarin hucrelerini cevirir.

    Sabit tablo sayisi, hucre sayisi veya koordinat kullanmaz.
    """
    veri = sayfa_tablolarini_al(sayfa_no)
    sonuc = deepcopy(veri)

    cevrilecek_bloklar = []
    hucre_haritasi = {}

    for tablo in sonuc["tablolar"]:
        tablo_yapisini_dogrula(tablo)

        for satir in tablo["satirlar"]:
            for hucre in satir["hucreler"]:
                hucre_id = hucre["id"]
                kaynak_metin = hucre.get("metin", "").strip()

                hucre["ceviri"] = kaynak_metin

                if hucre_id in hucre_haritasi:
                    raise ValueError(
                        f"Tekrarlanan hucre ID: {hucre_id}"
                    )

                hucre_haritasi[hucre_id] = hucre

                if sadece_sayisal_deger(kaynak_metin):
                    continue

                cevrilecek_bloklar.append({
                    "id": hucre_id,
                    "metin": kaynak_metin
                })

    if not cevrilecek_bloklar:
        return sonuc

    yanit = requests.post(
        f"{CEVIRI}/translate",
        json={"bloklar": cevrilecek_bloklar},
        timeout=300
    )

    yanit.raise_for_status()

    ceviri_sonucu = yanit.json()
    ceviriler = ceviri_sonucu.get(
        "ceviri_bloklari", []
    )

    beklenen_idler = {
        blok["id"] for blok in cevrilecek_bloklar
    }

    gelen_idler = [
        blok["id"] for blok in ceviriler
    ]

    if (
        len(gelen_idler) != len(beklenen_idler)
        or set(gelen_idler) != beklenen_idler
    ):
        raise ValueError(
            f"Sayfa {sayfa_no}: Eksik veya fazla tablo cevirisi."
        )

    for blok in ceviriler:
        hucre_id = blok["id"]
        hucre = hucre_haritasi[hucre_id]

        kaynak = hucre["metin"]
        ceviri = (blok.get("ceviri") or "").strip()

        if not ceviri:
            raise ValueError(
                f"{hucre_id}: Bos ceviri."
            )

        if teknik_degerleri_al(kaynak) != teknik_degerleri_al(ceviri):
            raise ValueError(
                f"{hucre_id}: Sayisal degerler degisti."
            )

        hucre["ceviri"] = ceviri

    return sonuc
