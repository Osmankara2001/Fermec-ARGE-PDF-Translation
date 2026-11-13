
from pathlib import Path
import json
import requests
import pymupdf
import os
import re
from tablo_isleyici import sayfa_tablolarini_cevir
from tablo_cizici import sayfa_tablolarini_ciz
from gorsel_yerlestirici import sayfa_gorsellerini_yerlestir

API = os.getenv("PDF_API_URL", "http://localhost:8000")
CEVIRI = os.getenv("CEVIRI_URL", "http://localhost:8001")

OUTPUT = Path(os.getenv("OUTPUT_DIR", "output"))
OUTPUT.mkdir(exist_ok=True)


def api_get(url):
    yanit = requests.get(url, timeout=120)
    yanit.raise_for_status()
    return yanit.json()



def cift_dilli_pdf_uret(pdf_yolu, tum_ceviriler,tum_tablolar):
    kaynak = pymupdf.open(pdf_yolu)
    cikti = pymupdf.open()

    font_yolu = Path(
    os.getenv(
        "TURKCE_FONT",
        "C:/Windows/Fonts/arial.ttf"
    )
)

    if not font_yolu.exists():
        raise FileNotFoundError(
            f"Turkce font bulunamadi: {font_yolu}"
        )

    for sayfa_no, orijinal in enumerate(kaynak, start=1):
        genislik = orijinal.rect.width
        yukseklik = orijinal.rect.height

        yeni = cikti.new_page(
            width=genislik * 2,
            height=yukseklik
        )

        # Sag tarafa orijinal sayfayi vektorel yerlestir.
        yeni.show_pdf_page(
            pymupdf.Rect(
                genislik, 0,
                genislik * 2, yukseklik
            ),
            kaynak,
            sayfa_no - 1
        )

        yeni.insert_font(
            fontname="turkce",
            fontfile=str(font_yolu)
        )
        # Tamamen taranmis sayfalarda orijinal goruntu,
        # Ingilizce metinleri de icerdigi icin sol tarafa kopyalanmaz.
        # Sag taraftaki orijinal sayfa her durumda korunur.

        # API tarafindaki OCR karar kuraliyla ayni kontrol.
        secilebilir_metin = orijinal.get_text().strip()

        sayfa_gorsel_var = bool(
            orijinal.get_images(full=True)
        )

        taranmis_sayfa = (
            not secilebilir_metin
            or (
                sayfa_gorsel_var
                and len(secilebilir_metin) < 150
            )
        )

        if taranmis_sayfa:
            gorsel_sayisi = 0
            print(
                f"Sayfa {sayfa_no}: Taranmis sayfa algilandi. "
                "Orijinal goruntu sol tarafa kopyalanmadi."
            )
        else:
            gorsel_sayisi = sayfa_gorsellerini_yerlestir(
                kaynak,
                orijinal,
                yeni
            )

        print(
            f"Sayfa {sayfa_no}: "
            f"{gorsel_sayisi} gorsel yerlestirildi."
        )
        # Bu sayfanin cevrilmis tablolarini al.
        sayfa_tablolari = tum_tablolar.get(
            str(sayfa_no), []
        )

        # Tablolari sol sayfaya yerlestir.
        sayfa_tablolarini_ciz(
            yeni,
            sayfa_tablolari,
            font_adi="turkce"
        )
        ceviriler = tum_ceviriler.get(str(sayfa_no), [])
        # Metin bloklarini sayfadaki dikey konumlarina gore sirala.
        ceviriler = sorted(
            ceviriler,
                key=lambda blok: min(
                (bbox[1] for bbox in blok.get("kaynak_bboxlar", [])),
                 default=float("inf")
                )
            )
        if taranmis_sayfa:
            # OCR bloklarini once gecici sayfada dene. Boylece tek bir
            # blok bile tasarsa eksik veya ust uste binmis PDF olusmaz.
            # Tum bloklarda ayni puntoyu kullanarak sayfayi sigdir.
            if sayfa_tablolari:
                print(
                    f"UYARI: Sayfa {sayfa_no}: OCR sayfasinda tablo var; "
                    "metin ile tablo cakisabilir.",
                    flush=True,
                )

            yerlestirme_plani = None
            for font_boyutu in (10, 9, 8, 7, 6, 5, 4):
                deneme_pdf = pymupdf.open()
                deneme_sayfasi = deneme_pdf.new_page(
                    width=genislik, height=yukseklik
                )
                deneme_sayfasi.insert_font(
                    fontname="turkce", fontfile=str(font_yolu)
                )
                plan = []
                son_y = 25.0
                uygun = True

                for blok in ceviriler:
                    metin = blok.get("ceviri", "").strip()
                    if not metin:
                        continue
                    bboxlar = blok.get("kaynak_bboxlar", [])
                    if not bboxlar:
                        deneme_pdf.close()
                        raise RuntimeError(
                            f"Sayfa {sayfa_no}, blok {blok.get('id')}: "
                            "Konum bilgisi bulunamadi."
                        )

                    # Tam genislik, kaynak metnin yatay hizasina yakin.
                    x0 = max(25.0, min(float(b[0]) for b in bboxlar))
                    x0 = min(x0, genislik - 75.0)
                    x1 = genislik - 25.0
                    y0 = son_y
                    y1 = yukseklik - 25.0
                    if x1 <= x0 or y1 <= y0:
                        uygun = False
                        break
                    alan = pymupdf.Rect(x0, y0, x1, y1)
                    kalan = deneme_sayfasi.insert_textbox(
                        alan,
                        metin,
                        fontsize=font_boyutu,
                        fontname="turkce",
                        lineheight=1.1,
                    )
                    if kalan < 0:
                        uygun = False
                        break

                    plan.append((alan, metin))
                    # insert_textbox sonucu basarida kullanilmayan
                    # dikey alandir; bir sonraki blok icin yer ayir.
                    son_y = alan.y1 - kalan + max(3.0, font_boyutu * 0.5)

                deneme_pdf.close()
                if uygun:
                    yerlestirme_plani = (font_boyutu, plan)
                    break

            if yerlestirme_plani is None:
                raise RuntimeError(
                    f"Sayfa {sayfa_no}: OCR cevirisi 4 puntoya kadar "
                    "denendi ancak sigmadi. Metin kaybi engellendi."
                )

            font_boyutu, plan = yerlestirme_plani
            if font_boyutu < 10:
                print(
                    f"UYARI: Sayfa {sayfa_no}: OCR metni "
                    f"{font_boyutu} puntoya kucultuldu.",
                    flush=True,
                )
            for alan, metin in plan:
                sonuc = yeni.insert_textbox(
                    alan,
                    metin,
                    fontsize=font_boyutu,
                    fontname="turkce",
                    lineheight=1.1,
                    overlay=True,
                )
                if sonuc < 0:
                    raise RuntimeError(
                        f"Sayfa {sayfa_no}: OCR yerlesimi "
                        "on kontrolden farkli sonuc verdi."
                    )
            continue

        # Metin tabanli PDF'lerde onceki konum koruma mantigi.
        for blok_index, blok in enumerate(ceviriler):
            metin = blok.get("ceviri", "").strip()
            bboxlar = blok.get("kaynak_bboxlar", [])
            if not metin:
                continue
            if not bboxlar:
                raise RuntimeError(
                    f"Sayfa {sayfa_no}, blok {blok.get('id')}: "
                    "Konum bilgisi bulunamadi. Metin kaybi onlendi."
                )

            x0 = min(bbox[0] for bbox in bboxlar)
            y0 = min(bbox[1] for bbox in bboxlar)
            x1 = max(bbox[2] for bbox in bboxlar)
            y1 = max(bbox[3] for bbox in bboxlar)
            x1 = min(genislik - 25, max(x1, x0 + 100))

            sonraki_y = yukseklik - 25
            for sonraki_blok in ceviriler[blok_index + 1:]:
                sonraki_bboxlar = sonraki_blok.get("kaynak_bboxlar", [])
                if sonraki_bboxlar:
                    sonraki_y = min(bbox[1] for bbox in sonraki_bboxlar)
                    break

            guvenli_alt = min(yukseklik - 25, sonraki_y - 8)
            if guvenli_alt > y1:
                y1 = guvenli_alt
            alan = pymupdf.Rect(x0, y0, x1, y1)

            yerlesti = False
            for font_boyutu in (10, 9, 8, 7, 6, 5):
                sonuc = yeni.insert_textbox(
                    alan,
                    metin,
                    fontsize=font_boyutu,
                    fontname="turkce",
                    lineheight=1.1,
                    overlay=True,
                )
                if sonuc >= 0:
                    yerlesti = True
                    break
            if not yerlesti:
                raise RuntimeError(
                    f"Sayfa {sayfa_no}, blok {blok.get('id')}: "
                    "Turkce metin alana sigmadi. "
                    "Eksik PDF olusturulmasi engellendi."
                )

    OUTPUT.mkdir(exist_ok=True)

    cikti_yolu = OUTPUT / (
        f"{Path(pdf_yolu).stem}_TR_EN.pdf"
    )

    cikti.save(cikti_yolu)
    cikti.close()
    kaynak.close()

    print(
        f"\nCift dilli PDF olusturuldu: {cikti_yolu}"
    )





