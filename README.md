# AI Based Official Document Verifier - BelgeDogrula

Yerel PaddleOCR ve Qwen kullanan belge metni doğrulama uygulaması.

## Bileşenler

- `frontend/`: Standart Next.js arayüzü
- `backend/`: FastAPI doğrulama servisi
- `backend/legacy/qr_document_verifier/`: Değiştirilmeden korunmuş QR çekirdeği
- `backend/legacy/paddleocr_qwen/`: Değiştirilmeden korunmuş eski alan çıkarma çekirdeği; zorunlu alan kategorileri çalışma akışında kullanılmaz
- `compose.yaml`: Linux/Docker dağıtım yapısı

## Platform desteği

| Platform | Destek durumu | Çalıştırma biçimi |
|---|---|---|
| Linux AMD64 | Destekleniyor | Docker Engine, Linux containers |
| Linux ARM64 | Destekleniyor | Docker Engine, Linux containers |
| Windows 10/11 | Destekleniyor | Docker Desktop, **Linux containers** ve WSL 2 |
| Windows native Python | Desteklenmiyor | OCR pipe ve ZBar DLL farkları nedeniyle kullanılmamalı |
| macOS ARM64 | Geliştirme desteği | Native geliştirme veya Docker Desktop |

Windows desteği native Python kurulumu anlamına gelmez. Uygulama Windows'ta
Docker Desktop'ın Linux container motorunda çalıştırılır. ZIP içinden bir
`.venv`, `node_modules` veya `.next` klasörü çıkmamalıdır; bağımlılıklar hedef
makinede kilit dosyalarından veya Docker imajı içinde yeniden kurulur.

## macOS geliştirme

Önce Ollama, Python 3.11, Node.js 22 ve sistem QR kitaplığını kurun:

```bash
brew install ollama python@3.11 node zbar
```

```bash
ollama serve
ollama pull qwen3:4b

cd backend
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Başka bir terminalde:

```bash
cd frontend
corepack enable
pnpm install
pnpm dev
```

Arayüz: `http://localhost:3000`

API: `http://localhost:8000`

## Docker / Linux

Tüm web uygulamasını başlatmak için:

```bash
docker compose up --build
```

Arayüz ve API birlikte `http://localhost:8080` adresinde açılır.

Sağlık kontrolü:

```bash
curl --fail http://localhost:8080/health
docker compose ps
```

İlk kurulum PaddleOCR bileşenlerini hazırladığı için sonraki açılışlardan uzun
sürebilir. Backend imajı yalnız CPU PyTorch deposunu kullanır;
`requirements-cpu.lock.txt` içindeki `+cpu` sürümleri CUDA paketlerinin
yanlışlıkla indirilmesini engeller.

## Windows 10/11 — Docker Desktop

Gereksinimler:

- WSL 2 etkin Windows 10 veya Windows 11
- Docker Desktop; motor ayarı **Linux containers**
- Windows üzerinde çalışan Ollama ve indirilmiş `qwen3:4b` modeli
- En az 16 GB RAM ve ilk imaj/model kurulumu için yeterli disk alanı

PowerShell'de proje klasöründen:

```powershell
ollama pull qwen3:4b
ollama serve
```

Ollama açıkken ikinci bir PowerShell penceresinde otomatik kontrolü çalıştırın:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows-smoke-test.ps1
```

Betik Docker motorunun Linux modunda olduğunu, Qwen modelini, iki uygulama
container'ını ve `http://localhost:8080/health` sonucunu doğrular. Başarılı
olduğunda uygulama `http://localhost:8080` adresindedir.

Manuel başlatma için:

```powershell
docker compose up --build --detach
Invoke-RestMethod http://localhost:8080/health
docker compose ps
```

Servisleri durdurmak için `docker compose down` kullanılır.

## Tekrarlanabilir bağımlılıklar

- `frontend/pnpm-lock.yaml`: Node bağımlılıklarını ve bütünlük özetlerini kilitler.
- `backend/requirements-base.lock.txt`: Ortak Python çalışma zamanı sürümlerini kilitler.
- `backend/requirements-cpu.lock.txt`: Linux container için CPU-only Torch ve
  Torchvision sürümlerini kilitler.
- `backend/requirements.txt`: Yalnız native macOS geliştirme kurulumudur.

