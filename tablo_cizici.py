
import pymupdf


def sayfa_tablolarini_ciz(sayfa, tablolar, font_adi="turkce"):
    """
    Cevrilmis tablolari PDF'in sol sayfasina cizer.

    Hucrelerin orijinal koordinatlarini kullanir.
    Sabit tablo, satir veya sutun sayisi kullanmaz.
    """
    uyari_listesi = []

    for tablo in tablolar:
        tablo_id = tablo["id"]

        for satir in tablo["satirlar"]:
            for hucre in satir["hucreler"]:
                hucre_id = hucre["id"]
                metin = str(
                    hucre.get("ceviri")
                    or hucre.get("metin")
                    or ""
                ).strip()

                bbox = hucre["bbox"]
                alan = pymupdf.Rect(bbox)

                if (
                    alan.is_empty
                    or alan.is_infinite
                    or not sayfa.rect.contains(alan)
                ):
                    uyari_listesi.append(
                        f"{hucre_id}: Gecersiz hucre alani."
                    )
                    continue

                # Hucre arka planini ciz.
                # Baslik satirini acik gri yap.
                arka_plan = (
                    (0.92, 0.92, 0.92)
                    if hucre["satir"] == 1
                    else (1, 1, 1)
                )

                sayfa.draw_rect(
                    alan,
                    color=(0.45, 0.45, 0.45),
                    fill=arka_plan,
                    width=0.5,
                    overlay=True
                )

                if not metin:
                    continue

                # Metnin cerceveye degmemesi icin bosluk.
                metin_alani = pymupdf.Rect(
                    alan.x0 + 3,
                    alan.y0 + 2,
                    alan.x1 - 3,
                    alan.y1 - 2
                )

                if metin_alani.is_empty:
                    uyari_listesi.append(
                        f"{hucre_id}: Metin alani cok dar."
                    )
                    continue

                yerlesti = False

                # Buyuk fonttan kucuge dogru dene.
                for font_boyutu in (9, 8, 7, 6, 5, 4):
                    # shape ile deneme yapilir.
                    # Metin sigmazsa sayfaya yazilmaz.
                    sekil = sayfa.new_shape()

                    sonuc = sekil.insert_textbox(
                        metin_alani,
                        metin,
                        fontname=font_adi,
                        fontsize=font_boyutu,
                        lineheight=1.1,
                        color=(0, 0, 0),
                        align=pymupdf.TEXT_ALIGN_LEFT
                    )

                    if sonuc >= 0:
                        sekil.commit(overlay=True)
                        yerlesti = True
                        break

                if not yerlesti:
                    uyari_listesi.append(
                        f"{hucre_id}: Metin hucreye sigmadi."
                    )

        print(f"Tablo cizildi: {tablo_id}")

    for uyari in uyari_listesi:
        print(f"UYARI: {uyari}")

    return uyari_listesi
