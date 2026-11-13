# Cevâmi 0.1.0 — yerel sürüm notları

**Güncelleme:** Kullanıcı `apdmrl/cevami` hedefini ve DB yüklemesini ayrıca onayladı. [Üretim rehberi](production.md) ve `data/v0.1.0/` manifestine bağlı sürüm eki paketi bu kapsama eklendi. Aşağıdaki ilk yerel hazırlık notları tarihsel düzeni anlatır; DB'ler artık sürümlü pakette ayrıca sağlanır. Canlı dağıtım yapılmadı.

Bu sürüm mevcut yerel okuyucunun kod, migration, test ve sürümlü küçük kaynak/inceleme kayıtlarını saklar. Uygulama sürümü `0.1.0`; yerel Git etiketi `v0.1.0` olarak hazırlanır. GitHub'a yükleme, hedef depo belirtilmeden yapılmaz.

## Depo kapsamı

Mevcut bağımsız `app/` Git deposu korunur. Üst proje klasörü, özgün program paketleri, referans SQLite/ZIP, araştırma arşivleri, PostgreSQL verisi, yedekler ve yerel ayarlar bu depoya alınmaz. Küçük `hadis_web/data/*.json` kayıtları uygulamanın sürümlü kanıt/yerelleştirme modelidir; ham külliyatla karıştırılmamalıdır. Bunların tarihsel sürümleri korunur.

`README.md` içindeki eski `../docs/`, `../research/` bağlantıları tam yerel çalışma klasörüne aittir. Bu not ve `CHANGELOG.md` kod deposu içinden okunabilir. Bu Git deposunu tek başına indirmek kaynak verisini veya mevcut PostgreSQL durumunu kurmaz; kaynak lisansı/yeniden dağıtım izni vermez.

## Gerekli klasör düzeni

```text
Hadis Projesi/
  app/                              # bu kod deposu
  references/datasets/jawami3_alkalem/jawami.db
  references/datasets/jawami3_alkalem/verification.json
  references/                       # kullanılan sabit kaynak arşivleri
  research/                         # bağlı araştırma/kanıt dosyaları
  GK4.5/GK4.5/Data/Books.zip
  docs/                             # proje araştırma ve teslim raporları
```

Git'ten kurarken kod deposu bu düzen içinde `app` adıyla yer almalıdır. Mevcut kaynakların hash/kimliği korunur. Boş veya farklı veriyi hazır yerel pilot yerine otomatik doldurmak bu sürümün işlemi değildir.

## Yerel çalıştırma

Python3.12, Git, mevcut Docker/PostgreSQL kurulumu ve yukarıdaki dosyalar gerekir. Yeni sanal ortam hazırlanıyorsa `app/` içinde:

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install --index-url https://pypi.org/simple --upgrade pip==26.3
.venv/Scripts/python.exe -m pip install -r requirements.lock
```

Bağlantı ayarı yalnız `.local/settings.json` veya `HADIS_DATABASE_URL` ortam değişkeninde tutulur. Ayar dosyası, DSN ve parolalar Git'e eklenmez. Mevcut çalışma verisinin kurulması/geri yüklenmesi ayrı, bilinçli veri işlemidir; bu komutlar migration/aktarımı otomatik başlatmaz.

Hazır yerel çalışma klasöründe:

```powershell
./start.ps1 -Status
./start.ps1
```

Üst klasördeki mevcut `Cevami.cmd` aynı okuyucuyu başlatır. Adres `http://127.0.0.1:8765/`; `/research` araştırma alanıdır. İstemci telefon ekranına uyumludur; bağımsız mobil uygulama değildir. Sunucu yerel erişimle sınırlıdır. Swagger/ReDoc arayüzü kapalı, OpenAPI şeması açıktır.

## Kaynaklara yazmadan sürüm kontrolü

Aşağıdaki sınama grubu geçici fixture'ları ve mevcut kaynakların salt okunur erişimini kullanır; tam depo test paketi değildir:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_security.py tests/test_presentation.py tests/test_search.py tests/test_presentation_api.py tests/test_reader_api.py tests/test_health.py tests/test_launcher.py -q
node --test tests/ui_pagination.cjs tests/ui_home_recovery.cjs
.venv/Scripts/python.exe -m pip check
```

Eski bütünleşme/çeviri testlerinin bir bölümü canlı PostgreSQL'de test şeması/migration oluşturur. İlk sürümü kontrol etmek için gelişigüzel tüm testleri çalıştırmak veya veri aktarmak gerekmez. Bu sürümdeki bu kontrollü grubun güncel sonucu teslim kaydında belirtilir; önceki testler yeniden çalıştırılmış sayılmaz.

## Git ve gizlilik

- Depo `.local`, `.venv`, `.env*`, `.superpowers`, DB/indeks, arşiv, yedek ve üretilen PDF'leri dışarıda bırakır. Dışlamak dosyayı silmez.
- İlk commit mevcut `feature/arabic-reader` dalındadır; henüz var olmayan `main` dalıyla birleştirme varsayılmaz.
- Commit adı bağlı GitHub hesabı `apdmrl`; kişisel e-posta yerine GitHub `noreply` adresi yalnız bu depoda kullanılır. Diğer depoların ayarları değiştirilmez. [GitHub commit e-postası belgesi](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address).
- `.gitattributes` Git'te metin satır sonlarını tutarlı saklar; mevcut çalışma ağacına toplu checkout/temizlik uygulanmaz.
- Kaynak verisi, çeviri doğruluğu, telif ve dağıtım hakkı yalnız kod commit'iyle onaylanmaz. Kaynak ve inceleme durumları aynen kalır.

Hesap/kişisel notlar, internet yayını, ayrı web DB rolü/TLS/dağıtık istek sınırı ve mobil uygulama bu yerel sürümün dışında. Çevirinin yeniden başlaması ayrıca kullanıcı yönlendirmesi gerektirir.
