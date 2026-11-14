import re
from typing import TypedDict

from openai import OpenAI
from langgraph.graph import END, StateGraph
import json
import time
from olcum import olcum_kaydet
from formul_koruyucu import (
    formul_satirlarini_koru,
    formulleri_geri_yerlestir
)


client = OpenAI()



class MetinBlogu(TypedDict):
    id: str
    metin: str


class CeviriBlogu(TypedDict):
    id: str
    kaynak_metin: str
    ceviri: str


class CeviriState(TypedDict):
    bloklar: list[MetinBlogu]
    ceviri_bloklari: list[CeviriBlogu]
    hatalar: list[str]
    duzeltme_turu: int
    insan_kontrolu_gerekli: bool
    durum: str
    kullanim: dict
    duzeltme_gecmisi: list[dict]


def budget_gate(state: CeviriState):
    return {
        "durum": "butce_onaylandi",
    }


def translate(state: CeviriState):
    bloklar = state["bloklar"]

    if not bloklar:
        return {
            "ceviri_bloklari": [],
            "durum": "cevrildi",
        }

    gonderilecek = []
    korunan_formuller = {}

    for blok in bloklar:
        korumali_metin, formuller = formul_satirlarini_koru(
            blok["metin"]
        )

        gonderilecek.append({
            "id": blok["id"],
            "metin": korumali_metin
        })

        korunan_formuller[blok["id"]] = formuller

    baslangic = time.perf_counter()

    toplam_giris_token = 0
    toplam_cikis_token = 0
    toplam_cached_token = 0

    for deneme in range(1, 4):
        response = client.responses.create(
            model="gpt-6-luna",
            instructions=(
                "You are a professional English-to-Turkish "
                "technical book translator. "
                "Translate every input block into Turkish. "
                "Preserve numbers, units, formulas, URLs and codes. "
                "Do not merge or omit any blocks. "
                "Preserve the exact original block IDs. "
                "Return translations in the same order as input."
            ),
            input=json.dumps(gonderilecek, ensure_ascii=False),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "translation_batch",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "translations": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "ceviri": {"type": "string"},
                                    },
                                    "required": ["id", "ceviri"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["translations"],
                        "additionalProperties": False,
                    },
                }
            },
            max_output_tokens=6000,
        )

        if response.usage:
            toplam_giris_token += response.usage.input_tokens
            toplam_cikis_token += response.usage.output_tokens
            detay = getattr(response.usage, "input_tokens_details", None)
            toplam_cached_token += getattr(detay, "cached_tokens", 0) or 0

        try:
            if not response.output_text.strip():
                raise ValueError("OpenAI bos ceviri sonucu dondurdu.")

            sonuc = json.loads(response.output_text)
            ceviriler = sonuc["translations"]

            kaynak_idler = [blok["id"] for blok in bloklar]
            ceviri_idler = [blok["id"] for blok in ceviriler]

            if kaynak_idler != ceviri_idler:
                raise ValueError(
                    "Toplu ceviride blok ID'leri veya sirasi eslesmiyor. "
                    f"Beklenen: {kaynak_idler}, Gelen: {ceviri_idler}"
                )

            if any(
                not isinstance(blok.get("ceviri"), str)
                or not blok["ceviri"].strip()
                for blok in ceviriler
            ):
                raise ValueError("Bos veya gecersiz ceviri blogu.")

            print(
                f"Ceviri dogrulandi. Deneme: {deneme}",
                flush=True
            )
            break

        except (ValueError, KeyError, TypeError) as hata:
            print(
                f"Ceviri denemesi {deneme}/3 basarisiz: {hata}",
                flush=True
            )

            if deneme == 3:
                raise RuntimeError(
                    "Ceviri 3 denemede dogrulanamadi."
                ) from hata

            time.sleep(2)

    gecen_sure = round(time.perf_counter() - baslangic, 3)


    ceviri_bloklari = []

    for kaynak, sonuc_blok in zip(bloklar, ceviriler):
        if not sonuc_blok["ceviri"].strip():
            raise ValueError(
                f"Bos ceviri sonucu: {kaynak['id']}"
            )

        duzeltilmis_ceviri = formulleri_geri_yerlestir(
            sonuc_blok["ceviri"],
            korunan_formuller[kaynak["id"]]
        )

        ceviri_bloklari.append({
            "id": kaynak["id"],
            "kaynak_metin": kaynak["metin"],
            "ceviri": duzeltilmis_ceviri,
        })

    print(
        f"OpenAI toplam kullanim: "
        f"{toplam_giris_token} giris, "
        f"{toplam_cikis_token} cikis token",
        flush=True
    )

    kullanim = {
        "model": response.model,
        "giris_token": toplam_giris_token,
        "cikis_token": toplam_cikis_token,
        "cached_giris_token": toplam_cached_token,
        "ilk_ceviri": {
            "giris_token": toplam_giris_token,
            "cikis_token": toplam_cikis_token,
            "cached_giris_token": toplam_cached_token,
        },
        "sure_saniye": gecen_sure,
    }

    olcum_kaydet(kullanim)

    return {
        "ceviri_bloklari": ceviri_bloklari,
        "durum": "cevrildi",
        "kullanim": kullanim,
    }