Bağımlılık sürümleri otomatik olarak genişletilmemelidir. Yeni sürümler ayrı bir
değişiklikte AMD64, ARM64 ve sentetik kabul testlerinden geçirilmelidir.

## Testler ve CI

Ana backend testleri:

```bash
cd backend
python -m unittest discover -s tests -v
cd legacy/qr_document_verifier
python -m unittest discover -s tests -v
```

`test_synthetic_end_to_end.py`, tamamı çalışma anında üretilen bir TEST belgesi
ile HTTP yükleme → gerçek üçlü QR decoder → güvenli resmî hedef adaptörü → OCR
adaptörü → metin karşılaştırma → eşleşme kararı zincirini doğrular. Ağ erişimi,
gerçek belge ve gerçek kişi/kurum verisi kullanmaz.

`.github/workflows/platform-containers.yml` aşağıdakileri hem `linux/amd64` hem
`linux/arm64` için çalıştırır:

1. Temiz kaynak denetimi
2. Backend ve frontend imaj derlemesi
3. İmaj mimarisi doğrulaması
4. Backend, güvenlik ve sentetik kabul testleri
5. Backend `/health` ve frontend HTTP sağlık kontrolü

## Temiz dağıtım paketi

Platforma özel geliştirme çıktıları içermeyen ZIP üretmek için:

```bash
python tools/package_release.py --check
python tools/package_release.py --output ../belgedogrula-release.zip
```

Paketleyici `.venv`, `node_modules`, `.next`, pnpm önbelleği, Python önbelleği,
macOS metadata dosyaları, mevcut ZIP dosyaları ve geliştirici makinesine bağlı
mutlak shebang'leri reddeder veya dışarıda bırakır.

## Güvenlik sınırları

- En fazla 15 MB PDF, JPEG veya PNG kabul edilir.
- QR içeriği yalnızca en az iki standart decoder uzlaştığında kabul edilir.
- QR içeriği AI tarafından tahmin edilmez veya tamamlanmaz.
- Resmî hedefler exact-host sabitleme, genel IP, TLS, içerik türü ve PDF imzası
  kontrollerinden geçirilir.
- Resmî hedef doğrudan belge veya HTML doğrulama sayfası sunabilir. Belge
  bağlantıları aynı sabitlenmiş hostta, en fazla 2 gezinme derinliği ve 12 URL
  sınırıyla kaynak sırasına göre incelenir.
- Yüklenen belgenin ve resmî adayın OCR metinleri zorunlu alanlara ayrılmadan
  genel metin benzerliği üzerinden karşılaştırılır.
- Büyük/küçük harf, noktalama, boşluk ve `i/ı`, `g/ğ`, `s/ş`, `c/ç`, `o/ö`,
  `u/ü` Türkçe karakter farkları karşılaştırma öncesinde normalize edilir.
- Satır ve kelime sırası farklılıklarına dayanıklılık için sıralı benzerlik ile
  kelime kümesi benzerliğinin yüksek olanı kullanılır.
- `%85` ve üzeri skorlar otomatik eşleşir, `%75` altı otomatik reddedilir.
  Aradaki gri bölge yerel `qwen3:4b` tarafından OCR gürültüsü, yerleşim ve
  anlamlı içerik çelişkisi açısından yorumlanır. Sınırlar
  `QWEN_REVIEW_MIN_SIMILARITY` ve `AUTO_MATCH_SIMILARITY` ile değiştirilebilir.
- Birden fazla PDF adayı kaynak sırasıyla işlenir. Her adayın ilk 12 OCR satırı
  önce yüklenen belgenin ilk satırlarıyla karşılaştırılır; `%35` başlangıç
  benzerliği oluşmazsa Qwen çalıştırılmadan sıradaki PDF'ye geçilir.
- Otomatik veya Qwen destekli güvenli eşleşme oluştuğu anda kalan bağlantılar
  indirilmeden arama sonlandırılır.
- En fazla 5 aday belge, dosya başına 20 MB, istek başına 15 saniye ve toplam
  işlem için 30 dakika sınırı uygulanır.
- Geçici belgeler işlem bitince silinir.
- Qwen yalnız gri bölgedeki iki OCR metnini yorumlar; QR çözmez, eksik bilgi
  üretmez ve belge metni içindeki talimatları uygulamaz.
