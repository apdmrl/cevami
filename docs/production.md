# Üretim kurulumu — v0.1.0

Bu dosyalar Docker Compose ile tek sunucuda kurulacak ilk üretim düzenini hazırlar. Bu teslim gerçek sunucuya dağıtım yapmaz; DNS veya sertifika oluşturulmadı. Gerçek alan adı, sunucu ve ağ uygun olduğunda aşağıdaki adımlar uygulanır. Windows'taki mevcut yerel okuyucu ve PostgreSQL kurulumu bağımsız kalır.

## Mimari ve sınırlar

- Caddy yalnız80/443portlarını açar; gerçek alan adı üzerinden HTTP→HTTPS ve otomatik TLS sağlar.
- Uygulama UID10001, salt okunur root ve veri mount'u, kısıtlı yetkiler ve kaynak limitleriyle çalışır.8080hosta açılmaz. Yalnız proxy'nin sabit özel IP'sinden forwarded bilgisi kabul edilir.
- PostgreSQL18yalnız iç ağdadır;5432hosta açılmaz. Kalıcı veri ayrı Docker volume'undadır. Owner parolası uygulamaya verilmez.
- Web kullanıcısı `cevami_web` yalnız SELECT yetkilidir; role/bağlantı düzeyinde salt okunur ve süre sınırlıdır. Yeni hesap veya web üzerinden veri değiştirme ucu yoktur.
- SQLite, kaynak ZIP ve tanıklar salt okunur monte edilir. Üretim açılışı ana kaynağın sabit SHA256 değerini doğrular; büyük dosya nedeniyle ilk açılış zaman alabilir.
- Otomatik yeniden başlatma, healthcheck, işlem/bellek/CPU ve log boyutu sınırları vardır. Bunlar internete açık yük/DDoS sınaması veya tam sunucu güvenlik sertifikası değildir.

## 1. Kodu ve veriyi al

Sunucuda Docker Engine+Compose, curl ve Python3.12 gerekir. Yeni bir klasörde:

```bash
git clone https://github.com/apdmrl/cevami.git
cd cevami
git checkout v0.1.0
curl -fL --retry 3 -o data/v0.1.0/workspace.tar.gz.part001 https://github.com/apdmrl/cevami/releases/download/v0.1.0/workspace.tar.gz.part001
curl -fL --retry 3 -o data/v0.1.0/workspace.tar.gz.part002 https://github.com/apdmrl/cevami/releases/download/v0.1.0/workspace.tar.gz.part002
python3 -m scripts.data_release restore --manifest data/v0.1.0/manifest.json --destination .local/deploy-data/v0.1.0
```

Paket yaklaşık1,48GiB sıkıştırılmış veridir; ana kaynak açıldığında4,28GiB'dir. Paket parçaları, açılan dosyalar, DB volume'u, Docker katmanları ve geçici restore SQL'i için yeterli boş alan bırakın. Araç önce parça/paket hash'lerini, sonra her dosyayı doğrular. Windows ve Linux'ta atomik, üzerine yazmayan hedef yayını kullanır; desteklenmeyen sistemde güvenli biçimde durur. macOS hostunda gerekirse aracı bir Linux/Python container'ı içinde çalıştırın.

Var olan hedefte otomatik üzerine yazma yoktur. Eksik veya değiştirilmiş parça veri yerine kabul edilmez. Yeni sürüm için farklı hedef dizini kullanın. Kaynak DB, arama DB, araştırma DB ve `postgres/working.dump` manifestte açıkça listelenir. `working.dump` yalnız çalışma şemasıdır; PostgreSQL kullanıcı/rol parolaları veya yerel ayarlar değildir.

## 2. Sırları ve alan adını hazırla

```bash
python3 -m scripts.production_setup --directory deploy/secrets
cp deploy/.env.example deploy/.env
```

`deploy/.env` içinde `CEVAMI_DOMAIN` değerini yalnız gerçek alan adıyla doldurun. Varsayılan boş bırakıldığı için ayarsız üretim başlatılmaz. DNS A/AAAA kaydı bu sunucuya yönelmeli,80/443erişilebilir olmalıdır. AAAA yayımlanırsa sunucunun IPv6 erişimi de gerçekten çalışmalıdır.

