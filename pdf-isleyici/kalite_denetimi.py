
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI


QA_MODEL = os.getenv("OPENAI_QA_MODEL", "gpt-5.4-mini")
QA_BATCH_CHARS = max(1000, int(os.getenv("OPENAI_QA_BATCH_CHARS", "12000")))
QA_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_QA_MAX_OUTPUT_TOKENS", "5000"))


def json_oku(yol):
    with Path(yol).open("r", encoding="utf-8") as dosya:
        veri = json.load(dosya)
    if not isinstance(veri, dict):
        raise ValueError(f"JSON nesnesi bekleniyor: {yol}")
    return veri


def denetim_kayitlari_hazirla(ceviriler, tablolar):
    kayitlar = []
    gorulen_idler = set()

    sayfalar = sorted(
        set(ceviriler) | set(tablolar),
        key=lambda x: int(x)
    )

    for sayfa in sayfalar:
        for blok in ceviriler.get(sayfa, []):
            kayitlar.append({
                "id": blok["id"],
                "sayfa": int(sayfa),
                "tur": "metin",
                "kaynak": str(blok.get("kaynak_metin") or ""),
                "ceviri": str(blok.get("ceviri") or ""),
            })

        for tablo in tablolar.get(sayfa, []):
            for satir in tablo.get("satirlar", []):
                for hucre in satir.get("hucreler", []):
                    kayitlar.append({
                        "id": hucre["id"],
                        "sayfa": int(sayfa),
                        "tur": "tablo_hucresi",
                        "kaynak": str(hucre.get("metin") or ""),
                        "ceviri": str(hucre.get("ceviri") or ""),
                    })

    for kayit in kayitlar:
        if kayit["id"] in gorulen_idler:
            raise ValueError(f"Tekrarlanan denetim ID'si: {kayit['id']}")
        gorulen_idler.add(kayit["id"])

    return kayitlar, [int(s) for s in sayfalar]


def gruplara_ayir(kayitlar):
    grup = []
    boyut = 0

    for kayit in kayitlar:
        uzunluk = len(json.dumps(kayit, ensure_ascii=False))

        if grup and boyut + uzunluk > QA_BATCH_CHARS:
            yield grup
            grup = []
            boyut = 0

        grup.append(kayit)
        boyut += uzunluk

    if grup:
        yield grup


def qa_semasi():
    hata = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "kategori": {"type": "string"},
            "onem": {
                "type": "string",
                "enum": ["kritik", "yuksek", "orta", "dusuk"]
            },
            "aciklama": {"type": "string"},
            "onerilen_ceviri": {"type": "string"},
        },
        "required": [
            "id", "kategori", "onem",
            "aciklama", "onerilen_ceviri"
        ],
        "additionalProperties": False,
    }

    return {
        "type": "object",
        "properties": {
            "sonuclar": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "puan": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100
                        },
                        "hatalar": {
                            "type": "array",
                            "items": hata
                        },
                    },
                    "required": ["id", "puan", "hatalar"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["sonuclar"],
        "additionalProperties": False,
    }


def grup_denetle(client, grup):
    son_hata = None
    kullanimlar = []

    for deneme in range(1, 4):
        try:
            response = client.responses.create(
                model=QA_MODEL,
                instructions=(
                    "You are an independent professional English-to-Turkish "
                    "technical translation quality auditor. "
                    "Compare each English source with its Turkish translation. "
                    "Evaluate semantic accuracy, completeness, technical "
                    "terminology, numbers, units, formulas, Turkish fluency "
                    "and consistency. "
                    "Score each item from 0 to 100 as an estimated quality "
                    "assessment, not a statistically verified accuracy rate. "
                    "Identify actual translation problems, not stylistic "
                    "preferences. Do not invent problems. "
                    "If the English source appears corrupted by OCR or "
                    "extraction, categorize that issue as source_extraction "
                    "rather than automatically blaming the translation. "
                    "Use severity: kritik, yuksek, orta, dusuk. "
                    "Return exactly one result for every input ID, "
                    "preserving the same order. "
                    "Every reported error must reference its input ID. "
                    "For a correct translation, return an empty errors list. "
                    "Never rewrite or modify the original input data."
                ),
                input=json.dumps(grup, ensure_ascii=False),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "translation_quality_audit",
                        "strict": True,
                        "schema": qa_semasi(),
                    }
                },
                max_output_tokens=QA_MAX_OUTPUT_TOKENS,
            )

            usage = response.usage
            kullanimlar.append({
                "giris_token": getattr(usage, "input_tokens", 0) or 0,
                "cikis_token": getattr(usage, "output_tokens", 0) or 0,
                "cached_giris_token": (
                    getattr(
                        getattr(usage, "input_tokens_details", None),
                        "cached_tokens", 0
                    ) or 0
                ),
            })

            if not response.output_text.strip():
                raise ValueError("Denetci bos cevap dondurdu.")

            sonuc = json.loads(response.output_text)["sonuclar"]

            beklenen = [kayit["id"] for kayit in grup]
            gelen = [kayit["id"] for kayit in sonuc]

            if gelen != beklenen:
                raise ValueError(
                    f"Denetim ID uyusmazligi: {beklenen} != {gelen}"
                )

            for madde in sonuc:
                for hata in madde["hatalar"]:
                    if hata["id"] != madde["id"]:
                        raise ValueError("Hata ID'si kayit ID'siyle eslesmiyor.")

            return sonuc, kullanimlar

        except Exception as hata:
            son_hata = hata
            print(
                f"QA denemesi {deneme}/3 basarisiz: {hata}",
                flush=True
            )
            if deneme < 3:
                time.sleep(2 * deneme)

    raise RuntimeError(f"QA grubu denetlenemedi: {son_hata}")