def rule_validation(state: CeviriState):
    from collections import Counter

    kaynak_idler = [blok["id"] for blok in state["bloklar"]]
    ceviri_bloklari = [dict(blok) for blok in state["ceviri_bloklari"]]
    ceviri_idler = [blok["id"] for blok in ceviri_bloklari]

    if kaynak_idler != ceviri_idler:
        raise ValueError("Kaynak ve ceviri blok ID'leri eslesmiyor.")

    def sayilari_al(metin):
        return Counter(re.findall(r"\d+(?:[.,]\d+)?", metin))

    # Yalnizca sayi kontrolu basarisiz olan bloklari tekrar cevir.
    # Basarili bloklara dokunma; eksik veya fazla sayiyi kabul etme.
    kullanim = dict(state.get("kullanim") or {})
    duzeltme_gecmisi = list(state.get("duzeltme_gecmisi") or [])
    for blok in ceviri_bloklari:
        kaynak_sayilar = sayilari_al(blok["kaynak_metin"])
        ceviri_sayilar = sayilari_al(blok["ceviri"])
        if kaynak_sayilar == ceviri_sayilar:
            continue

        print(
            f"Sayi uyusmazligi: {blok['id']}. "
            f"Kaynak: {dict(kaynak_sayilar)}, "
            f"Ceviri: {dict(ceviri_sayilar)}",
            flush=True,
        )
        for deneme in range(1, 3):
            kayit = {
                "blok_id": blok["id"],
                "hata_turu": "sayi_uyusmazligi",
                "deneme": deneme,
                "kaynak_sayilar": dict(kaynak_sayilar),
                "onceki_ceviri_sayilar": dict(sayilari_al(blok["ceviri"])),
                "sonuc": "basarisiz",
                "ek_giris_token": 0,
                "ek_cikis_token": 0,
                "ek_cached_giris_token": 0,
            }
            baslangic = time.perf_counter()
            response = client.responses.create(
                model="gpt-6-luna",
                instructions=(
                    "Translate the source text into natural Turkish. "
                    "The previous Turkish translation failed numerical validation. "
                    "Preserve every number exactly, including its spelling, "
                    "decimal separators, and frequency. Do not introduce "
                    "any additional numbers. Preserve formulas, units, "
                    "URLs, and codes. Return only the requested JSON."
                ),
                input=json.dumps(
                    {
                        "source": blok["kaynak_metin"],
                        "previous_translation": blok["ceviri"],
                        "required_numbers": list(kaynak_sayilar.elements()),
                    },
                    ensure_ascii=False,
                ),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "number_corrected_translation",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {"ceviri": {"type": "string"}},
                            "required": ["ceviri"],
                            "additionalProperties": False,
                        },
                    }
                },
                max_output_tokens=3000,
            )
            gecen_sure = round(time.perf_counter() - baslangic, 3)
            kayit["sure_saniye"] = gecen_sure
            if response.usage:
                ek_giris = response.usage.input_tokens
                ek_cikis = response.usage.output_tokens
                detay = getattr(response.usage, "input_tokens_details", None)
                ek_cached = getattr(detay, "cached_tokens", 0) or 0
                kayit["ek_cached_giris_token"] = ek_cached
                kullanim["cached_giris_token"] = kullanim.get("cached_giris_token", 0) + ek_cached
                kayit["ek_giris_token"] = ek_giris
                kayit["ek_cikis_token"] = ek_cikis
                kullanim["giris_token"] = kullanim.get("giris_token", 0) + ek_giris
                kullanim["cikis_token"] = kullanim.get("cikis_token", 0) + ek_cikis
                kullanim["sure_saniye"] = round(
                    kullanim.get("sure_saniye", 0) + gecen_sure, 3
                )
                olcum_kaydet({
                    "model": response.model,
                    "giris_token": ek_giris,
                    "cikis_token": ek_cikis,
                    "sure_saniye": gecen_sure,
                })

            try:
                duzeltilmis = json.loads(response.output_text)["ceviri"]
                if not isinstance(duzeltilmis, str) or not duzeltilmis.strip():
                    raise ValueError("Bos duzeltme")
                if sayilari_al(duzeltilmis) != kaynak_sayilar:
                    raise ValueError("Sayilar hala eslesmiyor")
            except (ValueError, KeyError, TypeError) as hata:
                kayit["hata"] = str(hata)
                duzeltme_gecmisi.append(kayit)
                print(
                    f"Blok {blok['id']}, sayi duzeltme "
                    f"{deneme}/2 basarisiz: {hata}",
                    flush=True,
                )
                continue

            kayit["sonuc"] = "basarili"
            duzeltme_gecmisi.append(kayit)
            blok["ceviri"] = duzeltilmis
            print(f"Blok {blok['id']} sayi kontrolu duzeltildi.", flush=True)
            break
        else:
            raise ValueError(
                f"Sayi kontrolu iki duzeltmede de basarisiz: {blok['id']}. "
                f"Kaynak: {dict(kaynak_sayilar)}"
            )

    return {
        "ceviri_bloklari": ceviri_bloklari,
        "kullanim": kullanim,
        "durum": "kurallar_kontrol_edildi",
        "duzeltme_gecmisi": duzeltme_gecmisi,
    }


