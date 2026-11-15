# Fermec ARGE – Çift Dilli PDF Çeviri Sistemi

İngilizce PDF belgelerini OpenAI destekli çeviri işleminden geçirerek Türkçe–İngilizce çift dilli PDF çıktısı üreten, Docker Compose ile çalışan bir otomasyon projesidir.

Her çıktı sayfasının **sol yarısında Türkçe çeviri**, **sağ yarısında orijinal İngilizce sayfa** bulunur. Sağ taraftaki orijinal sayfa PyMuPDF kullanılarak PDF sayfası olarak yerleştirilir; sayfa görüntüye dönüştürülerek yeniden çizilmez.

## 1. Mimari

| Bileşen | Adres / port | Görev |
|---|---|---|
| FastAPI (`api`) | `http://localhost:8000` | Kaynak PDF analizi, sayfa ve OCR verilerine erişim |
| Çeviri servisi (`ceviri-servisi`) | `http://localhost:8001` | OpenAI API ve LangGraph ile metin çevirisi ve sayısal doğrulama |
| PDF işleyici (`pdf-isleyici`) | `http://localhost:8002` | Sayfaları işleme, çevirileri birleştirme, PDF ve rapor üretimi |
| n8n (`n8n`) | `http://localhost:5678` | İş akışını başlatma ve sonuç/hata yönetimi |

Servisler `docker-compose.yml` ile başlatılır. n8n, PDF işleyicinin `POST /run` adresini çağırır. PDF işleyici, `otomatik_ceviri.py` üzerinden diğer servislerle haberleşir.

## 2. Gereksinimler

- Docker Desktop ve Docker Compose desteği
- OpenAI API anahtarı ve API kullanımına uygun bakiye/limit
- İşlenecek İngilizce PDF dosyası
- n8n iş akışı JSON dışa aktarımı (ayrı teslim edilir)

Docker ile çalıştırmak için bilgisayarda ayrıca Python sanal ortamı oluşturmak gerekmez.

## 3. Sıfırdan kurulum

1. Kaynak kod deposunu bilgisayarınıza indirin veya klonlayın ve proje ana klasörünü açın.
2. Ana klasördeki `.env.example` dosyasını `.env` adıyla kopyalayın.
3. `.env` içindeki `OPENAI_API_KEY` değerini kendi API anahtarınızla değiştirin.
4. Proje ana klasöründe terminal açın ve servisleri başlatın:

   ```powershell
   docker compose up -d --build
   ```

5. Servislerin durumunu kontrol edin:

   ```powershell
   docker compose ps
   ```

6. Tarayıcıda `http://localhost:5678` adresini açın. n8n iş akışı JSON dosyasını n8n'e içe aktarın. İş akışını çalıştırmadan önce PDF işleyici çağrısının `http://pdf-isleyici:8002/run` adresine yönlendiğini kontrol edin.

**Güvenlik:** Gerçek API anahtarını README, ekran görüntüsü, n8n JSON dosyası veya Git deposunda paylaşmayın. `.env` dosyasını Git'e eklemeyin.

## 4. Kullanım

1. Çevrilecek PDF'yi proje ana klasöründeki `input/` klasörüne koyun. İşleyici, dosyayı kendisi seçmek yerine PDF API'sinin `/pdf/analyze` yanıtında bildirdiği dosyayı kullanır; bu nedenle birden fazla PDF varsa seçim davranışını ayrıca kontrol edin.
2. Docker servislerinin çalıştığından emin olun.
3. n8n'deki içe aktarılan iş akışını manuel olarak çalıştırın.
4. n8n, PDF işleyicinin `POST /run` uç noktasını çağırır. PDF işleyici işlemi başlatır ve tamamlanana kadar bekler.
5. İşlem tamamlandığında `output/` klasöründeki PDF ve raporları inceleyin.

