
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import sqlite3
from pathlib import Path
from pdf_service import pdf_analiz_et
from typing import Literal
from pdf_service import (
    pdf_analiz_et,
    pdf_parca_metni_al,
    pdf_parca_kalite_kontrol,
    pdf_sayfa_ocr,
    pdf_parca_metin_hazirla,
    pdf_metin_bloklarini_al,
    pdf_sayfa_yapisini_cikar,
)

app = FastAPI(title="Fermec ARGE API")

# Veritabani dosyasi
DB_PATH = Path("/data/fermec.db")

# Pilot butcesi: 5 USD
BUDGET_USD = 5.00


def veritabani_hazirla():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_harcama (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                islem TEXT NOT NULL,
                tahmini_maliyet_usd REAL NOT NULL,
                durum TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pdf_parcalari (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dosya_adi TEXT NOT NULL,
                parca_no INTEGER NOT NULL,
                baslangic_sayfasi INTEGER NOT NULL,
                bitis_sayfasi INTEGER NOT NULL,
                durum TEXT NOT NULL DEFAULT 'bekliyor',
                hata TEXT,
                olusturma_zamani TEXT DEFAULT CURRENT_TIMESTAMP,
                guncelleme_zamani TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(dosya_adi, parca_no)
            )
        """)


@app.on_event("startup")
def baslangicta_hazirla():
    veritabani_hazirla()


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "fermec-api",
    }


class HarcamaIstegi(BaseModel):
    islem: str = Field(min_length=1, max_length=100)
    tahmini_maliyet_usd: float = Field(gt=0, le=5)

  
class ParcaDurumIstegi(BaseModel):
    dosya_adi: str = Field(min_length=1, max_length=255)
    parca_no: int = Field(gt=0)
    durum: Literal["bekliyor", "isleniyor", "tamamlandi", "hata"]
    hata: str | None = None
  


@app.get("/budget")
def butce_durumu():
    with sqlite3.connect(DB_PATH) as conn:
        sonuc = conn.execute(
            "SELECT COALESCE(SUM(tahmini_maliyet_usd), 0) "
            "FROM api_harcama WHERE durum = 'onaylandi'"
        ).fetchone()

    harcanan = round(sonuc[0], 4)

    return {
        "butce_usd": BUDGET_USD,
        "harcanan_usd": harcanan,
        "kalan_usd": round(max(0, BUDGET_USD - harcanan), 4),
    }


@app.post("/budget/check")
def butce_kontrol(istek: HarcamaIstegi):
    with sqlite3.connect(DB_PATH) as conn:
        sonuc = conn.execute(
            "SELECT COALESCE(SUM(tahmini_maliyet_usd), 0) "
            "FROM api_harcama WHERE durum = 'onaylandi'"
        ).fetchone()

        harcanan = sonuc[0]

        if harcanan + istek.tahmini_maliyet_usd > BUDGET_USD:
            raise HTTPException(
                status_code=402,
                detail="Butce limiti asiliyor. Islem onaylanmadi.",
            )

        conn.execute(
            "INSERT INTO api_harcama "
            "(islem, tahmini_maliyet_usd, durum) VALUES (?, ?, ?)",
            (istek.islem, istek.tahmini_maliyet_usd, "onaylandi"),
        )

    return {
        "durum": "onaylandi",
        "islem": istek.islem,
        "eklenen_tahmini_maliyet_usd": istek.tahmini_maliyet_usd,
    }


INPUT_DIR = Path("/input")


@app.get("/pdf/analyze")
def pdf_analiz():
    pdf_yolu = INPUT_DIR / "fermec_ornek.pdf"

    try:
        return pdf_analiz_et(pdf_yolu)
    except FileNotFoundError as hata:
        raise HTTPException(status_code=404, detail=str(hata))
    except Exception as hata:
        raise HTTPException(
            status_code=500,
            detail=f"PDF analiz edilemedi: {hata}",
        )


@app.post("/pdf/register")
def pdf_kaydet():
    pdf_yolu = INPUT_DIR / "fermec_ornek.pdf"

    try:
        analiz = pdf_analiz_et(pdf_yolu)

        with sqlite3.connect(DB_PATH) as conn:
            for parca in analiz["parcalar"]:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO pdf_parcalari
                    (dosya_adi, parca_no, baslangic_sayfasi, bitis_sayfasi)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        analiz["dosya"],
                        parca["parca_no"],
                        parca["baslangic_sayfasi"],
                        parca["bitis_sayfasi"],
                    ),
                )

            conn.commit()

        return {
            "durum": "kaydedildi",
            "dosya": analiz["dosya"],
            "toplam_parca": analiz["toplam_parca"],
            "parcalar": analiz["parcalar"],
        }

    except FileNotFoundError as hata:
        raise HTTPException(status_code=404, detail=str(hata))


@app.get("/pdf/jobs")
def pdf_islerini_listele():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        kayitlar = conn.execute(
            """
            SELECT dosya_adi, parca_no, baslangic_sayfasi,
                   bitis_sayfasi, durum, hata
            FROM pdf_parcalari
            ORDER BY dosya_adi, parca_no
            """
        ).fetchall()

    return {
        "toplam_kayit": len(kayitlar),
        "parcalar": [dict(kayit) for kayit in kayitlar],
    }


@app.post("/pdf/status")
def pdf_durum_guncelle(istek: ParcaDurumIstegi):
    with sqlite3.connect(DB_PATH) as conn:
        sonuc = conn.execute(
            """
            UPDATE pdf_parcalari
            SET durum = ?,
                hata = ?,
                guncelleme_zamani = CURRENT_TIMESTAMP
            WHERE dosya_adi = ? AND parca_no = ?
            """,
            (
                istek.durum,
                istek.hata,
                istek.dosya_adi,
                istek.parca_no,
            ),
        )

        if sonuc.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail="PDF parcasi bulunamadi.",
            )

    return {
        "durum": "guncellendi",
        "dosya": istek.dosya_adi,
        "parca_no": istek.parca_no,
        "yeni_durum": istek.durum,
    }


@app.get("/pdf/next")
def siradaki_pdf_parcasi():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        # Ayni anda birden fazla islem baslamasini onle.
        conn.execute("BEGIN IMMEDIATE")

        parca = conn.execute(
            """
            SELECT id, dosya_adi, parca_no,
                   baslangic_sayfasi, bitis_sayfasi
            FROM pdf_parcalari
            WHERE durum = 'bekliyor'
            ORDER BY dosya_adi, parca_no
            LIMIT 1
            """
        ).fetchone()

        if parca is None:
            return {
                "durum": "bekleyen_parca_yok",
                "parca": None,
            }

        conn.execute(
            """
            UPDATE pdf_parcalari
            SET durum = 'isleniyor',
                hata = NULL,
                guncelleme_zamani = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (parca["id"],),
        )

        return {
            "durum": "isleniyor",
            "parca": {
                "dosya_adi": parca["dosya_adi"],
                "parca_no": parca["parca_no"],
                "baslangic_sayfasi": parca["baslangic_sayfasi"],
                "bitis_sayfasi": parca["bitis_sayfasi"],
            },
        }


