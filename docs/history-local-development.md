# Cevâmi — ilk yerel web sürümü

**Yerel sürüm0.1.0:** Kod deposunun sınırları, dışarıda tutulan kaynak/DB dosyaları ve tekrar çalıştırma adımları [sürüm notlarında](docs/local-release-v0.1.0.md); özellik özeti [CHANGELOG](CHANGELOG.md) içinde. Bu, mevcut veriyle çalışan ilk yerel sürümdür; tek başına kurulabilen veri paketi veya internet yayını değildir.

**Yerel güvenlik ve PDF, 13 Kasım:** Ek sened beklenirken yazdırılan görünüm açık yükleme notu içerir. Yerel Host/Origin sınırı, CSP/güvenlik başlıkları, girdi ve sorgu süre sınırları, web PostgreSQL salt okunur bağlantıları eklendi.133Python/56istemci testi geçti; paket taramasında bildirimi olan venv pip26.3'e yükseltildi. Yeni venv kurulurken önce `.venv/Scripts/python.exe -m pip install --index-url https://pypi.org/simple --upgrade pip==26.3` kullanılmalı. Servis yalnız yerel kullanım içindir; Swagger/ReDoc arayüzleri kapalı, OpenAPI şeması açıktır. [Kapsam ve doğrulama sınırları](../docs/30-yerel-guvenlik-ve-pdf-duzeltmesi.md).

**Web kullanım düzeltmeleri, 13 Kasım:** Çeviri göstergesi seçili dile bağlandı; Arapça/Farsça rakamlarla kimlik araması düzeltildi. Yardımcı yazılar koyulaştırılıp büyütüldü, dar ekran menüsü düzenlendi. Bilinen eski gezinme ibareleri okuma görünümünden ayrılırken özgün metin ayrıntılarda korundu. Temel kayıt isteği zaman sınırı/iptal/yeniden deneme kazandı; İngilizce dizin erişim hatası da tekrar denenebilir.44Python ve54istemci testi geçti. Çeviri çalışması duruyor. [Kapsam, kararlar ve doğrulama](../docs/29-web-kullanim-duzeltmeleri.md).

**Kaynak künyeli yazdırma, 13 Kasım:** Kaynak satırındaki **Yazdır / PDF** düğmesi Arapça aslı, açık seçili çeviriyi, yüklenen senedlerin açık kapsamını ve kaynak künyesini tarayıcının yazdırma görünümünde birleştirir. Ctrl+P de aynı görünümü kullanır; yazdırma ekranından PDF kaydedilebilir. Kalan senedler önce ekrandan yüklenmelidir. [Kullanım, sınırlar ve doğrulama](../docs/27-kaynak-kunyeli-yazdirma.md).

**Kaynak bütünlüğü, 12 Kasım:** Özgün SQLite, Türkçe/İngilizce arama tanıkları ve PostgreSQL metin/sened/ravi/inceleme bağları birlikte denetlendi. Teknik hata yok; özgün kaynaktaki tek boş sened alanı uyarı olarak korunuyor. Yeni salt okunur komut: `app/` içinde `.venv/Scripts/python.exe -m scripts.audit_sources --output .local/source-integrity-20261112.json`. Çıktı dosyası yeni olmalıdır; kod0 uyarıları dışlamaz. Önceki doğrulanmış yedek ve sabit kaynaklardan gelen asgari envanter, eksilen kapsamın sessizce başarılı sayılmasını engeller. Bu araç anlam veya uzman onayı vermez. [Sonuçlar, kapsam ve sınırlar](../docs/26-kaynak-butunlugu-denetimi.md).

**Kullanım rehberi ve görünüm geçişi:** Arama, sade okuma ve araştırma sayfasındaki **Kullanım rehberi** düğmesi sayfaya göre kısa adımları ve bölüm bağlantılarını açar. Rehberi kapatmak sorguyu/filtreleri değiştirmez. **Sade okumaya geç / Araştırma alanına geç** aynı GK kaydını, seçili dili ve bölüm hedefini korur; **Hadis ara** aramaya dönüşü sağlar. [Kapsam ve doğrulama](../docs/25-kullanim-rehberi-ve-gorunum-gecisi.md).

**Bölüm karşılaştırma ve doğrudan atıf:** Kaynaklı Türkçe bölümlerde Arapça asıl/Türkçe karşılaştırma açılabilir; geniş ekranda yan yana, dar ekranda alt alta görünür. Sorunlu metinler kapalı kalır; genel çeviri adaylarına sahte hizalama yapılmaz. Bağlantı ve atıf kopyalama kanonik hadis adresi kullanır; clipboard reddinde seçilebilir metin sunulur. [Kapsam](../docs/17-karsilastirma-ve-dogrudan-atif.md). Yeni canlı test: `.venv/Scripts/python.exe tests/ui_comparison.py`.

**Eser filtresi ve kesintiye dayanıklı okuma:** Arama sonuçları gerçek eşleşen eserlere göre daraltılabilir; sorgu/dil/eser bağlantıda ve geri dönüşte korunur. Arapça asıl çeviri/sened servisinden bağımsız açılır; ek veri arızası yokluk diye sunulmaz ve yeniden denenebilir. Sened sayfalamasında zaman sınırı ve bölüm içi hata/yeniden deneme vardır. [Kapsam ve doğrulama](../docs/16-eser-filtresi-ve-dayanikli-okuma.md). İsteğe bağlı canlı test: `.venv/Scripts/python.exe tests/ui_resilience.py --url http://127.0.0.1:8765`.

