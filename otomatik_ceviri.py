
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
                # Orijinal sayfadaki gorselleri sol tarafa aktar.
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

        for blok in ceviriler:
            metin = blok.get("ceviri", "").strip()
            bboxlar = blok.get("kaynak_bboxlar", [])

            if not metin:
                continue

            if not bboxlar:
                print(
                    f"UYARI: Sayfa {sayfa_no}, "
                    f"{blok.get('id')} konum bilgisi yok."
                )
                continue

            # Birlesmis kaynak bloklarinin tamamini kapsayan alan.
            x0 = min(bbox[0] for bbox in bboxlar)
            y0 = min(bbox[1] for bbox in bboxlar)
            x1 = max(bbox[2] for bbox in bboxlar)
            y1 = max(bbox[3] for bbox in bboxlar)

            # Turkce metin daha uzun olabilecegi icin
            # kutuyu sag tarafa dogru genislet.
            x1 = min(genislik - 25, max(x1, x0 + 100))

            alan = pymupdf.Rect(
                x0, y0,
                x1, y1
            )

            yerlesti = False

            for font_boyutu in (10, 9, 8, 7, 6, 5):
                sonuc = yeni.insert_textbox(
                    alan,
                    metin,
                    fontsize=font_boyutu,
                    fontname="turkce",
                    lineheight=1.1,
                    overlay=True
                )

                if sonuc >= 0:
                    yerlesti = True
                    break

            if not yerlesti:
                print(
                    f"UYARI: Sayfa {sayfa_no}, "
                    f"{blok.get('id')} metni alana sigmadi."
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

                # Normal metin yoksa OCR dene.
                if not bloklar:
                    print(
                        "Metin bulunamadi. OCR deneniyor..."
                    )

                    ocr = api_get(
                        f"{API}/pdf/ocr/{sayfa_no}"
                    )

                    ocr_metni = (
                        ocr.get("metin") or ""
                    ).strip()

                    if ocr_metni:
                        bloklar = [
                            {
                                "id": (
                                    f"P{sayfa_no:04d}_OCR_0001"
                                ),
                                "metin": ocr_metni
                            }
                        ]

                        print("OCR ile metin bulundu.")

                    else:
                        print(
                            "OCR ile de metin bulunamadi."
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
                    print(
                        f"UYARI: Sayfa {sayfa_no}, "
                        f"tablo isleme hatasi: {tablo_hatasi}"
                    )

                    tum_tablolar[str(sayfa_no)] = []

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

