
from pathlib import Path
import json
import requests
import pymupdf
import os
import re
from datetime import datetime, timezone
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



def izlenebilirlik_raporu_yaz(dosya_adi, toplam_sayfa, tum_ceviriler, tum_tablolar, sayfa_kullanim, sayfa_duzeltmeler):
    """Basariyla uretilen PDF icin kaynak-ceviri esleme kaydi olusturur."""
    sayfalar = []
    for sayfa_no in range(1, toplam_sayfa + 1):
        bloklar = tum_ceviriler.get(str(sayfa_no), [])
        kayitlar = []
        for blok in bloklar:
            blok_id = blok["id"]
            kayitlar.append({
                "blok_id": blok_id,
                "okuma_yontemi": "ocr" if "_OCR" in blok_id else "metin",
                "kaynak_metin": blok.get("kaynak_metin", ""),
                "turkce_ceviri": blok["ceviri"],
                "kaynak_bboxlar": blok.get("kaynak_bboxlar", []),
                "blok_kontrolu": "kimlik_ve_bos_metin_kontrolu_gecti",
            })
        sayfalar.append({
            "sayfa": sayfa_no,
            "blok_sayisi": len(kayitlar),
            "tablo_sayisi": len(tum_tablolar.get(str(sayfa_no), [])),
            "api_kullanim": sayfa_kullanim.get(str(sayfa_no)),
            "duzeltme_gecmisi": sayfa_duzeltmeler.get(str(sayfa_no), []),
            "bloklar": kayitlar,
        })

    rapor = {
        "kaynak_pdf": dosya_adi,
        "cikti_pdf": f"{Path(dosya_adi).stem}_TR_EN.pdf",
        "olusturulma_zamani_utc": datetime.now(timezone.utc).isoformat(),
        "durum": "pdf_olusturuldu",
        "toplam_sayfa": toplam_sayfa,
        "toplam_ceviri_blogu": sum(s["blok_sayisi"] for s in sayfalar),
        "aciklama": (
            "Blok kontrolu, PDF isleyicinin kimlik ve bos ceviri kontrollerini "
            "gosterir. OCR dogrulugu ve anlamsal ceviri kalitesi onaylandi anlamina gelmez. "
            "Duzeltme gecmisi sadece ceviri servisinin raporladigi denemeleri kapsar."
        ),
        "sayfalar": sayfalar,
    }
    hedef = OUTPUT / f"{Path(dosya_adi).stem}_izlenebilirlik.json"
    with hedef.open("w", encoding="utf-8") as dosya:
        json.dump(rapor, dosya, ensure_ascii=False, indent=2)
    print(f"Izlenebilirlik raporu kaydedildi: {hedef}", flush=True)