**Kullanım ve teknik denetim:** Arama eşleşmeleri kaynak metnin ilgili bölümünde vurgulanır; bilinen eserlerin Türkçe adları ve ayrı GK/numara alanları gösterilir. Hadis sayfasında bölüm bağlantıları vardır. Kaynak ve arama bağlarını salt okunur denetlemek için `app/` içinde `.venv/Scripts/python.exe -m scripts.audit_reader --output .local/reader-integrity.json`. Kapsamı ve bir özgün boş sened alanı bulgusunu [denetim raporunda](../docs/15-kullanim-ve-kaynak-denetimi.md) okuyun. Bu araç anlam/uzman onayı üretmez. Kişiselleştirme ve çeviri çalışmaları bu teslimin dışındadır.

**Web, 4 Kasım:** `/` sade Türkçe/İngilizce/Arapça arama ekranı; `/hadith/146_1` paylaşılabilir tek kayıt; `/research?hadith=146_1` ayrıntılı araştırma alanıdır. Eski `/?hadith=146_1` bağlantıları tek kayıt sayfasına yönlenir. Yazarken öneriler, dil filtresi, klavye seçimi ve URL'de saklanan sorgu vardır. Çeviri ve kaynak ayrıntıları ayrı gösterilir; sorunlu Türkçe adaylar kapalı kaynak ayrıntısında tutulur.

Türkçe/İngilizce arama `.local/search.sqlite` yan dizinini kullanır. 21.775 farklı GK kaydı için 17.424 Türkçe ve 21.996 İngilizce kaynak tanığı içerir; bütün kütüphanenin çevrildiği anlamına gelmez. Kaynaklar aynı sabit Hadith API revision'ından gelir; İngilizce arşiv ve hash manifesti `../references/search/fawazahmed0-20261104/` altındadır. Kaynak içi Arapça anahtar bağı ve tam Arapça kelime eşitliği korunur; eşleştirme anlam, kapsam, çevirmen veya baskı onayı değildir. Çalışma PostgreSQL verisine yeni çeviri/inceleme aktarılmaz.

Dizini yeniden üretmek için `app/` içinde `.venv/Scripts/python.exe -m scripts.build_search`. Kaynak hash'leri uyuşmazsa işlem durur; kaynak DB değişmez. İsteğe bağlı gerçek tarayıcı testleri için `.venv/Scripts/python.exe -m pip install playwright`; ardından `tests/ui_search.py --url http://127.0.0.1:8765`, `tests/ui_translation_race.py --url http://127.0.0.1:8765` ve `tests/ui_dialog.py` çalıştırılabilir. Testler ayrı headless Brave profili açar; kullanıcı sekmelerine bağlanmaz.

**Güncel aşama (4 Kasım):** 1.000 kayıtlık toplu pilot ve kaynaklı Türkçe bölümler eklendi. İlk 50 kaydın gerçek kapsamı ve kalan işler [teslim raporunda](../docs/14-toplu-ceviri-pilotu.md); aşağıdaki eski aşama sayıları tarihsel notlardır.

Arapça asıl metin, kaynak künyesi, sıralı senedler ve ravi kartları. Türkçe metinler ayrı kaynak sürümlerine bağlı **inceleme adaylarıdır**. Kaynak karşılaştırması ve uzman incelemesi ayrı tutulur.

Hedef Türkçeleştirme bütün içerikleri kapsar: rivayetler, sened ifadeleri, kişi/ravi bilgileri, biyografiler, yaşadığı yerler, cerh-ta‘dîl ve kaynak hükümleri, eser/bab adları ve künyeler. Özel adlarda Türkçe yazım/çevriyazı özgün Arapçayla birlikte korunur. İlk sürümde bu alanların tamamı henüz Türkçeleştirilmiş değildir.

İlk alan pilotu eklendi: Buhârî’nin ilk senedindeki yedi ravi için 76 Türkçe alan kaydı. Sened ve ravi kartlarında ikincil Türkçe adlar, yerler, kaynak değerlendirmeleri, görev/nisbe/akrabalık alanları ve kısa kaynak özetleri görünür. Her alan kaynak ve durum taşır; tam biyografi/cerh-ta‘dîl çevirisi henüz tamamlanmadı. Ayrıntı: `../docs/06-ravi-turkcelestirme.md`.

V3 kaynak denetiminde 40 alanın bilgisi yayımlanmış Türkçe kaynaklarla bütünüyle desteklendi; 23 alan kısmen, 1 alan yalnız terim bakımından desteklendi; 6 alanda yeterli kaynak bulunamadı. Bunlar ve 6 kısa asistan özeti, birebir Türkçe kitap alıntısı olarak sunulmaz. V3'ün 30 bekleyen alanı aşağıdaki v4'te yeniden sınıflandırıldı. Ayrıntı: `../docs/07-turkce-kaynak-denetimi.md`.

V4 yeniden kontrolü, altı kaynak açığını bir açık asistan çeviri taslağı / dört Türkçe kaynak adayı / bir belirsiz kaynak ifadesi olarak ayırır. Etiketler ravi kartında görünür. “Taramada bulunamadı”, çevirinin dünyada hiç olmadığı anlamına gelmez. Son durum: 46 kaynak karşılaştırması, 29 bekleyen, 1 problem; 158 geçmiş / 76 aktif kayıt. Devam planı: `../docs/08-asistan-cevirisi-ve-calisma-kuyrugu.md`.

## Çalıştırma

Proje klasöründeki **Cevami.cmd** dosyasına çift tıklayın. Başlatıcı kurulu Docker Desktop ve mevcut veri konteynerini gerektiğinde açar; kaynak/arama/veritabanı erişimini denetledikten sonra tarayıcıyı açar. Hazır uygulama varsa aynı sunucu kullanılır. Eksik veri otomatik aktarılmaz; hata penceresindeki açıklama okunabilir. Sunucu arka planda çalışır; sonraki açılış aynı sunucuyu kullanır.

Bu bilgisayarda kurulum ve Buhârî pilot aktarımı yapıldı. PowerShell'den açmak için:

```powershell
cd 'D:\workspace\02_projeler\Hadis Projesi\app'
.\start.ps1
```

