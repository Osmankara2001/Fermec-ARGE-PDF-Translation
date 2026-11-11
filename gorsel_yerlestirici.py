
import pymupdf


def sayfa_gorsellerini_yerlestir(
    kaynak_pdf,
    kaynak_sayfa,
    hedef_sayfa
):
    """
    Kaynak sayfadaki gomulu gorselleri
    hedef sayfaya orijinal konumlarinda yerlestirir.
    """

    gorsel_sayisi = 0
    islenen_xrefler = set()

    for gorsel in kaynak_sayfa.get_images(full=True):
        xref = gorsel[0]

        if xref in islenen_xrefler:
            continue

        islenen_xrefler.add(xref)

        konumlar = kaynak_sayfa.get_image_rects(xref)

        if not konumlar:
            continue

        gorsel_verisi = kaynak_pdf.extract_image(xref)

        if not gorsel_verisi:
            print(
                f"UYARI: XREF {xref} gorsel verisi alinamadi."
            )
            continue

        for konum in konumlar:
            if konum.is_empty or konum.is_infinite:
                continue

            hedef_sayfa.insert_image(
                konum,
                stream=gorsel_verisi["image"],
                keep_proportion=False,
                overlay=True
            )

            gorsel_sayisi += 1

    return gorsel_sayisi