n8n kullanılmadan PDF işleyici doğrudan da tetiklenebilir:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8002/run
```

Servisin hazır olup olmadığını kontrol etmek için:

```powershell
Invoke-RestMethod -Uri http://localhost:8002/health
```

**Not:** `POST /run` işlemi eşzamanlı ikinci PDF çalıştırmasını HTTP 409 ile reddeder. PDF işleyicide bir çalıştırma için 3600 saniye (60 dakika) zaman aşımı vardır.

## 5. İşleme mantığı

1. PDF API'sinden kaynak dosyanın adı ve sayfa sayısı alınır.
2. Sayfalar **en fazla beş sayfalık mantıksal pencereler** halinde, sırayla işlenir. Çeviri isteği sayfa bazında yapılır.
3. Sayfa metin blokları alınır. Gerekirse PDF'den doğrudan metin çıkarma veya OCR kurtarma yolu denenir.
4. Çeviri servisi OpenAI API üzerinden Türkçe çeviri üretir. Blok kimlikleri kontrol edilir; sayısal uyuşmazlıklarda yeniden çeviri denenebilir.
5. Tablo işleme metin çevirisinden ayrı yürütülür.
6. Tamamlanan sayfaların çeviri ve tablo bilgileri `output/checkpoints/` altında saklanır. Uygun checkpoint'ler sonraki çalıştırmalarda yeniden kullanılabilir.
7. Her kaynak sayfa için iki kat genişliğinde bir çıktı sayfası oluşturulur: solda Türkçe, sağda orijinal İngilizce sayfa.
8. PDF ve kontrol raporları `output/` klasörüne kaydedilir.

## 6. Çıktılar ve raporlar

Kaynak dosya adı `ornek.pdf` ise aşağıdaki dosyalar oluşturulabilir:

| Dosya | İçerik |
|---|---|
| `output/ornek_TR_EN.pdf` | Türkçe–İngilizce çift dilli PDF |
| `output/ornek_izlenebilirlik.json` | Sayfa ve blok bazında kaynak–çeviri eşleştirmesi |
| `output/ornek_maliyet_raporu.json` | Token kullanımı ve yapılandırılmış fiyatlara dayalı tahmini maliyet |
| `output/ornek_eksik_ceviri_kontrol.json` | Eksik metin/yerleştirme taraması ve manuel inceleme uyarıları |
| `output/otomatik_ceviriler.json` | Çevrilmiş metin blokları |
| `output/otomatik_tablolar.json` | İşlenmiş tablo verileri |
| `output/pencere_0001_0005.json` vb. | Beş sayfalık pencere çeviri kayıtları |
| `output/checkpoints/<dosya_adi>/page_0001.json` vb. | Sayfa bazında yeniden başlatma kayıtları |

Maliyet raporu **resmî fatura değildir**. Hesaplama, Docker yapılandırmasındaki `OPENAI_PRICING_MODEL`, `OPENAI_INPUT_USD_PER_MILLION`, `OPENAI_CACHED_INPUT_USD_PER_MILLION` ve `OPENAI_OUTPUT_USD_PER_MILLION` değerlerine dayanır. Model kimliği uyuşmazsa veya kullanım bilgisi eksikse maliyet hesaplanamayabilir. Ayrı tablo API işlemlerinin maliyetleri rapora dahil olmayabilir.

Kalite raporu, seçilebilir metin varlığı ve yerleştirme gibi kontroller yapar; OCR doğruluğunu veya Türkçe çevirinin anlamsal kalitesini otomatik olarak onaylamaz.

## 7. Sorun giderme

**Servisler açılmıyor:**

```powershell
docker compose ps
docker compose logs --tail=100
```

**OpenAI API hatası:** `.env` içindeki `OPENAI_API_KEY` değişkeninin tanımlı olduğunu ve hesabın API kullanımına uygun olduğunu kontrol edin. Anahtarın kendisini günlüklerde veya destek mesajlarında paylaşmayın. Ortam değişkeni değiştirildiyse ilgili konteyneri yeniden oluşturun.

**PDF bulunamadı:** Dosyanın `input/` klasöründe olduğunu ve PDF API'sinin doğru dosyayı analiz ettiğini kontrol edin.

**İşlem zaten çalışıyor (HTTP 409):** PDF işleyici aynı anda yalnızca bir çalıştırmaya izin verir. Mevcut işlem bitene kadar bekleyin.

**İşlem zaman aşımına uğradı (HTTP 504):** PDF işleyicinin `subprocess.run` zaman aşımı 3600 saniyedir. Çok uzun veya karmaşık belgelerde bu sınıra ulaşılabilir.

**Çıktı oluşmadı veya işlem durdu:**

```powershell
docker compose logs --tail=150 pdf-isleyici
docker compose logs --tail=150 ceviri-servisi
```

`output/checkpoints/` klasöründeki geçerli sayfa kayıtları sonraki çalıştırmada yeniden kullanılabilir.

**Metin sığmıyor:** Sistem belirli punto seçeneklerini dener; metin yerleşemiyorsa sessizce atlamak yerine hata verebilir. İlgili sayfayı ve günlükleri inceleyin.

## 8. Bilinen sınırlamalar

- Bazı taranmış sayfalarda OCR sonucu veya görsel yerleşimi manuel inceleme gerektirebilir.
- Karmaşık tablo, şekil ve çok yoğun metin yerleşimlerinde görsel eşleşme kusursuz olmayabilir.
- Otomatik kalite kontrolleri çevirinin anlamsal doğruluğunu garanti etmez.
- Bütçe kontrolü ve maliyet raporlaması aynı şey değildir: mevcut rapor tahmini maliyet hesaplar, API harcamasına kesin bir tavan koymaz.
- n8n iş akışı manuel tetiklemeye dayanır; klasöre dosya bırakılması tek başına otomatik çalıştırma anlamına gelmez.
- Büyük PDF'lerde işlem süresi artabilir; PDF işleyici 60 dakikalık çalıştırma sınırına sahiptir.

## 9. Teslim içeriği

- Git geçmişiyle kaynak kod deposu
- `docker-compose.yml`
- LangGraph çeviri kodu (`ceviri-servisi/graph.py`)
- n8n iş akışı JSON dışa aktarımı (ayrı dosya)
- Bu Türkçe `README.md` ve `.env.example`
- Örnek çift dilli PDF ve ilgili raporlar (teslim paketinde ayrıca sağlanır)