Adres: http://127.0.0.1:8765 . Tarayıcı açmadan kontrol için `./start.ps1 -NoBrowser`; servis başlatmadan durum görmek için `./start.ps1 -Status`. Mevcut portta başka bir uygulama veya sağlık ucu olmayan eski okuyucu varsa güvenli biçimde açıklama gösterilir; süreç sonlandırılmaz. Sağlık kontrolü `/api/health` üzerinden yapılır; başlangıç günlükleri `.local/logs` altındadır. Bu hızlı kontrol tam kaynak bütünlüğü veya çeviri doğruluğu denetimi değildir.

Python 3.11+ ve PostgreSQL 18 kullanılıyor. Bağımlılıklar `requirements.lock` içinde sabitlenmiştir. `.venv`, bağlantı bilgileri ve `.local` Git dışında tutulur.

## Yedekleme ve geri yükleme kontrolü

Proje kökündeki **Cevami-Yedekle.cmd** dosyasına çift tıklayın. Tam paket varsayılan olarak proje dışındaki `D:/workspace/02_projeler/HadisYedekleri` klasörüne, eş kopyası kullanıcı klasöründeki `C:/Users/apdmrl/HadisYedekleri` klasörüne yazılır. Bu bilgisayarda bunlar iki ayrı fiziksel disktir. Başka bilgisayarda `backup.ps1 -Primary ... -Mirror ...` ile farklı sürücüler seçilmelidir. Eski yedekler otomatik silinmez; yeni paket adları tarih ve rastgele kimlik taşır.

Kod, sabit bağımlılık dosyası, Git'in mevcut çalışma durumu, özgün kaynaklar ve çalışma şemasının tutarlı PostgreSQL kopyası dahildir. Gerçek bağlantı/parola dosyası, Python ortamı ve geçici günlükler dahil değildir. Ayar şablonuna kurtarma kurulumu için yeni bağlantı bilgisi girilir. Yedek sırasında proje dosyalarını düzenlemeyin veya çeviri/aktarım araçlarını çalıştırmayın.

Her paket ancak dosyalar yeni test alanına çıkarılıp özetleri doğrulandıktan ve PG kopyası ayrı, geçici bir veritabanına geri yüklenip bütün tablo sayıları karşılaştırıldıktan sonra yayımlanır. Sonuç `.receipt.json` kaydı ve arşivin SHA-256 özetidir. İkinci kopya ayrıca karşılaştırılır. Uygulama açık kalabilir; çalışma veritabanının üzerine geri yükleme yapılmaz.

Sonradan kontrol için, proje kökünden:

```powershell
./app/backup.ps1 -Verify 'D:/workspace/02_projeler/HadisYedekleri/cevami-TARIH-KIMLIK.zip'
```

Veritabanı geri yükleme denemesi yalnız bu kurulumun bağımsız `.local/backup-trust.json` sicilinde aynı SHA bulunan paket için çalışır. Tanınmayan pakette yalnız dosyalar denetlenir ve durum kodu2 döner; veritabanı komutları çalıştırılmaz. Bir arşivin kendi içindeki hash listesi tek başına güven kanıtı değildir.

**Acil kurtarma:** Sağlam diskteki arşiv ile ayrı saklanan `.receipt.json` kaydını koruyun. Yeni kurulumda SHA-256'yı bağımsız kayıttan karşılaştırıp `-TrustedSha256 '64-basamakli-onceden-kaydedilmis-ozet'` ekleyerek aynı izole deneme yapılabilir. Mevcut proje klasörüne veya çalışma DB'sine dosya açmayın/restore çalıştırmayın. Dosyalar `hadis_web.backup.extract_verified` ile yeni ve var olmayan bir hedef klasöre çıkarılabilir; Python ortamı `requirements.lock` ile yeniden hazırlanır. Kalıcı PostgreSQL kurtarması da yeni, boş bir veritabanında yapılır; dump `--no-owner --no-privileges` ile yeni role yüklenir ve ayar şablonu yeni bağlantıyla doldurulur. Otomatik mevcut veriyi ezme komutu bu araçta yoktur.

Bu iki yerel disk kopyasıdır; bilgisayar dışı yedek veya tam işletim sistemi görüntüsü değildir. [Kapsam ve doğrulama](../docs/24-dogrulanmis-yedekleme.md).

## Veri düzeni

- `../references/datasets/jawami3_alkalem/jawami.db`: 1.400 eserlik salt okunur kaynak. Uygulama kaynağa yazmaz.
- `../GK4.5/GK4.5/Data/Books.zip`: özgün cilt/sayfa atıfları.
- PostgreSQL `hadis`: 17 kaynak anlık görüntüsü,105.548 metin sürümü,17.766 eşleştirme adayı,8.795 sened,54.456 sıralı halka,1.634 kaynak ravi kaydı. Sened ve ravi aktarımı Buhârî pilotudur; metin adayları yedi eseri kapsar.
- `../references/turkish/fawazahmed0`, `../research/turkish-sources`, `../research/bukhari-review`: sürümlenmiş çeviri ve karşılaştırma girdileri. Uygulama bu proje klasöründeki referanslarla birlikte çalışır.

Kaynak anahtarları, GK iç numarası, metinde görünen numara ve cilt/sayfa ayrı alanlardır. Benzer hadisler birleştirilmez. 30000/30001/30002 kimlikleri şahıs değil, özgün yapısal işaretlerdir. Metin içi ravi bağlantıları kayıtlı sened yerine kullanılmaz.

## Araçlar