@app.get("/pdf/chunk/{parca_no}")
def pdf_parca_getir(parca_no: int):
    if parca_no < 1:
        raise HTTPException(
            status_code=400,
            detail="Parca numarasi pozitif olmalidir.",
        )

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        parca = conn.execute(
            """
            SELECT dosya_adi, baslangic_sayfasi, bitis_sayfasi
            FROM pdf_parcalari
            WHERE dosya_adi = ? AND parca_no = ?
            """,
            ("fermec_ornek.pdf", parca_no),
        ).fetchone()

    if parca is None:
        raise HTTPException(
            status_code=404,
            detail="PDF parcasi bulunamadi.",
        )

    pdf_yolu = INPUT_DIR / parca["dosya_adi"]

    try:
        return pdf_parca_metni_al(
            pdf_yolu,
            parca["baslangic_sayfasi"],
            parca["bitis_sayfasi"],
        )
    except FileNotFoundError as hata:
        raise HTTPException(status_code=404, detail=str(hata))
    except ValueError as hata:
        raise HTTPException(status_code=400, detail=str(hata))


@app.get("/pdf/chunk/{parca_no}/validate")
def pdf_parca_kalite_kontrol_et(parca_no: int):
    if parca_no < 1:
        raise HTTPException(
            status_code=400,
            detail="Parca numarasi pozitif olmalidir.",
        )

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        parca = conn.execute(
            """
            SELECT dosya_adi, baslangic_sayfasi, bitis_sayfasi
            FROM pdf_parcalari
            WHERE dosya_adi = ? AND parca_no = ?
            """,
            ("fermec_ornek.pdf", parca_no),
        ).fetchone()

    if parca is None:
        raise HTTPException(
            status_code=404,
            detail="PDF parcasi bulunamadi.",
        )

    try:
        return pdf_parca_kalite_kontrol(
            INPUT_DIR / parca["dosya_adi"],
            parca["baslangic_sayfasi"],
            parca["bitis_sayfasi"],
        )
    except FileNotFoundError as hata:
        raise HTTPException(status_code=404, detail=str(hata))
    except ValueError as hata:
        raise HTTPException(status_code=400, detail=str(hata))

