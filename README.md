# Cevâmi

Arapça asıl metni, senedleri, ravileri ve kaynak künyesini birlikte sunan hadis araştırma uygulaması. Türkçe ve İngilizce çeviriler bağlı kaynakları ve kapsamlarıyla gösterilir.

**İlk sürüm: v0.1.0.** Web okuyucusu, çok dilli arama, sened karşılaştırma, ravi kartları ve kaynaklı yazdırma/PDF görünümü içerir. Çevirilerin tüm külliyatta tamamlandığı veya uzman onayı aldığı anlamına gelmez.

## Veritabanları

Veriler bu depoda [v0.1.0 sürüm eklerinde](https://github.com/apdmrl/cevami/releases/tag/v0.1.0) saklanır: [v0.1.0 veri manifesti](data/v0.1.0/manifest.json). Paket ana SQLite kaynağını, arama/araştırma DB'lerini, tutarlı PostgreSQL çalışma şeması export'unu ve gereken kaynak dosyalarını içerir. Parolalar, rollerin parolaları ve yerel ayarlar içermez.

```bash
git clone https://github.com/apdmrl/cevami.git
cd cevami
curl -fL --retry 3 -o data/v0.1.0/workspace.tar.gz.part001 https://github.com/apdmrl/cevami/releases/download/v0.1.0/workspace.tar.gz.part001
curl -fL --retry 3 -o data/v0.1.0/workspace.tar.gz.part002 https://github.com/apdmrl/cevami/releases/download/v0.1.0/workspace.tar.gz.part002
python3 -m scripts.data_release restore --manifest data/v0.1.0/manifest.json --destination .local/deploy-data/v0.1.0
```

Açma aracı parça/paket/dosya SHA256 değerlerini doğrular; var olan hedefin üzerine yazmaz. GitHub'ın kaynak ZIP indirmesi veritabanını içermez; sürüm eklerindeki iki dosyayı yukarıdaki komutlarla indirin. Ham kaynak DB4,28GiB olduğundan veri paketi iki sıkıştırılmış parçadan oluşur; normal Git'e büyük ham DB konulmaz.

## Üretim kurulumu

[Docker Compose + Caddy/HTTPS kurulum rehberi](docs/production.md) alan adı, veri açma, sır hazırlama, tek seferlik atomik DB restore ve başlatma adımlarını içerir. Uygulama/DB portları dışarı açılmaz. Web DB kullanıcısı yalnız SELECT yetkilidir; uygulama nonroot ve salt okunur dosya sistemiyle çalışır.

**Bu teslimde canlı sunucuya dağıtım yapılmadı.** Alan adı ve gerçek sunucu seçildiğinde rehber uygulanır. Parolalar `deploy/secrets/` altında yerel üretilir; Git'e gönderilmez.

## Mevcut yerel çalışma klasörü

Tam eski proje düzeninde `Cevami.cmd` veya `app/start.ps1` okuyucuyu açar. Adres `http://127.0.0.1:8765/`; araştırma alanı `/research`. Git'ten tek başına indirme için üretim rehberi veri yollarını ayrıca yapılandırır. Yerel moda yeni internet hostları otomatik eklenmez.

## Kontroller ve kaynak yaklaşımı

- [Sürüm geçmişi](CHANGELOG.md)
- [Yerel v0.1.0 kapsamı](docs/local-release-v0.1.0.md)
- [Üretim kurulumu ve işletim sınırları](docs/production.md)
- [Önceki yerel geliştirme günlüğü](docs/history-local-development.md)

CI, küçük geçici verilerle güvenlik/üretim/geri açma testlerini, izole PostgreSQL restore testini, istemci testlerini ve Docker build'i çalıştırır. Büyük veri paketi CI'da indirilmez; kaynak/çeviri verisine yazılmaz.

Arapça kaynak ve kimlikler korunur. Çeviri/kişi bilgisi, kaynak karşılaştırması ve varsa uzman incelemesi ayrı tutulur. Kod sürümü veya başarılı teknik test, metnin anlam/kapsam/telif bakımından onaylandığı anlamına gelmez. Kaynaklarda bulunmayan tarihsel ilişkiler tahminle tamamlanmaz.
