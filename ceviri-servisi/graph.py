from typing import TypedDict

from langgraph.graph import END, StateGraph


class CeviriState(TypedDict):
    kaynak_metin: str
    ceviri: str
    durum: str


def budget_gate(state: CeviriState):
    return {
        "durum": "butce_onaylandi",
    }


def translate(state: CeviriState):
    # Simdilik gercek AI modeli kullanmiyoruz.
    # Graph akisinin calistigini test ediyoruz.
    return {
        "ceviri": f"[TEST CEVIRI] {state['kaynak_metin']}",
        "durum": "cevrildi",
    }


def rule_validation(state: CeviriState):
    return {
        "durum": "kurallar_kontrol_edildi",
    }


def model_review(state: CeviriState):
    return {
        "durum": "model_kontrolunden_gecti",
    }


def approve(state: CeviriState):
    return {
        "durum": "onaylandi",
    }


graph_builder = StateGraph(CeviriState)

graph_builder.add_node(
    "budget_gate",
    budget_gate,
)

graph_builder.add_node(
    "translate",
    translate,
)

graph_builder.add_node(
    "rule_validation",
    rule_validation,
)

graph_builder.add_node(
    "model_review",
    model_review,
)

graph_builder.add_node(
    "approve",
    approve,
)

graph_builder.set_entry_point(
    "budget_gate"
)

graph_builder.add_edge(
    "budget_gate",
    "translate",
)

graph_builder.add_edge(
    "translate",
    "rule_validation",
)

graph_builder.add_edge(
    "rule_validation",
    "model_review",
)

graph_builder.add_edge(
    "model_review",
    "approve",
)

graph_builder.add_edge(
    "approve",
    END,
)

ceviri_graph = graph_builder.compile()