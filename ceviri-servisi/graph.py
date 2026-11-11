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
    response = client.responses.create(
        model="gpt-6-luna",
        instructions=(
            "You are a professional English-to-Turkish "
            "technical book translator. "
            "Translate each input block into Turkish. "
            "Preserve all numbers, units, formulas, codes, "
            "URLs and identifiers exactly. "
            "Do not merge, remove or reorder blocks. "
            "Return a JSON object containing a 'translations' "
            "array. Each item must contain the original 'id' "
            "and its Turkish 'ceviri'. "
            "Return only valid JSON."
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
        max_output_tokens=3000,
    )
    gecen_sure = round(time.perf_counter() - baslangic, 3)

    if not response.output_text.strip():
        raise ValueError("OpenAI bos ceviri sonucu dondurdu.")

    sonuc = json.loads(response.output_text)
    ceviriler = sonuc["translations"]

    kaynak_idler = [blok["id"] for blok in bloklar]
    ceviri_idler = [blok["id"] for blok in ceviriler]

    if kaynak_idler != ceviri_idler:
        raise ValueError(
            "Toplu ceviride blok ID'leri veya sirasi eslesmiyor."
        )

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
        f"OpenAI kullanim: "
        f"{response.usage.input_tokens} giris, "
        f"{response.usage.output_tokens} cikis token"
    )

    kullanim = {
        "model": response.model,
        "giris_token": response.usage.input_tokens,
        "cikis_token": response.usage.output_tokens,
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

    kaynak_idler = [
        blok["id"]
        for blok in state["bloklar"]
    ]

    ceviri_idler = [
        blok["id"]
        for blok in state["ceviri_bloklari"]
    ]

    if kaynak_idler != ceviri_idler:
        raise ValueError(
            "Kaynak ve ceviri blok ID'leri eslesmiyor."
        )

    for blok in state["ceviri_bloklari"]:
        kaynak_sayilar = re.findall(
            r"\d+(?:[.,]\d+)?",
            blok["kaynak_metin"],
        )

        ceviri_sayilar = re.findall(
            r"\d+(?:[.,]\d+)?",
            blok["ceviri"],
        )

        if Counter(kaynak_sayilar) != Counter(ceviri_sayilar):
            raise ValueError(
                f"Sayi kontrolu basarisiz: {blok['id']}. "
                f"Kaynak: {kaynak_sayilar}, "
                f"Ceviri: {ceviri_sayilar}"
            )

    return {
        "durum": "kurallar_kontrol_edildi",
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