```powershell
.\.venv\Scripts\python.exe -m hadis_web.cli counts
.\.venv\Scripts\python.exe -m hadis_web.cli bootstrap
.\.venv\Scripts\python.exe -m hadis_web.cli localize
.\.venv\Scripts\python.exe -m hadis_web.cli localize-opinions
.\.venv\Scripts\python.exe -m hadis_web.cli localize-critic-names
.\.venv\Scripts\python.exe -m hadis_web.cli review-critic-names
.\.venv\Scripts\python.exe -m hadis_web.cli localize-terms
.\.venv\Scripts\python.exe -m hadis_web.cli review-fields
.\.venv\Scripts\python.exe -m hadis_web.cli review-opinions
.\.venv\Scripts\python.exe -m hadis_web.cli review-hadiths
.\.venv\Scripts\python.exe -m hadis_web.cli translation-queue
.\.venv\Scripts\python.exe -m pytest -q
node --test tests/ui_pagination.cjs
```

`bootstrap` kaynak özetlerini doğrular, şemayı kurar ve aynı pilotu çoğaltmadan aktarır. Büyük kaynak dosyası iki kez doğrulandığından entegrasyon testi yaklaşık iki dakika sürer. Testler geçici PostgreSQL şemalarında çalışır; çalışma şemasını silmez.

`localize` alan çevirisi şemasını ve sabit kaynak sürümüne bağlı ilk yedi ravi pilotunu yükler. Aynı pilotu tekrar yüklemek kayıt çoğaltmaz; incelenmiş kaynak kaydı veya snapshot değişmişse işlem durur.

`translation-queue` 1.631 gerçek Buhârî ravisinin 15.521 alan görevini kaynak kimliğiyle dışarı verir. Aranmamış alanlar bilinmeyen durumdadır; bu komut çeviri üretmez veya onaylamaz.

`localize-opinions` 50 kişinin 527 görüş kökünü yükler; ilk yedi ravinin 110 inceleme sürümü korunur. 527 aktif görüşün 481’i dil karşılaştırması, 46’sı açık kaynak/okuma sorunudur. Türkçe desteği ve asistan aktarımı ayrı gösterilir; tarihsel atıf teyidi veya uzman onayı değildir. [Önceki 123 görüş](../research/turkish-sources/v9-opinion-reviews.md), [50 sahâbî görüşü](../research/turkish-sources/companion-opinion-reviews.md), [üç sahâbî grubu](../research/turkish-sources/deferred-companions-research.md), [dört ravi grubu](../research/turkish-sources/high-frequency-review-evidence.md), [Abdullah b.Yûsuf’un 15 görüşü](../research/turkish-sources/abdullah-yusuf-review-evidence.md).

## Mimari ve kapsam

`review-hadiths` ilk üç Türkçe adayın 15 ayrı kaynak inceleme kararını, mevcut Arapça/Türkçe metin sürümlerine bağlı ve tek işlemde aktarır. Eksik üst senedler, karışık açıklamalar ve doğrulanmamış kitap künyeleri açık kalır. Okuyucuda **İnceleme ayrıntıları** görünür. [Ayrıntı](../docs/13-hadis-adayi-kaynak-incelemeleri.md).

Güncel devam: yedi eserde17.563farklı Arapça kayıt için17.766Türkçe kaynak adayı var; anlam/bütünlük incelemesi bekler. `localize-critic-names`65eski adı, `review-critic-names`on iki dosyadaki58sürümü yükler:120aktif kısa adın112’si karşılaştırılmış,8’i kaynak kimliği sorunu taşır. Aynı yazım farklı kaynakIDlerini birleştirmez. [Ad araştırması](../research/turkish-sources/critic-name-reviews.md), [önceki20ad](../research/turkish-sources/v9-opinion-reviews.md), [Halîlî ve açık Seyf kimliği](../research/turkish-sources/high-frequency-review-evidence.md), [son dört ad](../research/turkish-sources/abdullah-yusuf-review-evidence.md). Ortak sözlük55.149alanda otomatik tam eşleşme sunabilir; kişiye özel inceleme değildir. Bütün külliyatın çevirisi tamamlanmadı.

Kişiye bağlı incelemeyi asistan yürütür; kullanıcıya Arapça onay işi verilmez. `review-fields` 22 dosyada 100 kişi / 916 özel aktif alanı 938 sürümle yükler: 887 karşılaştırılmış, 29 açık kaynak/okuma sorunu. V8 ilk 76 alan pilotunun 30 düzeltmesini, V9 yeni 13 kişinin 125 alanını, V10 Âişe’nin sekiz kaynak künyesi düzeltmesini, V11 yeni 11 kişinin 104 alanını, V12 Saîd’in 10, V13 Sa‘d ve Sehl’in 18, V14 Şuayb/Sâlim/İsmâil/A‘rec’in 39, V15 Abdullah b.Yûsuf’un dokuz, V16 Yûnus/Yahyâ’nın 21, V17 Mûsâ/Ukayl’ın 19 alanını, V18 Ukayl’ın dokuz kaynak konumu düzeltmesini içerir; dosyalar doğrudan toplanmaz. Tam kayıt/hash/alan/dil/ebeveyn/künye bağı korunur. [Alan incelemeleri](../docs/12-asistan-alan-incelemeleri.md), [Türkçe tez](../research/turkish-sources/said-thesis-research.md), [son kaynak karşılaştırması](../research/turkish-sources/yunus-yahya-field-evidence.md).

FastAPI + sade HTML/CSS/JavaScript; SQLite kaynak erişimi; psycopg ile PostgreSQL çalışma katmanı. `GET /docs` API belgelerini açar. İlk API salt okunurdur; hesap ve inceleme yazma ekranı henüz yoktur. Arayüz tüm kaynak kütüphanesini okuyabilir. Türkçe metin adayları yedi esere genişletildi; sened aktarımı Buhârî pilotudur.

Türkçe adayların çevirmen/baskı bilgileri henüz doğrulanmadı. İlk sürümde onaylı çeviri veya uzman onayı yoktur. Kaynaktaki hükümler uygulamanın yeni bir değerlendirmesi değildir. Yerel geliştirme sunucusudur; genel erişime yayın yapılandırılmadı.

