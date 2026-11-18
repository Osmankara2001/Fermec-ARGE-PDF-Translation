
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    requests \
    pymupdf \
    openai

COPY otomatik_ceviri.py .
COPY kalite_denetimi.py .
COPY tablo_isleyici.py .
COPY tablo_cizici.py .
COPY gorsel_yerlestirici.py .
COPY pdf_isleyici.py .

EXPOSE 8002

CMD ["uvicorn", "pdf_isleyici:app", "--host", "0.0.0.0", "--port", "8002"]
