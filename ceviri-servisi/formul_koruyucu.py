
import re


def formul_satiri_mi(metin):
    """
    Tek basina matematiksel ifade olan
    satirlari tespit etmeye calisir.
    """

    metin = metin.strip()

    if not metin or "=" not in metin:
        return False

    # Formul satirlarinda beklenen karakterler.
    izinli = re.fullmatch(
        r"[\w\s=+\-*/^().,×÷√∑∫≈≤≥∞πηρ%]+",
        metin,
        flags=re.UNICODE
    )

    if not izinli:
        return False

    # En az bir matematiksel islem bulunmali.
    return bool(
        re.search(r"[=+*/^×÷]", metin)
    )


def formul_satirlarini_koru(metin):
    """
    Tek basina formul olan satirlari
    degistirilemez yer tutucularla saklar.
    """

    satirlar = metin.splitlines()
    korunan = {}
    sonuc = []

    for satir in satirlar:
        if formul_satiri_mi(satir):
            anahtar = f"FORMULKORUMA{len(korunan):04d}"
            korunan[anahtar] = satir
            sonuc.append(anahtar)
        else:
            sonuc.append(satir)

    return "\n".join(sonuc), korunan


def formulleri_geri_yerlestir(metin, korunan):
    """
    Ceviri sonrasinda saklanan formulleri
    orijinal halleriyle geri yerlestirir.
    """

    for anahtar, formul in korunan.items():
        adet = metin.count(anahtar)

        if adet != 1:
            raise ValueError(
                f"Formul yer tutucusu bozuldu: {anahtar}"
            )

        metin = metin.replace(anahtar, formul)

    return metin