@app.get("/pdf/ocr/{sayfa_no}")
def pdf_ocr_yap(sayfa_no: int):
    pdf_yolu = INPUT_DIR / "fermec_ornek.pdf"

    try:
        return pdf_sayfa_ocr(
            pdf_yolu=pdf_yolu,
            sayfa_no=sayfa_no,
            dil="eng",
        )
    except FileNotFoundError as hata:
        raise HTTPException(status_code=404, detail=str(hata))
    except ValueError as hata:
        raise HTTPException(status_code=400, detail=str(hata))
    except RuntimeError as hata:
        raise HTTPException(status_code=500, detail=str(hata))


@app.get("/pdf/chunk/{parca_no}/prepare")
def pdf_parca_hazirla(parca_no: int):
    if parca_no < 1:
        raise HTTPException(
            status_code=400,
            detail="Parca numarasi pozitif olmalidir.",
        )

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        parca = conn.execute(
            """
            SELECT dosya_adi, baslangic_sayfasi, bitis_sayfasi
            FROM pdf_parcalari
            WHERE dosya_adi = ? AND parca_no = ?
            """,
            ("fermec_ornek.pdf", parca_no),
        ).fetchone()

    if parca is None:
        raise HTTPException(
            status_code=404,
            detail="PDF parcasi bulunamadi.",
        )

    try:
        return pdf_parca_metin_hazirla(
            INPUT_DIR / parca["dosya_adi"],
            parca["baslangic_sayfasi"],
            parca["bitis_sayfasi"],
        )
    except FileNotFoundError as hata:
        raise HTTPException(status_code=404, detail=str(hata))
    except ValueError as hata:
        raise HTTPException(status_code=400, detail=str(hata))
    except RuntimeError as hata:
        raise HTTPException(status_code=500, detail=str(hata))

@app.get("/pdf/page/{sayfa_no}/blocks")
def pdf_sayfa_bloklari(sayfa_no: int):
    pdf_yolu = INPUT_DIR / "fermec_ornek.pdf"

    try:
        return pdf_metin_bloklarini_al(
            pdf_yolu=pdf_yolu,
            sayfa_no=sayfa_no,
        )
    except FileNotFoundError as hata:
        raise HTTPException(status_code=404, detail=str(hata))
    except ValueError as hata:
        raise HTTPException(status_code=400, detail=str(hata))

@app.get("/pdf/page/{sayfa_no}/structure")
def pdf_sayfa_yapisi(sayfa_no: int):
    pdf_yolu = INPUT_DIR / "fermec_ornek.pdf"

    try:
        return pdf_sayfa_yapisini_cikar(
            pdf_yolu=pdf_yolu,
            sayfa_no=sayfa_no,
        )

    except FileNotFoundError as hata:
        raise HTTPException(
            status_code=404,
            detail=str(hata),
        )

    except ValueError as hata:
        raise HTTPException(
            status_code=400,
            detail=str(hata),
        )