Sıradaki dilim: Arapça rivayet kapsamı, Türkçe anlam/bütünlük ve açıklama ayrımının kayıt bazında kaynaklarla incelenmesi; inceleme kanıtını gösteren çalışma ekranı.

Mûsâ ve Ukayl’ın 27 görüşü ve dört kısa ad eklendi; iki bozuk okuma ikinci Arapça şahit ile açıklanır, beş görüş ve bir ad sorunu açık kalır. [Kaynak karşılaştırması](../research/turkish-sources/musa-ukayl-opinion-evidence.md). Toplam1.737tarihsel/1.492aktif çeviri-inceleme kaydı; külliyat tamamlanmış değildir.

Ubeydullah’ın dokuz alanı ve beş görüşü eklendi;[akrabalık/kaynak sınırları](../research/turkish-sources/ubeydullah-utba-source-recon.md) açık gösterilir. Güncel toplam1.751tarihsel/1.506aktif kayıt; bütün hadislerin çevirisi tamamlanmış değildir.

Müsnedî’nin 11alanı/dokuzgörüşü/İbnMâkûlâ kısa adı eklendi;[velâ/ata/coğrafya sorunları](../research/turkish-sources/musnedi-source-recon.md) korunur. Güncel toplam1.772tarihsel/1.527aktif kayıt; bütün külliyatın çevirisi tamamlanmadı.

İbnCüreyc’in 11alanı/18görüşü/iki münekkit adı eklendi;[sekiz açık kaynak sorunu](../research/turkish-sources/ibn-cureyc-source-recon.md) gizlenmez. Güncel toplam1.803tarihsel/1.558aktif kayıt; tüm külliyatın çevirisi tamamlanmadı.

Âdem b.Ebû İyâs için11alan/10görüş/EbûDâvûd kısa adı eklendi.22yeni inceleme sürümünün ikisi önceki pilot alanlarını geçmiş bağıyla günceller; toplam1.825tarihsel/1.578aktif kayıt. [Seyahat–ikamet ayrımı](../research/turkish-sources/adem-ebu-iyas-source-recon.md) ve yayımlanmış Türkçe destek sınırları görünür; bütün külliyat tamamlanmadı.


### 3 Kasım 2026 — İbrâhim b. Sa‘d (GK823)
10 ravi alanı, 18 tam değerlendirme ve 2 münekkit adı: **30 yeni kaynak bağlı kayıt**, toplam **1.855 geçmiş / 1.608 aktif**. Dört değerlendirme (1268/1657/20/2769) ile iki ad kimliği belirsizliği açık tutuldu. Türkçe destek alanlarda 5 tam/4 kısmi/1 incelenen bölümde bulunamadı; görüşlerde 4 tam/8 kısmi/6 bulunamadı. Arapça metin ve sened sırası korunuyor.

Gerçek API üzerinde 30 kaydın metni, tam kaynak gövdesi, hash, durum ve kökeni doğrulandı; üç aktarım komutunun tekrarı aynı kimlikleri korudu. Önceki 1.825 kimlik, 15 hadis incelemesi, senedler ve eski JSON’lar değişmedi. Seçili 8 test geçti (223,19 sn); önceki tam 207 testlik sonuç bu ek gruptan öncedir, 211 testlik tam çalışma iddiası yoktur. Tek bağımsız son incelemede bulgu yok. Tarayıcıda 146_1071/sened71544/GK823, konuşmacı ayrımı ve okuma farkı görüldü; konsol hatasız.

Güncel: 972 aktif ravi alanı (943 karşılaştırılmış/29 sorun), 494 görüş (455/39), 118 münekkit adı (110/8), 24 terim (22 karşılaştırılmış/2 bekleyen). Alan inceleme sicili 23 dosya/101 kişi/926 aktif/948 sürüm. Kuyruk 1.631 kişi/15.521 görev: 965 karşılaştırılmış,48 sorun,2.170 terim,12.337 başlanmamış,1 aday. İlerleme sayacı terimler hariç1.584 aktif; tümüyle karşılaştırılmış hadis0, project_complete=false. Yayımlanmış Türkçe kaynakla asistan çevirisi ve uzman onayı ayrıdır. Sırada Şakīk b. Seleme GK3825.


### 3 Kasım 2026 — Şakīk b. Seleme (GK3825)
Yedi ravi alanı ve on tam değerlendirme için **17 yeni kayıt** aktarıldı; toplam **1.872 geçmiş / 1.625 aktif**. Muhadram kuşak bilgisi olarak açıklandı. Maîn’in olumsuz soru ifadesi korundu; Kâşif lafız farkı sorun olarak görünür. Alanlarda Türkçe destek6tam/1kısmi; görüşlerde0tam/7kısmi/3incelenen bölümde bulunamadı. Bu, uzman/tarihsel atıf onayı değildir.

Sekiz seçili test geçti (133,14sn); tek bağımsız incelemede engelleyici bulgu yok. Küçük ertelenen not: Merâsîl kaynak açıklamasında318numaralı Âişe’den işitme belirsizliği,321numaralı Ebû Bekir mürsel naklinden daha açık ayrılmalı;429görüşünün kendi gerekçesi bu ayrımı doğru yapıyor. İki gerçek aktarım komutu ve tekrarları EXIT0;17kaynak/APIbağlantısı iki kez doğrulandı, önceki1.855kimlik/15hadis incelemesi/hamkaynaklar/sened sırası/eskiJSONlar/4662507769tam geçmiş gövdeleri korundu. Web146_1073/sened71546kontrolü, kaynak farkı ekran görüntüsü ve hatasız konsol kaydı alındı. Önceki tam207test sonucu bu iki son gruptan öncedir;215testlik tam çalışma iddiası yok.

