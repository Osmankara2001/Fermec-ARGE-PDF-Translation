from fastapi import FastAPI
from pydantic import BaseModel

from graph import ceviri_graph


app = FastAPI(
    title="Fermec Ceviri Servisi",
)


class CeviriIstegi(BaseModel):
    kaynak_metin: str


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ceviri-servisi",
    }


@app.post("/translate")
def translate(istek: CeviriIstegi):
    baslangic_state = {
        "kaynak_metin": istek.kaynak_metin,
        "ceviri": "",
        "durum": "basladi",
    }

    sonuc = ceviri_graph.invoke(
        baslangic_state
    )

    return sonuc