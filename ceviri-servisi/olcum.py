import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_YOLU = Path("/app/data/olcumler.db")


def olcum_kaydet(kullanim: dict):
    DB_YOLU.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_YOLU) as baglanti:
        baglanti.execute("""
            CREATE TABLE IF NOT EXISTS api_olcumleri (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tarih TEXT,
                model TEXT,
                giris_token INTEGER,
                cikis_token INTEGER,
                sure_saniye REAL
            )
        """)

        baglanti.execute("""
            INSERT INTO api_olcumleri
            (tarih, model, giris_token, cikis_token, sure_saniye)
            VALUES (?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            kullanim["model"],
            kullanim["giris_token"],
            kullanim["cikis_token"],
            kullanim["sure_saniye"],
        ))