def model_review(state: CeviriState):
    return {
        "hatalar": [],
        "durum": "model_kontrolunden_gecti",
    }

def fix(state: CeviriState):
    return {
        "duzeltme_turu": state["duzeltme_turu"] + 1,
        "hatalar": [],
        "durum": "duzeltildi",
    }


def review_karari(state: CeviriState):
    if not state["hatalar"]:
        return "approve"

    if state["duzeltme_turu"] < 2:
        return "fix"

    return "human_review"


def human_review(state: CeviriState):
    return {
        "insan_kontrolu_gerekli": True,
        "durum": "insan_kontrolu_gerekli",
    }



def approve(state: CeviriState):
    return {
        "durum": "onaylandi",
    }


graph_builder = StateGraph(CeviriState)

graph_builder.add_node("budget_gate", budget_gate)
graph_builder.add_node("translate", translate)
graph_builder.add_node("rule_validation", rule_validation)
graph_builder.add_node("model_review", model_review)
graph_builder.add_node("fix", fix)
graph_builder.add_node("human_review", human_review)
graph_builder.add_node("approve", approve)

graph_builder.set_entry_point("budget_gate")

graph_builder.add_edge("budget_gate", "translate")
graph_builder.add_edge("translate", "rule_validation")
graph_builder.add_edge("rule_validation", "model_review")

graph_builder.add_conditional_edges(
    "model_review",
    review_karari,
    {
        "approve": "approve",
        "fix": "fix",
        "human_review": "human_review",
    },
)

graph_builder.add_edge("fix", "rule_validation")
graph_builder.add_edge("approve", END)
graph_builder.add_edge("human_review", END)

ceviri_graph = graph_builder.compile()