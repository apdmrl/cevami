# Sürümlü veritabanları

`v0.1.0/manifest.json`40dosyanın SHA256 değerlerini ve iki sürüm eki parçasını tanımlar. Paket; ana Cevâmi SQLite kaynağı, mevcut PostgreSQL çalışma şeması export'u, arama/araştırma DB'leri, Books.zip ve uygulamanın kaynak karşılaştırmasında okuduğu sabit tanıkları içerir.

```bash
curl -fL --retry 3 -o data/v0.1.0/workspace.tar.gz.part001 https://github.com/apdmrl/cevami/releases/download/v0.1.0/workspace.tar.gz.part001
curl -fL --retry 3 -o data/v0.1.0/workspace.tar.gz.part002 https://github.com/apdmrl/cevami/releases/download/v0.1.0/workspace.tar.gz.part002
python3 -m scripts.data_release restore --manifest data/v0.1.0/manifest.json --destination .local/deploy-data/v0.1.0
```

Dosyaları doğrudan birleştirip körlemesine açmayın; araç parça/paket/dosya hash'lerini ve güvenli hedefleri doğrular. Var olan hedefin üzerine yazmaz. Geri açma, PostgreSQL'e otomatik bağlanmaz veya veri yazmaz. PostgreSQL restore için [üretim rehberini](../docs/production.md) izleyin.

Bu paket kaynak/kapsam/çeviri uzman onayı değildir; mevcut durumları korur. Parola, DSN, özel yedek ve yerel ayar pakete alınmamıştır. Kaynak ve küçük sürümlü kanıt JSON'ları Git satır sonu dönüşümüyle değiştirilmez.
