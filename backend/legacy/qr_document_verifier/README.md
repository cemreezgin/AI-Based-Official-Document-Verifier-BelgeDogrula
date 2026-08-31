# Güvenli QR Belge Doğrulama

## Kurulum

```bash
python3 -m venv .venv
source .venv/bin/activate
brew install zbar
python -m pip install -r requirements.txt
```

## Bulanıklık ve gürültü kurtarma

Standart akışta OpenCV ile kalite ölçümü, gürültü giderme, keskinleştirme,
CLAHE ve adaptive threshold otomatik denenir. Bunlar sonuç vermezse Restormer
isteğe bağlı ikinci aşama olarak çalıştırılabilir:

```bash
python -m pip install -r requirements-restormer.txt
git clone --depth 1 https://github.com/swz30/Restormer.git third_party/Restormer
curl -L -o third_party/Restormer/Motion_Deblurring/pretrained_models/motion_deblurring.pth \
  https://github.com/swz30/Restormer/releases/download/v1.0/motion_deblurring.pth
curl -L -o third_party/Restormer/Denoising/pretrained_models/real_denoising.pth \
  https://github.com/swz30/Restormer/releases/download/v1.0/real_denoising.pth
```

Restormer kurulduktan sonra ayrıca seçenek verilmez. Sistem doğrudan okuma ve
OpenCV aşamaları başarısız olursa Restormer'ı otomatik çalıştırır:

```bash
python verify_document_qr.py belge.png \
  --fetch
```

Restormer yalnız OpenCV aşaması başarısız olduğunda en olası köşe ve merkez
bölgelerinde çalışır. İyileştirilmiş görüntü hiçbir zaman tek başına kanıt
sayılmaz; içerik yine en az iki standart QR decoder tarafından aynı şekilde
okunmalıdır. CPU kullanımında işlem yaklaşık 10-30 saniye sürebilir; ilerleme
mesajları işlem sırasında ekranda gösterilir.

Gerekli bir teşhis durumunda Restormer özellikle kapatılabilir:

```bash
python verify_document_qr.py belge.png \
  --no-restormer
```

## Çalıştırma

Yalnızca QR ve hedef kontrolü:

```bash
python verify_document_qr.py belge.png \
  --fetch
```

Resmî PDF'leri HTTPS üzerinden geçici belleğe alma:

```bash
python verify_document_qr.py belge.png \
  --fetch
```

QR alan adı otomatik okunur. `gov.tr`, `bel.tr`, `pol.tr`, `tsk.tr`,
`edu.tr` ve `k12.tr` gibi belgeli kurum uzantıları doğrulanır; ardından tüm
erişim aynı tam alan adına sabitlenir. `--allowed-host` yalnız daha dar bir
exact-host politikası istenirse isteğe bağlı olarak kullanılabilir.

Sistem HTTP QR hedefini yalnızca aynı host, yol ve parametreleri koruyarak
HTTPS'e yükseltir. GlobalSign ara sertifikası SHA-256 parmak iziyle
sabitlenmiştir. Her yönlendirme ve PDF bağlantısı exact-host allowlist, genel
IP, TLS, içerik türü, boyut ve `%PDF-` imzasıyla yeniden doğrulanır.

PDF'ler diske yazılmaz. JSON çıktısının sonundaki `user_summary` sonucu sade
Türkçeyle açıklar.
