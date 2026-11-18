
import pymupdf


def sayfa_gorsellerini_yerlestir(
    kaynak_pdf,
    kaynak_sayfa,
    hedef_sayfa
):
    """
    Gorselleri kaynak PDF'deki cizim sirasini,
    konumlarini ve saydamliklarini koruyarak aktarir.
    """

    gorsel_sayisi = 0
    gorsel_onbellegi = {}

    # Her gorselin saydamlik maskesini bul.
    maskeler = {
        gorsel[0]: gorsel[1]
        for gorsel in kaynak_sayfa.get_images(full=True)
    }

    # Gorselleri sayfadaki gercek kullanim sirasina gore al.
    gorseller = kaynak_sayfa.get_image_info(xrefs=True)

    for gorsel in gorseller:
        xref = gorsel.get("xref", 0)

        if not xref:
            print(
                "UYARI: XREF bilgisi olmayan gorsel atlandi.",
                flush=True
            )
            continue

        konum = pymupdf.Rect(gorsel["bbox"])

        if konum.is_empty or konum.is_infinite:
            continue

        try:
            if xref not in gorsel_onbellegi:
                ana_gorsel = pymupdf.Pixmap(
                    kaynak_pdf, xref
                )

                smask = maskeler.get(xref, 0)

                if smask:
                    maske = pymupdf.Pixmap(
                        kaynak_pdf, smask
                    )

                    birlesik = pymupdf.Pixmap(
                        ana_gorsel, maske
                    )

                    gorsel_verisi = birlesik.tobytes("png")

                else:
                    gorsel_verisi = ana_gorsel.tobytes("png")

                gorsel_onbellegi[xref] = gorsel_verisi

            hedef_sayfa.insert_image(
                konum,
                stream=gorsel_onbellegi[xref],
                keep_proportion=False,
                overlay=True
            )

            gorsel_sayisi += 1

        except Exception as hata:
            print(
                f"UYARI: XREF {xref} "
                f"gorseli yerlestirilemedi: {hata}",
                flush=True
            )

    return gorsel_sayisi