Güncel979aktif ravi alanı(950karşılaştırılmış/29sorun),504görüş(464/40),118münekkit adı(110/8),24terim(22karşılaştırılmış/2bekleyen). Alan sicili24dosya/102kişi/933aktif/955sürüm. Kuyruk1.631kişi/15.521görev:972karşılaştırılmış,49sorun,2.169terim,12.330başlanmamış,1aday. Terimler hariç ilerleme1.601aktif. Tümüyle karşılaştırılmış hadis0/project_complete=false. Sırada Ebû Nuaym/Fazl b.Dükeyn GK1548; onun verisi henüz aktarılmadı.


### 3 Kasım 2026 — Ebû Nuaym / Fazl b. Dükeyn (GK1548)
14ravi alanı,23tam kaynak değerlendirme kaydı ve2münekkit adı için **39 yeni kaynak bağlı kayıt** aktarıldı; toplam **1.911 geçmiş / 1.664 aktif**. Lakabın babaya ait olması ve6görüşteki atıf/özne sorunları görünür.431son cümlenin anlamı kesinleştirilemedi: Arapçası korunuyor, tam Türkçe çeviri iddiası yok. Alanlarda8tam/5kısmi/1incelenen bölümde bulunamadı; görüşlerde0tam/12kısmi/11bulunamadı Türkçe destek. İki yeni kısa adın Türkçe desteği mevcut. Arapça kaynak kayıtları/sened sırası/tarihler değiştirilmedi.

12seçili test kapsamı doğrulandı: ilk çalışmada11geçti/bir yalnız büyük-küçük harf varsayımı başarısızdı(251,65sn); düzeltilen tek test1,36sn’de geçti. Tek12geçişli çalışma veya tam219test iddiası yok. Tek bağımsız incelemede yeni bulgu yok. Üç gerçek aktarım komutu ve tekrarları EXIT0;39gerçekAPI/tamkaynak/hash/metin/durum/köken/uzman=false bağlantısı iki kez doğrulandı. Önceki1.872kimlik/15hadis incelemesi/kaynak kimlikleri/sened sırası/eskiJSONlar/4662507769tam geçmişleri korundu. UI146_1032/sened71488/GK1548:23/23görüş,14alan,431belirsizliği/2769konuşmacı/769tedlîs gerekçeleri görüldü; konsol hatasız, kendi geçici sekmesi kapatıldı. Uygulama8765’te açık.

Güncel993aktif ravi alanı(963karşılaştırılmış/30sorun),527görüş(481/46),120münekkit adı(112/8),24terim(22karşılaştırılmış/2bekleyen). Alan sicili25dosya/103kişi/947aktif/969sürüm. Kuyruk1.631kişi/15.521görev:985karşılaştırılmış,51sorun,2.167terim,12.317başlanmamış,1aday. Terimler hariç1.640aktif kayıt. Tümüyle karşılaştırılmış hadis0/project_complete=false. Önceki Şakīk Merâsîl kaynak açıklamasındaki küçük ifade netleştirmesi ertelenmiş/disclosed; kendi429gerekçesi ayrımı doğru yapıyor. Sıradaki Mansûr b.Mu‘temir GK7673henüz araştırma aşamasında.


### 3 Kasım 2026 — Mansûr b. Mu‘temir (GK7673)
9 ravi alanı, 16 tam değerlendirme kaydı ve 2 münekkit adı için **27 yeni kaynak bağlı kayıt** aktarıldı; toplam **1.938 geçmiş / 1.691 aktif**. On parçalı ad ve Attâb içeren alternatif soy ayrı korundu. 751’in meşâyih şartı yaşlılık anlatısıyla değiştirilmedi; 1708, Süfyân’ın anlattığı A‘meş tutumu olarak gösteriliyor. Alanlarda Türkçe destek 4 tam/4 kısmi/1 incelenen bölümde bulunamadı; görüşlerde 0 tam/15 kısmi/1 bulunamadı; iki kısa adın Türkçe desteği mevcut. Bunlar asistan dil karşılaştırmalarıdır; uzman veya tarihsel kimlik onayı değildir.

Sekiz test iki çalıştırmada kapsandı: iki yeni anlam testi 0,70 sn; iki yeni bütünleşme ve dört eski test 129,34 sn’de geçti. Tek sekizli veya tam223test çalışması iddiası yok; son tam207test sonucu dört sonraki gruptan öncedir. Kota nedeniyle yarım kalan aynı tek bağımsız son inceleme koltuğu tamamlandı; yeni bulgu yok. Üç gerçek aktarım komutu ve tekrarları EXIT0; 27 gerçek HTTP/tam kaynak/hash/metin/durum/köken/uzman=false bağı iki kez doğrulandı. Önceki1.911kimlik/15hadis incelemesi/kaynak kimlikleri/sened sırası/eskiJSONlar/4662507769tam gövdeleri korundu. UI146_104/sened71497/GK7673:9alan/16görüş,751ve1708kaynak açıklamaları,44ve1708adları görüldü; konsol hatasız; kendi test sekmesi kapatıldı. Docker durmuştu; mevcut container ve okuyucu yeniden açıldı, aktif sunucuPID20944/8765. Kullanıcı sekmeleri korundu.

Güncel1.002aktif ravi alanı(972karşılaştırılmış/30sorun),543görüş(497/46),122münekkit adı(114/8),24terim(22karşılaştırılmış/2bekleyen). Alan sicili26dosya/104kişi/956aktif/978sürüm. Kuyruk1.631kişi/15.521görev:995karşılaştırılmış,51sorun,2.166terim,12.308başlanmamış,1aday. Terimler hariç1.667aktif kayıt. Tümüyle karşılaştırılmış hadis0/project_complete=false. Önceki Şakīk/Merâsîl ortak kaynak açıklamasının küçük ifade netleştirmesi ertelenmiş kayıtta; kendi429gerekçesi doğru. Sırada İbrâhim en-Nehaî GK902/176sened tekrarı; onun verisi henüz aktarılmadı.