Parolalar rastgele üretilir, yazdırılmaz ve yeniden çalıştırmada değiştirilmez. Eksik/mevcut karışık sır seti varsa araç durur. Linux'ta sır dizini0700, dosyalar0444'tür: özel üst dizin hostta diğer kullanıcıların erişimini önler, seçilmiş file-backed Docker secret'ı nonroot container okuyabilir. Windows'ta bu POSIX modları yerine dosyaların NTFS erişim izinlerini koruyun. Sır dosyalarını veya `.env` dosyasını Git'e eklemeyin. Çalışan DB'nin sırlarını dosyayı değiştirerek rastgele yenilemeyin; ayrıca parola rotasyonu planı gerekir.

Varsayılan özel ağ `172.30.80.0/24`, dinamik adres havuzu `172.30.80.128/25`, proxy IP'si `172.30.80.2`dir. Hostta çakışma varsa `.env` içindeki subnet, dinamik havuz ve proxy IP'sini birlikte değiştirin. Proxy adresi subnet içinde ve dinamik havuzun dışında olmalıdır; app de aynı sabit proxy adresine güvenir.

`CEVAMI_DATA_DIR` Compose dosyasına göre yorumlanır; örnekte `../.local/deploy-data/v0.1.0`dir. Mutlak yol da kullanılabilir. Bu dizine sır dosyası koymayın: doğrulanmış, yayımlanan veri UID10001tarafından okunabilmesi için0755/0644moduyla açılır.

## 3. Yeni üretim DB'sine tek seferlik restore

```bash
docker compose --env-file deploy/.env -f deploy/compose.yml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yml up -d database
docker compose --env-file deploy/.env -f deploy/compose.yml --profile tools run --rm restore
```

Restore yalnız yeni, boş `hadis` şemasına ve mevcut olmayan web rolüne uygulanır. Var olan şema veya rol varsa reddeder; temizleme/üzerine yazma yapmaz. Önce SQL üretimi tamamlanıp kontrol edilir; ardından şema/veri ile rol/yetkiler aynı PostgreSQL transaction'ında uygulanır. Bir adım başarısız olursa yarım şema bırakılmaz. Yaklaşık285MiB çözümlenen SQL için restore container'ında1GiBgeçici alan ayrılmıştır.

Bu araç yeni üretim kurulumuna aittir. Windows'taki mevcut yerel DB'ye yönlendirmeyin. `down --volumes` kalıcı DB'yi siler; rutin kapatma veya güncellemede kullanmayın. Kullanıcı verisi eklenmiş bir kuruluma bu başlangıç restore'unu tekrar uygulamayın.

## 4. Uygulamayı ve HTTPS proxy'yi başlat

```bash
docker compose --env-file deploy/.env -f deploy/compose.yml up -d --build
docker compose --env-file deploy/.env -f deploy/compose.yml ps
docker compose --env-file deploy/.env -f deploy/compose.yml logs --tail=100 app caddy
```

İlk kaynak doğrulamasından sonra app sağlıklı olunca Caddy başlar. Gerçek alan adıyla `https://ALAN_ADINIZ/api/health` yanıtında `ready:true` görülmelidir. Caddy'nin ACME sertifika işlemi ancak gerçek kurulumda yapılır; geliştirme kontrolünde sertifika üretilmez. HSTS bir yıl sürelidir, yalnız açık üretim profilinde verilir; localhost moduna eklenmez.

Uygulama ve DB portlarını sonradan ayrıca public açmayın. Docker dışındaki SSH/firewall/OS güncellemeleri, izleme/uyarı, erişim politikası ve yedekleme planı sunucu seçildiğinde host üzerinde ayrıca uygulanır. Bu dosyalar o sunucu işlemlerini yapılmış saymaz. Sağlık durumu bozulduğunda logları inceleyin; healthcheck tek başına tüm dış bağımlılıkları veya akademik doğruluğu onaylamaz.

## Kontroller ve bakım

CI küçük sahte verilerle çalışır; canlı kaynak/DB gerektiren eski veri aktarım testlerini otomatik çalıştırmaz. İzole PostgreSQL testi rol kurulumu hatasında geri alma, güvenli tekrar, başarılı restore ve SELECT-only yetkisini sınar. Docker/CI temel araçları sabit commit/digest ile pinlidir; güvenlik güncellemelerinde bu pinler ve kilitler bilinçli yenilenmelidir.

Veri paketini sürüm eklerinden almak, şema migration'ı veya yeni çeviri onayı üretmez. Yeni içerik için yeni sürümlü paket ve kontrollü geçiş gerekir. Mevcut public API yazma yapmadığından web rolü bunun için genişletilmez. Eski snapshot ve kaynak kimlikleri korunmalıdır.