def main():
    analiz = api_get(f"{API}/pdf/analyze")

    dosya_adi = analiz["dosya"]
    toplam_sayfa = analiz["toplam_sayfa"]

    print(f"PDF: {dosya_adi}")
    print(f"Toplam sayfa: {toplam_sayfa}")

    tum_ceviriler = {}
    tum_tablolar = {}

    # Her pencere en fazla 5 sayfa icerir.
    PENCERE_BOYUTU = 5

    for pencere_baslangic in range(
        1, toplam_sayfa + 1, PENCERE_BOYUTU
    ):
        pencere_bitis = min(
            pencere_baslangic + PENCERE_BOYUTU - 1,
            toplam_sayfa
        )

        print(
            f"\n=== PENCERE: "
            f"{pencere_baslangic}-{pencere_bitis} ==="
        )

        # Pencere icindeki sayfalari sirayla isle.
        for sayfa_no in range(
            pencere_baslangic, pencere_bitis + 1
        ):
            print(f"\nSayfa {sayfa_no}/{toplam_sayfa}")

            try:
                veri = api_get(
                    f"{API}/pdf/page/{sayfa_no}/translation-ready"
                )

                bloklar = [
                    {
                        "id": blok["id"],
                        "metin": blok["metin"]
                    }
                    for blok in veri["cevrilecek_bloklar"]
                ]

                # OCR dahil tum metinler artik API tarafinda
                # koordinatlariyla birlikte hazirlaniyor.
                if not bloklar:
                    print(
                        f"Sayfa {sayfa_no}: "
                        "Cevirilecek metin bulunamadi."
                    )
                    tum_ceviriler[str(sayfa_no)] = []
                    continue

                # OpenAI ceviri servisine gonder.
                yanit = requests.post(
                    f"{CEVIRI}/translate",
                    json={"bloklar": bloklar},
                    timeout=300
                )

                yanit.raise_for_status()

                sonuc = yanit.json()

                ceviriler = sonuc.get(
                    "ceviri_bloklari", []
                )
                # Kaynak ve ceviri bloklarini dogrula.
                kaynak_idler = [blok["id"] for blok in bloklar]
                ceviri_idler = [blok["id"] for blok in ceviriler]

                if (
                    len(kaynak_idler) != len(set(kaynak_idler))
                    or len(ceviri_idler) != len(set(ceviri_idler))
                    or set(kaynak_idler) != set(ceviri_idler)
                ):
                    raise RuntimeError(
                        f"Sayfa {sayfa_no}: Ceviri blok kimlikleri "
                        "kaynak bloklarla eslesmiyor."
                    )

                for blok in ceviriler:
                    if not isinstance(blok.get("ceviri"), str) or not blok["ceviri"].strip():
                        raise RuntimeError(
                            f"Sayfa {sayfa_no}, blok {blok['id']}: "
                             "Bos veya gecersiz ceviri."
                        )

                print(f"Sayfa {sayfa_no}: Ceviri blok kontrolu basarili.")



                # Kaynak PDF'deki konum bilgilerini eslestir.
                konumlar = {
                    blok["id"]: blok.get(
                        "kaynak_bboxlar", []
                    )
                    for blok in veri["cevrilecek_bloklar"]
                }

                for blok in ceviriler:
                    blok["kaynak_bboxlar"] = (
                        konumlar.get(
                            blok["id"], []
                        )
                    )

                tum_ceviriler[str(sayfa_no)] = ceviriler

                print(
                    f"Cevirilen blok: {len(ceviriler)}"
                )

                # Tablo islemini metin cevirisinden ayri tut.
                try:
                    tablo_sonucu = sayfa_tablolarini_cevir(
                        sayfa_no
                    )

                    tum_tablolar[str(sayfa_no)] = (
                        tablo_sonucu["tablolar"]
                    )

                    print(
                        f'Islenen tablo: '
                        f'{tablo_sonucu["tablo_sayisi"]}'
                    )

                except Exception as tablo_hatasi:
                    raise RuntimeError(
                         f"Sayfa {sayfa_no}: Tablo isleme basarisiz: "
                         f"{tablo_hatasi}"
                    ) from tablo_hatasi

            except Exception as hata:
                print(
                    f"HATA: Sayfa {sayfa_no} islenirken "
                    f"islem durduruldu: {hata}",
                    flush=True
                )
                raise
                 
                 
            
         # Bu pencerenin cevirilerini ayri kaydet.
        pencere_cevirileri = {
            str(sayfa): tum_ceviriler.get(str(sayfa), [])
            for sayfa in range(
                pencere_baslangic,
                pencere_bitis + 1
            )
        }

        pencere_dosyasi = OUTPUT / (
            f"pencere_{pencere_baslangic:04d}_"
            f"{pencere_bitis:04d}.json"
        )

        with open(
            pencere_dosyasi, "w", encoding="utf-8"
        ) as dosya:
            json.dump(
                pencere_cevirileri,
                dosya,
                ensure_ascii=False,
                indent=2
            )

        print(f"Pencere kaydedildi: {pencere_dosyasi}")


        print(
            f"\n=== PENCERE TAMAMLANDI: "
            f"{pencere_baslangic}-{pencere_bitis} ==="
        )


    tablo_ciktisi = OUTPUT / "otomatik_tablolar.json"

    with open(
        tablo_ciktisi, "w", encoding="utf-8"
    ) as dosya:
        json.dump(
            tum_tablolar,
            dosya,
            ensure_ascii=False,
            indent=2
        )

    print(f"Tablolar kaydedildi: {tablo_ciktisi}")

    # Tum sayfalarin cevirilerini JSON olarak kaydet.
    cikti = OUTPUT / "otomatik_ceviriler.json"

    with open(
        cikti, "w", encoding="utf-8"
    ) as dosya:
        json.dump(
            tum_ceviriler,
            dosya,
            ensure_ascii=False,
            indent=2
        )

    print(f"\nCeviriler kaydedildi: {cikti}")

    # Tum sayfalari tek bir cift dilli PDF'e donustur.
    pdf_yolu = Path(os.getenv("INPUT_DIR", "input")) / dosya_adi

    cift_dilli_pdf_uret(
        pdf_yolu,
        tum_ceviriler,
        tum_tablolar
    )


if __name__ == "__main__":
    main()