### 3 Kasım 2026 — İbrâhim en-Nehaî (GK902)
9 ravi alanı,9tam değerlendirme ve2yeni münekkit adı için20yeni kök; mevcut Mizzî adına açık üst kimlikli1sorun sürümü eklendi: **21 yeni sürüm**, toplam **1.959 geçmiş / 1.711 aktif**. Altı parçalı soy/Kays,bir gözün görmemesi,anne ve iki dayı,ham50/96/46tarihleri korundu.1011irsâl istisnası,1425üç ayrı işitme/idrak olumsuzluğu ve490bir grup imam/Beyhakī sınırı kaybolmadı.1385Mizzî749/742ve466EbûZür‘a kimlik çelişkileri sorun olarak görünür; eskiMizzîüst kaydı ve tam gövdesi değişmedi. Alanlarda Türkçe destek8tam/1kısmi; görüşlerde2tam/6kısmi/1incelenen bölümde bulunamadı;3kısa ad Türkçe destekli, Mizzî tarih/kimlik sorunu ayrı.

Sekiz test üç çalıştırmada kapsandı:2yeni anlam testi0,63sn; sonraki çalışma5geçti/1öngörülen sicil sayısı yanlıştı119,39sn. Mizzîüstü eski13inceleme dosyası dışındaki kök olduğundan14dosyada63başlık/63sürüm var,62değil; yalnız test/plan beklentisi düzeltildi, veri değişmedi. Başarısız tekbütünleşme testi21,23sn’de geçti. Teksekizli/tam227test iddiası yok; eski tam207sonucu beş sonraki gruptan öncedir. Tek bağımsız incelemede yeni bulgu yok. Kontrol betiğindeki991→1691sayı hatası dosya yazımı/aktarımdan önce yakalandı; doğru başlangıç kontrolü geçti.

Üç gerçek aktarım komutu ve tekrarları EXIT0;21gerçekHTTP/tam kaynak/hash/metin/durum/köken/uzman=false ve Mizzîüst bağı iki kez doğrulandı. Önceki1.938kimlik/15hadis incelemesi/kaynak kimlikleri/sened sırası/eskiJSONlar/4662507769veeski1385tam gövdeleri korundu. UI146_1027/sened71477/GK902:9alan9görüş/işitme olumsuzlukları/hadis sarrafı/Mizzî tarih sorunu/Beyhakī sınırı ve kaynaklar görüldü; konsol hatasız; kendi test sekmesi kapatıldı. İki ekran görüntüsü docs/screenshots altında. Kullanıcı sekmeleri ve8765sunucusu20944korundu.

Güncel1.011aktif ravi alanı(981karşılaştırılmış/30sorun),552görüş(504/48),124münekkit adı(115/9),24terim(22karşılaştırılmış/2bekleyen). Alan sicili27dosya/105kişi/965aktif/987sürüm; münekkit inceleme sicili14dosya/63başlık/63sürüm (Mizzîüstü sicil dışından gelir). Kuyruk1.631kişi/15.521görev:996karşılaştırılmış,60sorun,2.164terim,12.300başlanmamış,1aday. Terimler hariç1.687aktif kayıt. Tümüyle karşılaştırılmış hadis0/project_complete=false. Kaynak karşılaştırması uzman/tarihsel onay değildir. Önceki Şakīk/Merâsîl küçük ortak kaynak açıklaması notu ertelenmiş kayıtta. Sırada EbûÜsâme/Hammâd b.Üsâme GK2484/174sened tekrarı; asıl Arapça iki biyografi ve Türkçe tez/kitap bölümleri araştırıldı, henüz uygulama verisi yok.


### 3 Kasım 2026 — Ebû Üsâme / Hammâd b. Üsâme (GK2484)
9 ravi alanı ve 12 tam değerlendirme için **21 yeni kaynak bağlı kayıt** aktarıldı; toplam **1.980 geçmiş / 1.732 aktif**. Bazen tedlîs, son dönemde başkalarının kitaplarından rivayet, tedlîsi açıklama ve değerlendirmelerin bütün kitap atıfları korundu. Ahmed’in üç sözü, övgü ünlemi ve “neredeyse hata yapmazdı” sınırı açık; Türkçe tezdeki mutlak hata yokluğu ifadesi kopyalanmadı. Mevlâlık biyolojik akrabalığa çevrilmedi; ham121/201/80 ve kaynak işaretleri değişmedi. Alanlarda Türkçe destek8tam/1kısmi, görüşlerde0tam/10kısmi/2incelenen bölümde bulunamadı. Yeni münekkit adı eklenmedi; mevcut12adın tam kaynak bağı korundu.

Şahyar’ın yayınevi PDF’si arşivlendi: 2.baskı İstanbul2025; kapak/künye ve basılı161’deki bölüm703–709dipnotları görüldü. Hıdır2024tezinin basılı70/§3.1.2.13bölümü ve198–199dipnotları metin ve gerçek görüntüyle karşılaştırıldı. Bütün kitaplar veya özgün Takrîb/Hedyü’s-sârî/diğer kitap girişleri okunmuş sayılmadı. Kullanılan PDF ve metaveri dosyalarının hash’leri incelemeye bağlandı.

Sekiz test dört çalıştırmada kapsandı: ilk2testte1geçti/1yalnız harf duyarlılığı varsayımı başarısızdı0,78sn; başarısız testin0,82sn’lik tekrarında sonraki Türkçe eklenme varsayımı görüldü; iki test beklentisi düzeltildi, veri değişmedi. Aynı test0,64sn’de, diğer2yeni bütünleşme+4eski test122,68sn’de geçti. Teksekizli/tam231test iddiası yok; eski tam207sonucu altı sonraki gruptan öncedir. Kota ile yarım kalan aynı tek bağımsız son inceleme tamamlandı; yeni bulgu yok. İki gerçek aktarım komutu ve tekrarları EXIT0;21gerçekHTTP/tam kaynak/hash/metin/durum/köken/uzman=false ve12mevcutmünekkit bağı iki kez doğrulandı. Önceki1.959kimlik/15hadis incelemesi/kaynak kimlikleri/sened sırası/eskiJSONlar ve bütün münekkit geçmişi (eskiMizzîüstü ve sorun ardılı dahil) korundu.

