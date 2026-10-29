
from fastapi import FastAPI

app = FastAPI(title="Fermec ARGE API")


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "fermec-api",
    }