def kalite_raporu_uret(ceviri_json, tablo_json, rapor_yolu):
    ceviriler = json_oku(ceviri_json)
    tablolar = json_oku(tablo_json)

    kayitlar, sayfalar = denetim_kayitlari_hazirla(
        ceviriler, tablolar
    )

    rapor_yolu = Path(rapor_yolu)
    rapor_yolu.parent.mkdir(parents=True, exist_ok=True)

    rapor = {
        "olusturulma_zamani": datetime.now(timezone.utc).isoformat(),
        "model": QA_MODEL,
        "durum": "tamamlandi",
        "toplam_sayfa": len(sayfalar),
        "toplam_kayit": len(kayitlar),
        "denetlenen_kayit": 0,
        "belge_kalite_puani": None,
        "sayfalar": [],
        "hatalar": [],
        "uyarilar": [],
        "api_kullanim": {
            "giris_token": 0,
            "cikis_token": 0,
            "cached_giris_token": 0,
        },
    }

    sonuc_haritasi = {}
    client = OpenAI() if kayitlar else None

    for grup_no, grup in enumerate(gruplara_ayir(kayitlar), 1):
        print(
            f"AI kalite denetimi: grup {grup_no}, "
            f"{len(grup)} kayit",
            flush=True
        )

        try:
            sonuclar, kullanimlar = grup_denetle(client, grup)
            for sonuc in sonuclar:
                sonuc_haritasi[sonuc["id"]] = sonuc
        except Exception as hata:
            rapor["uyarilar"].append({
                "grup": grup_no,
                "idler": [kayit["id"] for kayit in grup],
                "hata": str(hata),
            })
            kullanimlar = getattr(hata, "kullanimlar", [])

        for kullanim in kullanimlar:
            for alan in rapor["api_kullanim"]:
                rapor["api_kullanim"][alan] += kullanim[alan]

    sayfa_kayitlari = defaultdict(list)

    for kayit in kayitlar:
        sayfa_kayitlari[kayit["sayfa"]].append(kayit)

    for sayfa in sayfalar:
        maddeler = sayfa_kayitlari[sayfa]
        puanlar = []
        hata_sayisi = 0

        for kayit in maddeler:
            sonuc = sonuc_haritasi.get(kayit["id"])
            if sonuc is None:
                continue

            puanlar.append(sonuc["puan"])
            rapor["denetlenen_kayit"] += 1

            for hata in sonuc["hatalar"]:
                rapor["hatalar"].append({
                    "sayfa": sayfa,
                    "tur": kayit["tur"],
                    "kaynak_metin": kayit["kaynak"],
                    "mevcut_ceviri": kayit["ceviri"],
                    **hata,
                })
                hata_sayisi += 1

        rapor["sayfalar"].append({
            "sayfa": sayfa,
            "toplam_kayit": len(maddeler),
            "denetlenen_kayit": len(puanlar),
            "kalite_puani": (
                round(sum(puanlar) / len(puanlar), 2)
                if puanlar else None
            ),
            "hata_sayisi": hata_sayisi,
        })

    tum_puanlar = [
        sonuc["puan"] for sonuc in sonuc_haritasi.values()
    ]

    if tum_puanlar:
        rapor["belge_kalite_puani"] = round(
            sum(tum_puanlar) / len(tum_puanlar), 2
        )

    if rapor["denetlenen_kayit"] < rapor["toplam_kayit"]:
        rapor["durum"] = "kismi"

    rapor["hatalar"].sort(
        key=lambda hata: (
            {"kritik": 0, "yuksek": 1, "orta": 2, "dusuk": 3}.get(
                hata["onem"], 4
            ),
            hata["sayfa"],
        )
    )

    with rapor_yolu.open("w", encoding="utf-8") as dosya:
        json.dump(rapor, dosya, ensure_ascii=False, indent=2)

    print(f"Kalite raporu kaydedildi: {rapor_yolu}", flush=True)
    print(
        f"Denetlenen: {rapor['denetlenen_kayit']}/"
        f"{rapor['toplam_kayit']}, "
        f"belge puani: {rapor['belge_kalite_puani']}",
        flush=True
    )

    return rapor
