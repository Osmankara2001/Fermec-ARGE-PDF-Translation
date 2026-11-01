import re
from typing import TypedDict

from langgraph.graph import END, StateGraph



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


def budget_gate(state: CeviriState):
    return {
        "durum": "butce_onaylandi",
    }


def translate(state: CeviriState):
    ceviri_bloklari = []

    for blok in state["bloklar"]:
        ceviri_bloklari.append({
            "id": blok["id"],
            "kaynak_metin": blok["metin"],
            "ceviri": (
                f"[TEST CEVIRI] {blok['metin']}"
            ),
        })

    return {
        "ceviri_bloklari": ceviri_bloklari,
        "durum": "cevrildi",
    }


def rule_validation(state: CeviriState):
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

        if kaynak_sayilar != ceviri_sayilar:
            raise ValueError(
                f"Sayi kontrolu basarisiz: {blok['id']}"
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