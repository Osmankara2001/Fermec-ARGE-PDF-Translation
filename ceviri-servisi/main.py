from fastapi import FastAPI
from pydantic import BaseModel

from graph import ceviri_graph


app = FastAPI(
    title="Fermec Ceviri Servisi",
)


class MetinBlogu(BaseModel):
    id: str
    metin: str


class CeviriIstegi(BaseModel):
    bloklar: list[MetinBlogu]


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "ceviri-servisi",
    }


@app.post("/translate")
def translate(istek: CeviriIstegi):
    baslangic_state = {
        "bloklar": [
            blok.model_dump()
            for blok in istek.bloklar
        ],
        "ceviri_bloklari": [],
        "hatalar": [],
        "duzeltme_turu": 0,
        "insan_kontrolu_gerekli": False,
        "kullanim": {},
        "duzeltme_gecmisi": [],
        "durum": "basladi",
    }

    sonuc = ceviri_graph.invoke(
        baslangic_state
        
    )

    return sonuc