UI146_1004/sened71446/GK2484:9alan12görüş,1011iki kitap+şartlar,751üç söz+anlam sınırı,diğer kitap atıfları/mevlâlık/kaynaklar görüldü. Konsol hatasız; ekran görüntüsü kaydedildi; kendi test sekmesi kapatıldı, kullanıcı sekmeleri ve8765sunucusu20944korundu. Güncel1.020aktif ravi alanı(990karşılaştırılmış/30sorun),564görüş(516/48),124münekkit adı(115/9),24terim(22karşılaştırılmış/2bekleyen). Alan sicili28dosya/106kişi/974aktif/996sürüm; görüş sicili22dosya/53kişi/564görüş. Kuyruk1.631kişi/15.521görev:1.006karşılaştırılmış,60sorun,2.162terim,12.292başlanmamış,1aday. Terimler hariç1.708aktif kayıt. Tümüyle karşılaştırılmış hadis0/project_complete=false; karşılaştırmalar uzman/tarihsel onay değildir. Önceki Şakīk/Merâsîl ortak kaynak açıklaması küçük notu ertelenmiş kayıtta.

Sırada Yahyâ b. Ebû Kesîr GK8208/165sened tekrarı. Tam kişi/14görüş, tamMizzî ve Türkçe tez§3.8.4.4basılı111 araştırıldı; TDV kendi maddesi yalnız başlık ve “güncellenmektedir” notu taşıyor. Kattân’ın Şu‘be’den nakliyle kendi sözünün ayrımı kaydedildi. 918Eyyûb adı için tamTDV12(1995)19ve dört tam münekkit/ilişkili kayıt arşivleri hazır. Arama sonucu yanlış kitaba giden130/444sayfası Süyûtî’nin el-Hâvî’si olarak teşhis edildi; Siyer kanıtı sayılmadı. Henüz8208uygulama verisi/planı/aktarımı yok.
# Güncel toplu çeviri pilotu — 4 Kasım 2026

İlk 1.000 Buhârî kaydı sınıflandırıldı; 50 kayıtta kaynak/eksik incelemesi var. Webde ilk 10'un 40 ayrılmış bölümü ve diğer 40'ın kaynak adayları gösteriliyor. **29 bölüm karşılaştırılmış, 48 bekliyor, 3 sorunlu; bütün rivayet gereği tamamlanan 0.** Künye bilinmiyorsa açık kalır; asistan ekleri yayımlanmış çeviriden ayrıdır. Aşağıdaki eski aşama notlarındaki sayılar tarihsel kalır; güncel sayım için [teslim raporu](../docs/14-toplu-ceviri-pilotu.md) ve [kapsam JSON'u](../research/corpus-review/translation-progress.json) kullanılır.

Örnek: <http://127.0.0.1:8765/?hadith=146_1> → **Türkçe çeviri**. Yeni salt okunur uç: `/api/hadith/{bhid}/components?language=tr`. Arapça düğmesi klavye ve tıklamayla da açılır. Veriler SQLite aslından doğrulanır, çalışma kayıtları PostgreSQL'de tutulur.

Proje kökünden:

```powershell
app/.venv/Scripts/python.exe research/scripts/build_translation_pilot.py --limit 1000
app/.venv/Scripts/python.exe research/scripts/import_hadith_component_batch.py app/hadis_web/data/hadith-component-batches/bukhari-first10-tr-v2.json
app/.venv/Scripts/python.exe research/scripts/import_hadith_component_batch.py app/hadis_web/data/hadith-component-batches/bukhari-first10-tr-v3.json
app/.venv/Scripts/python.exe research/scripts/import_hadith_component_batch.py app/hadis_web/data/hadith-component-batches/bukhari-11-50-triage-tr-v1.json
app/.venv/Scripts/python.exe research/scripts/verify_translation_pilot.py
app/.venv/Scripts/python.exe research/scripts/verify_translation_pilot.py --packet-manifest research/translation-pilot/v1/remaining40-manifest.json --output research/translation-pilot/v1/remaining40-live-verification.json
```

Tekrar aktarım yeni kayıt oluşturmaz. Doğrulayıcı için yerel sunucu ve bu uygulamadan önce kaydedilmiş başlangıç kanıtı gerekir; komutlar eksik bir kaynağa onay üretmez. Ayrıntılı sonuç ve kalan kapsam yukarıdaki teslim raporundadır.


## 11 Kasım — Eser içi arama ve numarayla geçiş
Aynı eserin son sonuçlarına dönülebilir; dönüş eski bekleyen numara isteğini iptal eder. Bulunamayan numarada açık metin/URL korunur; Latin/Arapça/Farsça rakamları desteklenir, kaynak numarasıyla iç sıra ayrıdır. Son13JS+32tarayıcısenaryosu başarılı; bu statik değişiklik için backend/audit yeniden koşulmadı. [Rapor](../docs/19-eser-ici-arama-ve-kayit-gecisi.md). Çeviri ve kişiselleştirme beklemede kalır.

## 12 Kasım — Arama ve ravi görüşlerinde yeniden deneme
Ana arama ve ek ravi görüşleri için 8 saniye sınırı, başarısız aynı sayfayı yeniden deneme ve mevcut kaynak metnini koruma eklendi. Arama metnini silmeyen Escape, güvenli klavye odağı ve mobilde sonuçların yanında hata/tekrar seçeneği var. [Ayrıntılar ve doğrulama sınırları](../docs/22-arama-ve-ravi-goruslerinde-yeniden-deneme.md). Çeviri üretimi ve kişiselleştirme beklemede kalır.