def maliyet_raporu_yaz(dosya_adi, toplam_sayfa, sayfa_kullanim, sayfa_duzeltmeler):
    """API usage'dan tahmini maliyet. Fiyatlar ortam degiskenlerinden okunur."""
    from decimal import Decimal

    def fiyat(anahtar):
        deger = os.getenv(anahtar)
        if deger is None or not deger.strip():
            return None
        return Decimal(deger)

    giris_fiyat = fiyat("OPENAI_INPUT_USD_PER_MILLION")
    cached_fiyat = fiyat("OPENAI_CACHED_INPUT_USD_PER_MILLION")
    cikis_fiyat = fiyat("OPENAI_OUTPUT_USD_PER_MILLION")
    fiyat_modeli = os.getenv("OPENAI_PRICING_MODEL", "").strip()
    fiyatlar_hazir = all(x is not None for x in (giris_fiyat, cached_fiyat, cikis_fiyat)) and bool(fiyat_modeli)

    def hesapla(giris, cikis, cached):
        if not fiyatlar_hazir:
            return None
        normal = max(0, giris - cached)
        tutar = (Decimal(normal) * giris_fiyat + Decimal(cached) * cached_fiyat + Decimal(cikis) * cikis_fiyat) / Decimal(1000000)
        return float(tutar)

    sayfalar = []
    toplam_giris = toplam_cikis = toplam_cached = 0
    toplam_ilk = toplam_duzeltme = Decimal(0)
    maliyet_hesaplanabilir = fiyatlar_hazir
    modeller = set()
    for no in range(1, toplam_sayfa + 1):
        kullanim = sayfa_kullanim.get(str(no)) or {}
        duzeltmeler = sayfa_duzeltmeler.get(str(no)) or []
        model = kullanim.get("model")
        if model:
            modeller.add(model)
        giris = int(kullanim.get("giris_token") or 0)
        cikis = int(kullanim.get("cikis_token") or 0)
        cached = int(kullanim.get("cached_giris_token") or 0)
        duz_giris = sum(int(d.get("ek_giris_token") or 0) for d in duzeltmeler)
        duz_cikis = sum(int(d.get("ek_cikis_token") or 0) for d in duzeltmeler)
        duz_cached = sum(int(d.get("ek_cached_giris_token") or 0) for d in duzeltmeler)
        ilk = kullanim.get("ilk_ceviri")
        if ilk:
            ilk_giris = int(ilk.get("giris_token") or 0)
            ilk_cikis = int(ilk.get("cikis_token") or 0)
            ilk_cached = int(ilk.get("cached_giris_token") or 0)
        else:
            ilk_giris = giris - duz_giris
            ilk_cikis = cikis - duz_cikis
            ilk_cached = cached - duz_cached
        tutar_ilk = hesapla(ilk_giris, ilk_cikis, ilk_cached)
        tutar_duz = hesapla(duz_giris, duz_cikis, duz_cached)
        if model != fiyat_modeli or not kullanim or min(ilk_giris, ilk_cikis, ilk_cached) < 0 or cached > giris or ilk_cached > ilk_giris or duz_cached > duz_giris:
            tutar_ilk = tutar_duz = None
            maliyet_hesaplanabilir = False
        if tutar_ilk is not None:
            toplam_ilk += Decimal(str(tutar_ilk))
            toplam_duzeltme += Decimal(str(tutar_duz))
        toplam_giris += giris
        toplam_cikis += cikis
        toplam_cached += cached
        sayfalar.append({
            "sayfa": no, "model": model,
            "giris_token": giris, "cached_giris_token": cached,
            "cikis_token": cikis,
            "ilk_ceviri_maliyeti_usd": tutar_ilk,
            "duzeltme_maliyeti_usd": tutar_duz,
            "toplam_maliyet_usd": round(tutar_ilk + tutar_duz, 10) if tutar_ilk is not None else None,
            "duzeltme_deneme_sayisi": len(duzeltmeler),
        })

    rapor = {
        "kaynak_pdf": dosya_adi,
        "olusturulma_zamani_utc": datetime.now(timezone.utc).isoformat(),
        "para_birimi": "USD",
        "hesaplama_turu": "API token kullanimina dayali tahmin; fatura degildir",
        "fiyatlandirma_modeli": fiyat_modeli or None,
        "bir_milyon_token_fiyatlari_usd": {
            "giris": float(giris_fiyat) if giris_fiyat is not None else None,
            "cached_giris": float(cached_fiyat) if cached_fiyat is not None else None,
            "cikis": float(cikis_fiyat) if cikis_fiyat is not None else None,
        },
        "durum": "hesaplandi" if maliyet_hesaplanabilir else "fiyat_veya_kullanim_dogrulanmali",
        "toplam_giris_token": toplam_giris,
        "toplam_cached_giris_token": toplam_cached,
        "toplam_cikis_token": toplam_cikis,
        "ilk_ceviri_maliyeti_usd": round(float(toplam_ilk), 10) if maliyet_hesaplanabilir else None,
        "duzeltme_maliyeti_usd": round(float(toplam_duzeltme), 10) if maliyet_hesaplanabilir else None,
        "toplam_maliyet_usd": round(float(toplam_ilk + toplam_duzeltme), 10) if maliyet_hesaplanabilir else None,
        "sayfa_basi_ortalama_usd": round(float((toplam_ilk + toplam_duzeltme) / Decimal(toplam_sayfa)), 10) if maliyet_hesaplanabilir and toplam_sayfa else None,
        "uyari": "Fiyatlar OPENAI_* ortam degiskenleriyle verilmeli; model eslesmeli. Tablo servisinin ayri API maliyetleri dahil olmayabilir. API hatalarinda tamamlanmayan cagri maliyetleri raporlanmaz.",
        "sayfalar": sayfalar,
    }
    hedef = OUTPUT / f"{Path(dosya_adi).stem}_maliyet_raporu.json"
    with hedef.open("w", encoding="utf-8") as dosya:
        json.dump(rapor, dosya, ensure_ascii=False, indent=2)
    print(f"Maliyet raporu kaydedildi: {hedef}", flush=True)


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
    sayfa_kullanim = {}
    sayfa_duzeltmeler = {}

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
                sayfa_kullanim[str(sayfa_no)] = sonuc.get("kullanim")
                sayfa_duzeltmeler[str(sayfa_no)] = sonuc.get("duzeltme_gecmisi", [])

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

    maliyet_raporu_yaz(dosya_adi, toplam_sayfa, sayfa_kullanim, sayfa_duzeltmeler)

    izlenebilirlik_raporu_yaz(
        dosya_adi,
        toplam_sayfa,
        tum_ceviriler,
        tum_tablolar,
        sayfa_kullanim,
        sayfa_duzeltmeler,
    )


if __name__ == "__main__":
    main()

