
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException

app = FastAPI(title="Fermec PDF Isleyici")

calisma_kilidi = threading.Lock()


@app.get("/health")
def saglik_kontrolu():
    return {"durum": "hazir"}


@app.post("/run")
def ceviriyi_baslat():
    if not calisma_kilidi.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail="Baska bir PDF islemi devam ediyor."
        )

    try:
        sonuc = subprocess.run(
            [sys.executable, "-u", "otomatik_ceviri.py"],
            capture_output=True,
            text=True,
            timeout=3600,
            cwd="/app"
        )

        if sonuc.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail={
                    "mesaj": "PDF isleme basarisiz.",
                    "hata": sonuc.stderr[-4000:],
                    "kayit": sonuc.stdout[-4000:]
                }
            )

        return {
            "durum": "tamamlandi",
            "mesaj": "PDF isleme komutu tamamlandi.",
            "kayit": sonuc.stdout[-6000:]
        }

    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail="PDF isleme zaman asimina ugradi."
        )

    finally:
        calisma_kilidi.release()
