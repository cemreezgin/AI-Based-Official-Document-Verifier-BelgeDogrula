# BelgeDoğrula geliştirme kuralları

- Uygulama çalışma zamanında OpenAI API veya ChatGPT Sites kullanma.
- QR içeriğini hiçbir modelle tahmin etme; decoder uzlaşmasını zorunlu tut.
- `backend/legacy/` altındaki korunmuş kaynakları doğrudan değiştirme.
- Yeni entegrasyonları legacy kaynakların etrafında adaptör olarak yaz.
- Belge gövdelerini loglama veya kalıcı depolama.
- Test fixture'larında gerçek belge, kişi, kurum, adres, belge numarası,
  doğrulama kodu veya resmî URL verisi tutma; yalnız açıkça sentetik
  `TEST` / `ÖRNEK` verileri kullan.
- macOS 8 GB geliştirme ortamında PaddleOCR ve Qwen'i sıralı çalıştır.
- Değişikliklerden sonra frontend derlemesini, backend testlerini ve güvenlik
  testlerini çalıştır.
