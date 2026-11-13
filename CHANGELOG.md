# Sürüm geçmişi

## 0.1.0 — 2026-11-13

İlk yerel araştırma okuyucusu. Arapça asıl, kaynak kimliği, sened sırası ve ravi bağları korunur; mevcut Türkçe ve İngilizce içerik kaynak ve kapsam bilgileriyle gösterilir.

- Türkçe, İngilizce ve Arapça arama; eser filtresi, sayfalama ve klavyeyle öneri seçimi.
- Tek kayıt sayfası ve aynı kaydı koruyan araştırma görünümü; ayrı kaynak numaraları ve künyesi.
- Sened sayfalama/karşılaştırma, ravi kartı ve kaynakta kayıtlı cerh-ta‘dîl görüşleri.
- Seçili çeviride dil başına kaynak/bölüm sayacı; Arapça/Farsça rakamlarla kimlik araması.
- Kaynaklı yazdırma/PDF görünümü; gerçek yüklü sened kapsamı ve bekleyen ek sayfa notu.
- Yerel Host/Origin sınırı, CSP ve güvenlik başlıkları, girdi/sorgu sınırları, salt okunur web DB bağlantıları.
- Tek tık yerel açılış, durum kontrolü, ayrı doğrulanmış yedekleme araçları.
- Açık HTTPS üretim profili, Caddy/PostgreSQL Docker Compose düzeni, nonroot/salt okunur uygulama ve atomik ilk restore.
- GitHub sürüm eklerinde hash doğrulamalı veritabanı paketi; CI ve izole PostgreSQL geri alma/yetki sınamaları.

Bu teslim canlı internet yayını değildir; üretim yapılandırması [kurulum rehberindedir](docs/production.md). Kaynak/DB paketi aynı deponun sürüm eklerinden ayrıca doğrulanıp açılır. Çeviriler tüm külliyatta tamamlanmış, anlam/kapsam/baskı bakımından kesin onaylı veya uzman incelemeli sayılmaz. Çeviri üretimi beklemededir.

Kurulum düzeni, test kapsamı ve sürüm kontrolü sınırları: [yerel sürüm notları](docs/local-release-v0.1.0.md).
