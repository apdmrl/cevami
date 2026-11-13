const $ = selector => document.querySelector(selector);
const readingMode = document.body.dataset.page === 'hadith';
const state = { book: '146', hadith: null, bookOffset: 0, bookQuery: '', books: [], query: '', resultOffset: 0, sanadOffset: 0, job: 0, font: 29, translation: 'tr', loadingHadith: null };
let comparison = false;
let componentViews = [];
let copyAttempt = 0;
let printContext = null;
let coreRequest = null;
let translationSummary = {tr:{status:'idle',count:0,components:0},en:{status:'idle',count:0,components:0}};
let sanadComparison = {bhid:null, rows:[], total:0, open:false};
const number = n => new Intl.NumberFormat('tr-TR').format(n);
const comparisonNames = { same_arabic_tokens_without_diacritics: 'Harekesiz Arapça kelimeler aynı', same_tokens_after_orthographic_folding: 'Yazım eşitlemesiyle aynı kelimeler', equal_concatenated_letters_but_word_boundaries_differ: 'Kelime sınırı farkı var' };
const fieldLabels = {opinion:'Değerlendirme metni',critic:'Kaynakta kayıtlı isim',name:'Tam ad',shohra:'Tanınan adı',badeel:'Diğer adı',konya:'Künye',lakab:'Lakap',san3a:'Görev / meslek',wasf:'Nitelik',mazhab:'Mezhep',nasab:'Nisbe / soy',wasf_rotba:'Kaynak ravi değerlendirmesi',baladekama:'Yaşadığı yerler — kaynak kaydı',baladwafa:'Vefat yeri — kaynak kaydı',mawaaly:'Mevlâ ilişkisi',karaba:'Akrabalık',critic_opinions:'Cerh ve ta‘dîl görüşleri',biography_note:'Kısa Türkçe kaynak özeti'};
const renderingNames = {translation:'Alan çevirisi',transliteration:'Türkçe yazım',name_form:'Türkçe ad biçimi',source_summary:'Asistanın kaynak özeti · tam biyografi çevirisi değildir'};
const originNames = {assistant_source_corrected_rendering:'Kaynak yazımı açıklanarak yapılan asistan aktarımı',assistant_reviewed_translation:'Arapça aslıyla karşılaştırılmış asistan aktarımı',controlled_vocabulary:'Kaynaklı sözlükten otomatik terim aktarımı',assistant_translation:'Asistanın Arapçadan çeviri taslağı',assistant_draft:'Asistan aktarımı · inceleme bekliyor',source_supported_rendering:'Türkçe kaynakla desteklenen aktarım · birebir alıntı değil',assistant_source_summary:'Asistanın kısa kaynak özeti',unknown:'Çeviri kökeni ayrıca doğrulanacak'};
const availabilityNames = {terminology_only:'Türkçe kaynak yalnız terim/yer adı karşılığını destekler; kişi bilgisi ayrıca doğrulanacak.',not_found_in_checked_sources:'İncelenen kaynaklarda yayımlanmış Türkçe karşılık bulunamadı. Bu, hiçbir çevirisinin bulunmadığı anlamına gelmez.',candidate_unverified:'Türkçe kaynak adayı var; alan ve kaynak güvenilirliği kontrol edilecek.',candidate_inaccessible:'Türkçe kaynak adayı bulundu; ilgili tam metne erişilemedi.',partial_support:'Türkçe kaynak alanın yalnız bir kısmını destekliyor.',unknown:'Türkçe karşılığın kaynak durumu henüz belirlenmedi.',source_support_found:'Türkçe kaynak dayanağı mevcut.'};
const supportNames = {arabic_source_comparison:'Arapça karşılaştırma kaynağı; yayımlanmış Türkçe çeviri değildir.',identity_only:'Bu kaynak kişinin kimlik bilgisi için kullanıldı.',supports_full_field:'Bu kaynağın desteği: alanın tamamı.',supports_part_of_field:'Bu kaynağın desteği: yalnız alanın bir kısmı.',not_found:'Kontrol edilen kaynak: bu görüşün/alanın tam Türkçe karşılığı bulunamadı.',terminology_only:'Bu kaynak yalnız terim karşılığını destekliyor.',source_based_summary:'Bu kaynak kısa özetin dayanağıdır.'};

function localizedText(data, field) {
  const rows = data?.fields?.[field] || [];
  if (!rows.length || rows.some(row => row.status !== 'source_compared' || row.rendering_kind === 'source_summary')) return '';
  const texts = [...new Set(rows.map(row => row.text))];
  return texts.length === 1 ? texts[0] : '';
}
function controlledText(data, field) {
  if (data?.conflicting_fields?.includes(field)) return '';
  const rows = data?.fields?.[field] || [];
  return rows.length === 1 && rows[0].translation_origin === 'controlled_vocabulary' &&
    rows[0].actor_kind === 'automated_check' && rows[0].status === 'needs_review' ? rows[0].text : '';
}
function sourceLink(ref) {
  try {
    const url = new URL(ref.url);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return element('span', '', ref.title);
    const link = element('a', '', ref.title + ' ↗');
    link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
    link.title = ref.locator; return link;
  } catch { return element('span', '', ref.title); }
}

function renderLocalization(profile, content, entityType = 'narrator') {
  const data = profile.localization;
  const section = element('section', 'localization-section');
  const heading = element('h3', '', entityType === 'critic_opinion' ? 'Görüşün Türkçe aktarımı' : 'Türkçe bilgiler'); section.append(heading);
  section.append(element('p', 'localization-intro', entityType === 'critic_opinion' ? 'Arapça değerlendirme kaynakta kaydedildiği biçimde korunur.' : 'Arapça kayıt korunur. Çeviri, Türkçe ad yazımı ve kaynak özeti ayrı gösterilir.'));
  if (!data?.available) section.append(element('p', 'empty-state', 'Türkçe çalışma verisine şu anda erişilemiyor.'));
  for (const [field, claims] of Object.entries(data?.fields || {})) {
    for (const claim of claims) {
      const card = element('section', 'localized-field');
      const label = element('h4', '', fieldLabels[field] || field); card.append(label);
      const status = claim.status === 'source_compared' ? 'Asistan kaynak karşılaştırması' : claim.status === 'problem_detected' ? 'İnceleme sorunu var' : 'Asistan incelemesi bekliyor';
      const actorStatus = claim.expert_reviewed ? 'Uzman incelemesi' : status;
      if (data.conflicting_fields.includes(field)) card.append(element('p', 'translation-notice', 'Bu alan için birden fazla farklı Türkçe karşılık var; seçim yapılmadı.'));
      const text = element('p', 'localized-text', claim.text); text.lang = data.language; text.dir = 'ltr'; card.append(text);
      if (profile[field] && entityType === 'narrator') { const original = element('p', 'field-original', profile[field]); original.lang = 'ar'; original.dir = 'rtl'; card.append(original); }
      const sources = element('div', 'field-sources');
      for (const ref of claim.sources) {
        const line = element('p'); line.append(sourceLink(ref), document.createTextNode(' · ' + ref.locator));
        if (supportNames[ref.support_scope]) line.append(element('span','source-support',' ' + supportNames[ref.support_scope]));
        if (ref.evidence_note) line.append(element('span','source-support',' ' + ref.evidence_note));
        sources.append(line);
      }
      const evidence = element('details', 'field-evidence'); evidence.append(element('summary', '', 'Kaynak ve karşılaştırma gerekçesi'), element('p', '', claim.rationale), sources);
      evidence.append(element('p', 'field-status', `${renderingNames[claim.rendering_kind] || claim.rendering_kind} · ${actorStatus}`),
        element('p', 'field-status', originNames[claim.translation_origin] || originNames.unknown),
        element('p', 'localization-intro', availabilityNames[claim.turkish_availability] || availabilityNames.unknown));
      if (claim.status === 'problem_detected') card.append(element('p','translation-notice','Bu alanda kaynak farkı var; karşılaştırma gerekçesini inceleyin.'));
      card.append(evidence); section.append(card);
    }
  }
  if (data?.pending_fields?.length) {
    const pending = element('details','field-evidence');
    pending.append(element('summary','','Eksik Türkçe bilgiler'),element('p', 'pending-fields', 'Kaynak kontrolü bekleyen alanlar: ' + data.pending_fields.map(field => fieldLabels[field] || field).join(', ') + '.'));
    section.append(pending);
  }
  section.append(element('p', 'translation-notice', entityType === 'critic_opinion' ? 'Bu aktarım uygulamanın yeni ravi hükmü değildir. Kaynak atfı, sözün asıl sahibine ilişkin yeni bir tespit sayılmaz.' : 'Kısa kaynak özetleri tam biyografi çevirisi değildir. Çevrilmemiş alanlar Arapça kaynak kaydında kalır.'));
  content.append(section);
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function button(text, className, action) {
  const node = element('button', className, text);
  node.type = 'button';
  node.addEventListener('click', action);
  return node;
}
async function get(url, signal) {
  const response = await fetch(url, { headers: { Accept: 'application/json' }, signal });
  let data;
  try { data = await response.json(); }
  catch { const failure = new Error('Kaynak yanıtı okunamadı. Yeniden deneyebilirsiniz.'); failure.status = response.status; throw failure; }
  if (!response.ok) { const failure = new Error(typeof data.detail === 'string' ? data.detail : 'Kayıt bilgileri alınamadı.'); failure.status = response.status; throw failure; }
  return data;
}
function error(message) { $('#error-banner').textContent = message; $('#error-banner').classList.toggle('hidden', !message); }
let toastTimer;
function toast(message) { $('#toast').textContent = message; $('#toast').classList.add('visible'); clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').classList.remove('visible'), 2500); }
function fact(list, label, value, arabic = true) {
  const group = element('div');
  group.append(element('dt', '', label));
  const description = element('dd', arabic ? '' : 'latin', value || 'Belirtilmemiş');
  if (arabic && value) { description.lang = 'ar'; description.dir = 'rtl'; }
  group.append(description); list.append(group);
}

let bookListJob = 0, pendingBooks = null, failedBooks = null;
let bookSelectionJob = 0, selectedBookRequest = null;
async function loadBooks(append = false) {
  if (append && pendingBooks) return;
  const job = append ? bookListJob : ++bookListJob;
  const request = {job, append, query:state.bookQuery, offset:append ? state.bookOffset + 60 : 0};
  pendingBooks = request; failedBooks = null;
  $('#retry-books').hidden = true; $('#book-status').textContent = 'Eserler yükleniyor…';
  $('#book-list').setAttribute('aria-busy','true'); $('#more-books').disabled = true;
  if (!append) { state.books = []; state.bookOffset = 0; $('#book-list').replaceChildren(); $('#more-books').classList.add('hidden'); $('#library-count').textContent = '…'; }
  try {
  const data = await getAuxiliary(`/api/books?limit=60&offset=${request.offset}&q=${encodeURIComponent(request.query)}`);
  if (job !== bookListJob) return;
  $('#library-count').textContent = `${number(data.total)} eser`;
  state.books.push(...data.items);
  for (const book of data.items) {
    const node = button('', 'book-button' + (book.book_id === state.book ? ' active' : ''), () => selectBook(book.book_id));
    node.dataset.bookId = book.book_id;
    if (book.book_id === state.book) node.setAttribute('aria-current', 'true');
    node.append(element('span', 'book-icon', '▤'));
    const copy = element('span', 'book-copy');
    const name = element('strong', '', book.name); name.lang = 'ar';
    copy.append(name, element('small', 'author-line', book.author), element('small', '', `${number(book.hadith_count || 0)} metin kaydı`));
    node.append(copy); $('#book-list').append(node);
  }
  state.bookOffset = request.offset;
  $('#more-books').classList.toggle('hidden', request.offset + data.items.length >= data.total);
  $('#book-status').textContent = data.total ? '' : 'Bu aramaya uygun eser bulunamadı.';
  } catch {
    if (job !== bookListJob) return;
    failedBooks = request;
    $('#book-status').textContent = append ? 'Diğer eserler yüklenemedi. Gösterilen liste korunuyor.' : 'Eserler yüklenemedi. Yeniden deneyebilirsiniz.';
    $('#retry-books').hidden = false;
  } finally {
    if (pendingBooks === request) {
      pendingBooks = null; $('#book-list').setAttribute('aria-busy','false'); $('#more-books').disabled = false;
    }
  }
}
async function selectBook(bookId) {
  cancelRecordJump();
  const job = ++bookSelectionJob;
  selectedBookRequest = bookId; $('#retry-book-selection').hidden = true;
  $('#book-selection-status').textContent = 'Eserin ilk kaydı yükleniyor…';
  try {
    const data = await getAuxiliary(`/api/books/${bookId}/hadiths?limit=1`);
    if (job !== bookSelectionJob) return;
    $('#book-selection-status').textContent = '';
    if (!data.items.length) { $('#book-selection-status').textContent = 'Bu eserde görüntülenebilir numaralı metin bulunmuyor.'; return; }
    setLibraryOpen(false,{cancelSelection:false});
    $('#search-results').classList.add('hidden');
    await loadHadith(data.items[0].bhid);
  } catch {
    if (job !== bookSelectionJob) return;
    $('#book-selection-status').textContent = 'Eserin ilk kaydı yüklenemedi. Yeniden deneyebilirsiniz.';
    $('#retry-book-selection').hidden = false;
  }
}

function viewLocation(bhid,research,translation=state.translation,withHash=true) {
  const params = new URLSearchParams();
  if (research) params.set('hadith',bhid);
  const from = new URLSearchParams(location.search);
  for (const key of ['q','language','book_id']) if (from.has(key)) params.set(key,from.get(key));
  if (translation === 'en') params.set('translation','en');
  const hash = withHash && ['#arabic-text','#translations-panel','#sanad-list','#source-details'].includes(location.hash) ? location.hash : '';
  return (research ? '/research' : `/hadith/${encodeURIComponent(bhid)}`) + (params.size ? '?'+params : '') + hash;
}
function updateViewLink() {
  if (!state.hadith) return;
  $('#open-research').href = viewLocation(state.hadith.bhid,readingMode);
  $('#open-research').textContent = readingMode ? 'Araştırma alanına geç ↗' : 'Sade okumaya geç ↗';
}
function updateSearchLink() {
  const from = new URLSearchParams(location.search);
  const params = new URLSearchParams();
  for (const key of ['q','language','book_id']) if (from.has(key)) params.set(key,from.get(key));
  $('#back-search').href = '/' + (params.size ? '?' + params : '');
}
function renderHadith(data) {
  state.hadith = data; state.book = data.book.book_id;
  document.title = `${data.book.name} · ${data.internal_number} — Cevâmi`;
  $('#book-title').textContent = data.book.name;
  $('#book-title-tr').textContent = data.book.name_tr || '';
  $('#book-title-tr').hidden = !data.book.name_tr;
  $('#breadcrumb-book').textContent = data.book.name;
  $('#book-author').textContent = data.book.author;
  $('#hadith-number').textContent = data.internal_number;
  $('#jump-number').value = data.internal_number;
  $('#identity-short').textContent = `GK ${data.bhid}`;
  $('#identity-details').replaceChildren();
  fact($('#identity-details'),'GK kayıt kimliği',data.bhid,false);
  fact($('#identity-details'),'İç kayıt sırası',String(data.internal_number),false);
  fact($('#identity-details'),'Metinde görünen numara',data.display_number,false);
  fact($('#identity-details'),'Kaynak indeksindeki atıf',data.citation.hadith_reference_raw,false);
  fact($('#identity-details'),'Kaynak cilt / sayfa gösterimi',data.citation.page_reference_raw,false);
  $('#record-position').textContent = `${number(data.book.hadith_count)} metin kaydı`;
  updateViewLink();
  updateSearchLink();
  $('#previous-record').disabled = !data.previous;
  $('#next-record').disabled = !data.next;
  $('#arabic-text').replaceChildren();
  for (const run of data.arabic.runs) {
    if (run.kind === 'narrator') {
      const link = button(run.text, 'inline-narrator', () => showNarrator(run.narrator_id));
      link.setAttribute('aria-label', `Ravi bilgisi: ${run.text.trim()}`);
      $('#arabic-text').append(link);
    } else { $('#arabic-text').append(document.createTextNode(run.text)); }
  }
  $('#reference-book').textContent = data.book.name;
  $('#reference-details').replaceChildren();
  fact($('#reference-details'), 'Müellif', data.book.author);
  fact($('#reference-details'), 'Yayınevi', data.book.publisher);
  fact($('#reference-details'), 'Baskı / yıl', [data.book.edition, data.book.year_pub].filter(Boolean).join(' · '));
  fact($('#reference-details'), 'Muhakkik', data.book.editor);
  fact($('#reference-details'), 'Cilt / sayfa — kaynak gösterimi', data.citation.page_reference_raw, false);
  $('#record-details').replaceChildren();
  fact($('#record-details'), 'Kaynak kayıt kimliği', data.bhid, false);
  fact($('#record-details'), 'Metinde görünen numara', data.display_number, false);
  fact($('#record-details'), 'Hadis indeksi atfı', data.citation.hadith_reference_raw, false);
  fact($('#record-details'), 'Kaynak hükmü', data.source_judgement?.label);
  if (data.source_judgement) fact($('#record-details'), 'Kaynak hükmü — Türkçe karşılığı', data.source_judgement.label_tr, false);
  fact($('#record-details'), 'Kayıtlı sened', number(data.sanad_count), false);
  $('#raw-text').textContent = data.arabic.raw_text;
  $('#short-citation').replaceChildren(document.createTextNode(data.book.name));
  if (data.citation.page_reference_raw) {
    const page = element('bdi','citation-page',data.citation.page_reference_raw.trim()); page.dir = 'ltr';
    $('#short-citation').append(document.createTextNode('، '),page);
  }
  for (const node of document.querySelectorAll('.book-button')) {
    const active = node.dataset.bookId === state.book;
    node.classList.toggle('active', active);
    active ? node.setAttribute('aria-current', 'true') : node.removeAttribute('aria-current');
  }
}
let auxiliaryAttempt = 0;
let readerInteraction = 0;
async function getWithDeadline(url,controller,ms) {
  if (controller.signal.aborted) throw controller.signal.reason || new Error('İstek iptal edildi.');
  let rejectRequest;
  const interrupted = new Promise((_,reject)=>{ rejectRequest = reject; });
  const onAbort = ()=>rejectRequest(controller.signal.reason || new Error('İstek iptal edildi.'));
  controller.signal.addEventListener('abort',onAbort,{once:true});
  const timer = setTimeout(()=>{
    const failure = new Error('Kaynak zamanında yanıt vermedi. Yeniden deneyebilirsiniz.');
    failure.name = 'TimeoutError'; controller.abort(failure);
  },ms);
  try { return await Promise.race([get(url,controller.signal),interrupted]); }
  finally { clearTimeout(timer); controller.signal.removeEventListener('abort',onAbort); }
}
function getAuxiliary(url) { return getWithDeadline(url,new AbortController(),8000); }
function updateTranslationIndicator() {
  const data = translationSummary[state.translation], language = state.translation === 'en' ? 'İngilizce' : 'Türkçe';
  const label = data.components ? `${number(data.components)} bölüm`
    : data.status === 'ready' ? `${number(data.count)} kaynak` : data.status === 'unavailable' ? '—' : '…';
  $('#translation-count').textContent = label;
  $('#translation-count').title = data.components ? `${language}: ${number(data.components)} kaynaklı bölüm; ek kaynak kaydı: ${number(data.count)}. Bütünlük durumu bölümlerde açıklanır.`
    : data.status === 'ready' ? `${language} kaynak kaydı sayısı. Anlam veya bütünlük onayı değildir.`
    : data.status === 'unavailable' ? `${language} kaynak bilgisine şu anda erişilemiyor.` : `${language} kaynak bilgisi yükleniyor.`;
}
function resetTranslationSummary() {
  translationSummary = {tr:{status:'idle',count:0,components:0},en:{status:'idle',count:0,components:0}};
  updateTranslationIndicator();
}
function readerVisible(visible) {
  for (const selector of ['#hadith-paper','.sanad-section','#source-details','#section-navigation','.reader-topline','#open-research']) $(selector).hidden = !visible;
}
async function loadAuxiliary(bhid,job) {
  resetSanadComparison();
  const attempt = ++auxiliaryAttempt;
  const current = () => job === state.job && bhid === state.hadith?.bhid && attempt === auxiliaryAttempt;
  const retry = () => { if (current()) loadAuxiliary(bhid,job); };
  const failures = [];
  $('#auxiliary-status').hidden = false; $('#auxiliary-status').textContent = 'Çeviri ve sened bilgileri yükleniyor…';
  $('#retry-auxiliary').hidden = true;
  $('#sanad-list').replaceChildren(element('p','empty-state','Sened bilgileri yükleniyor…'));
  $('#sanad-count').textContent = '…'; $('#sanad-top-count').textContent = '…';
  $('#more-sanads').classList.add('hidden'); $('#more-sanads').disabled = true;
  $('#more-sanads').setAttribute('aria-busy','false');
  $('#expand-sanads').disabled = true;
  $('#sanad-page-error').hidden = true; $('#sanad-page-error').textContent = '';
  $('#translations-content').replaceChildren(element('p','empty-state','Türkçe çeviri bilgileri yükleniyor…'));
  $('#components-content').replaceChildren(); $('#components-section').hidden = true;
  resetComparison();
  translationSummary.tr = {status:'loading',count:0,components:0}; updateTranslationIndicator();
  const sanads = getAuxiliary(`/api/hadith/${encodeURIComponent(bhid)}/sanads`).then(data=>{
    if (!current()) return;
    state.sanadOffset = 0; renderSanads(data); $('#more-sanads').disabled = false;
  }).catch(()=>{
    if (!current()) return;
    failures.push('sanads');
    $('#sanad-list').replaceChildren(element('p','empty-state','Sened verisi yüklenemedi. Arapça metindeki ravi bağlantıları kullanılabilir.'),button('Senedleri yeniden yükle','text-button',retry));
    $('#sanad-count').textContent = '—'; $('#sanad-top-count').textContent = '—';
  });
  const translations = Promise.allSettled([
    getAuxiliary(`/api/hadith/${encodeURIComponent(bhid)}/translations`),
    getAuxiliary(`/api/hadith/${encodeURIComponent(bhid)}/components`)
  ]).then(results=>{
    if (!current()) return;
    const tr = results[0].status === 'fulfilled' ? results[0].value : {available:false,items:[],total:0,message:'Türkçe çeviri verisi yüklenemedi. Yeniden deneyebilirsiniz.'};
    const components = results[1].status === 'fulfilled' ? results[1].value : {available:false,items:[],hadith_core_complete:false,blockers:['working_data_unavailable']};
    if (tr.available === false || components.available === false) failures.push('translations');
    renderTranslations(tr,components.items?.some(item=>item.translation_text)); renderComponents(components);
    if (tr.available === false || components.available === false) $('#translations-content').append(button('Türkçe veriyi yeniden yükle','text-button',retry));
  }).catch(()=>{
    if (!current()) return;
    failures.push('translations');
    $('#translations-content').replaceChildren(element('p','empty-state','Çeviri verisi şu anda gösterilemiyor. Yeniden deneyebilirsiniz.'),button('Türkçe veriyi yeniden yükle','text-button',retry));
  });
  await Promise.allSettled([sanads,translations]);
  if (!current()) return;
  $('#auxiliary-status').hidden = !failures.length;
  $('#auxiliary-status').textContent = failures.length ? 'Bazı ek bilgilere şu anda erişilemiyor. Arapça asıl metin ve kaynak künyesi okunabilir.' : '';
  $('#retry-auxiliary').hidden = !failures.length;
}
async function loadHadith(bhid, push = true, prepared = null) {
  coreRequest?.abort();
  const controller = prepared ? null : new AbortController(); coreRequest = controller;
  updateSearchLink();
  dismissNarrator();
  resetSanadComparison();
  const differentBook = bhid.split('_')[0] !== state.book;
  closeResearchResults(differentBook,false);
  if (differentBook) { state.query = ''; $('#query').value = ''; }
  cancelRecordJump();
  ++bookSelectionJob;
  $('#book-selection-status').textContent = ''; $('#retry-book-selection').hidden = true;
  const job = ++state.job;
  resetTranslationSummary();
  const interaction = readerInteraction;
  state.loadingHadith = bhid; state.hadith = null; state.lastHadithRequest = {bhid,push};
  clearCopyFallback();
  clearPrintView();
  readerVisible(false); $('#record-loading').hidden = false;
  $('#record-loading').textContent = `${bhid} kaydı yükleniyor…`;
  $('#retry-hadith').hidden = true; $('#auxiliary-status').hidden = true; $('#retry-auxiliary').hidden = true;
  document.title = 'Kayıt yükleniyor — Cevâmi';
  error(''); $('#hadith-paper').setAttribute('aria-busy', 'true');
  try {
    const data = prepared || await getWithDeadline(`/api/hadith/${encodeURIComponent(bhid)}`,controller,10000);
    if (job !== state.job) return;
    if (coreRequest === controller) coreRequest = null;
    renderHadith(data); state.sanadOffset = 0;
    $('#english-content').replaceChildren();
    state.loadingHadith = null; readerVisible(true); $('#record-loading').hidden = true;
    $('#hadith-paper').setAttribute('aria-busy','false');
    const auxiliaries = loadAuxiliary(bhid,job);
    if (readingMode) {
      $('#translations-panel').classList.remove('hidden');
      $('#translation-toggle').setAttribute('aria-expanded','true');
    }
    const language = new URLSearchParams(location.search).get('translation') === 'en' ? 'en' : 'tr';
    if (push) history.pushState({ bhid }, '', viewLocation(bhid,!readingMode,language,false));
    const targetHash = location.hash;
    const selected = selectTranslation(language);
    if (targetHash) {
      await Promise.all([selected,auxiliaries]);
      if (job === state.job && location.hash === targetHash && interaction === readerInteraction) navigateSection(targetHash,false);
    }
  } catch (e) {
    if (job !== state.job) return;
    readerVisible(false); $('#record-loading').hidden = true;
    document.title = 'Kayıt yüklenemedi — Cevâmi';
    error(`${bhid}: ${e.name === 'TimeoutError' ? 'Kaynak kaydı zamanında yanıt vermedi. Yeniden deneyebilirsiniz.' : e.status ? e.message : 'Kaynak kaydı şu anda yüklenemiyor. Yeniden deneyebilirsiniz.'}`); $('#retry-hadith').hidden = e.status === 404;
  }
  finally {
    if (coreRequest === controller) coreRequest = null;
    if (job === state.job) { state.loadingHadith = null; $('#hadith-paper').setAttribute('aria-busy', 'false'); }
  }
}

function setComparison(active) {
  comparison = active;
  $('#components-content').classList.toggle('comparison-active',active);
  $('#compare-components').setAttribute('aria-pressed',String(active));
  $('#compare-components').textContent = active ? 'Normal okumaya dön' : 'Arapça ve Türkçeyi karşılaştır';
  for (const sync of componentViews) sync();
}
function resetComparison() {
  componentViews = []; setComparison(false); $('#compare-toolbar').hidden = true;
}
function renderComponents(data) {
  translationSummary.tr.components = data.available === false ? 0 : (data.items || []).filter(item=>item.translation_text).length;
  updateTranslationIndicator();
  const content = $('#components-content');
  content.replaceChildren(); resetComparison();
  const blockers = (data.blockers || []).filter(reason => reason !== 'no_component_review');
  const unavailable = data.available === false || blockers.length > 0;
  $('#components-section').hidden = !data.items?.length && !unavailable;
  if (!data.items?.length) {
    if (unavailable) {
      const reasons = {
        source_binding_invalid: 'Türkçe bölümlerin kaynak bağı doğrulanamadı. Yanlış bir eşleştirme gösterilmemesi için bölümler saklandı.',
        multiple_source_versions_require_review: 'Bu kayıt için birden çok kaynak sürümü var; Türkçe bölümler yeniden karşılaştırılmayı bekliyor.',
        working_data_unavailable: 'Türkçe bölüm incelemelerine şu anda erişilemiyor.'
      };
      content.append(element('h3', 'components-heading', 'Türkçe bölüm incelemesi'));
      const messages = [...new Set(blockers.map(reason => reasons[reason] || 'Türkçe bölüm incelemesi bu kayıt için henüz gösterilemiyor.'))];
      if (!messages.length) messages.push(data.message || reasons.working_data_unavailable);
      content.append(element('p', 'empty-state', messages.join(' ') + ' Arapça asıl metin okunabilir.'));
    }
    return;
  }
  if (data.items.some(item => item.translation_text)) {
    updateTranslationIndicator();
  }
  $('#compare-toolbar').hidden = !data.items.some(item=>item.arabic_text && item.translation_text && item.status !== 'problem_detected');
  content.append(element('h3', 'components-heading', 'Kaynaklarıyla Türkçe bölümler'));
  if (!data.hadith_core_complete) content.append(element('p', 'component-overview', 'Çeviri kısmi olabilir. Bölümlerin kaynağı ve kapsamı açılır ayrıntılardadır.'));
  const kinds = {matn:'Rivayet metni', isnad:'Sened', notes:'Kaynak notu / tahric', unclassified:'Ayrımı incelenen bölüm'};
  const origins = {assistant_translation:'Arapçadan asistan çevirisi', reused_rendering:'Önceki kaynak karşılaştırmasına bağlı aktarım', unresolved:'Türkçe karşılığı inceleme bekliyor'};
  for (const item of data.items) {
    const card = element('article', 'translation-component');
    card.append(element('h4', '', kinds[item.kind] || 'Kaynak bölümü'));
    const origin = item.origin === 'published_translation'
      ? (item.bibliography_ok ? 'Türkçe kaynak aktarımı' : 'Türkçe kaynak adayı · çevirmen ve baskı doğrulanmadı')
      : (origins[item.origin] || 'Çeviri kökeni inceleniyor');
    const status = item.status === 'source_compared' ? 'Asistan kaynak karşılaştırması yapıldı'
      : item.status === 'problem_detected' ? 'Kaynak karşılaştırmasında sorun saptandı' : 'Kaynak karşılaştırması bekliyor';
    const translation = element('p', 'component-translation', item.translation_text || 'Bu bölümün Türkçe karşılığı henüz bulunmuyor.');
    translation.lang = 'tr';
    const pair = element('div','component-pair');
    const rendering = element('div','component-rendering'); rendering.lang = 'tr'; rendering.dir = 'ltr';
    rendering.append(element('p','component-language','Türkçe'));
    if (item.status === 'problem_detected') {
      rendering.append(element('p','translation-notice','Bu bölümün çevirisinde kaynakla uyuşmayan ifadeler var. Kaynak metni ayrıntılarda gösterilir.'));
      const original = element('details','problem-text'); original.append(element('summary','','Sorunlu kaynak çevirisi'),translation); rendering.append(original);
    } else rendering.append(translation);
    pair.append(rendering);
    if (item.arabic_text) {
      const box = element('div', 'component-arabic-preview');
      box.append(element('p','component-language','Arapça asıl'));
      const arabic = element('p', 'component-arabic-text', item.arabic_text);
      arabic.id = `component-arabic-${item.id}`; arabic.lang = 'ar'; arabic.dir = 'rtl'; arabic.hidden = true;
      let pinned = false, hovered = false, focused = false;
      const sync = () => {
        const shown = comparison || pinned || hovered || focused;
        arabic.hidden = !shown; toggle.hidden = comparison; toggle.setAttribute('aria-expanded',String(shown));
      };
      const toggle = button('Arapça aslı', 'component-arabic-toggle', () => { pinned = !pinned; sync(); });
      toggle.setAttribute('aria-controls', arabic.id); toggle.setAttribute('aria-expanded', 'false');
      box.addEventListener('mouseenter', () => { hovered = true; sync(); });
      box.addEventListener('mouseleave', () => { hovered = false; sync(); });
      box.addEventListener('focusin', () => { focused = true; sync(); });
      box.addEventListener('focusout', event => { focused = box.contains(event.relatedTarget); sync(); });
      box.append(toggle, arabic); pair.append(box); componentViews.push(sync);
    } else pair.append(element('p','component-original-missing','Bu bölüm için ayrı bir Arapça alıntı bulunmuyor.'));
    card.append(pair);
    const evidence = element('details', 'component-evidence');
    evidence.append(element('summary', '', 'Kaynak ve inceleme gerekçesi'));
    evidence.append(element('p', 'component-origin', origin), element('p', 'component-status', status + (item.bibliography_ok ? '' : ' · Künye incelemesi açık')));
    const references = new Map();
    const reviewLabels = {arabic_relation:'Arapça kaynak bağı',translation_meaning:'Anlam',translation_completeness:'Kapsama göre bütünlük',notes_separation:'Metin / not ayrımı',reuse_context:'Yeni bağlam kontrolü'};
    const outcomeLabels = {pass:'Karşılaştırıldı',pending:'Bekliyor',fail:'Sorun var',not_applicable:'Uygulanmıyor'};
    const decisions = element('dl', 'component-decisions');
    const rationales = new Set();
    for (const review of item.reviews || []) {
      const decision = element('div');
      decision.append(element('dt', '', reviewLabels[review.dimension] || 'Kaynak incelemesi'),
        element('dd', 'decision-' + review.outcome, outcomeLabels[review.outcome] || 'Bekliyor'));
      decisions.append(decision); rationales.add(review.rationale);
      for (const ref of review.sources || []) references.set(`${ref.url}|${ref.locator}`, ref);
    }
    evidence.append(decisions);
    for (const rationale of rationales) evidence.append(element('p', '', rationale));
    for (const ref of item.bibliography?.sources || []) references.set(`${ref.url}|${ref.locator}`, ref);
    for (const ref of item.source_search?.sources || []) references.set(`${ref.url}|${ref.locator}`, ref);
    if (item.source_search?.missing_scope) evidence.append(element('p', '', item.source_search.missing_scope));
    for (const ref of references.values()) {
      const line = element('p'); line.append(sourceLink(ref), document.createTextNode(' · ' + ref.locator)); evidence.append(line);
    }
    card.append(evidence); content.append(card);
  }
}

function resetSanadComparison() {
  sanadComparison = {bhid:null, rows:[], total:0, open:false};
  $('#sanad-comparison').hidden = true;
  $('#compare-sanads').disabled = true;
  $('#compare-sanads').textContent = 'Senedleri karşılaştır';
  $('#compare-sanads').setAttribute('aria-expanded','false');
  for (const selector of ['#sanad-compare-first','#sanad-compare-second','#sanad-comparison-result']) $(selector).replaceChildren();
  $('#sanad-comparison-status').textContent = ''; $('#sanad-comparison-coverage').textContent = '';
}
function updateSanadComparison(data, append) {
  const bhid = state.hadith?.bhid;
  if (!append || sanadComparison.bhid !== bhid) resetSanadComparison();
  sanadComparison.bhid = bhid;
  sanadComparison.total = data.total;
  const known = new Set(sanadComparison.rows.map(row=>String(row.sanad_id)));
  for (const row of data.items) {
    if ((row.bhid && row.bhid !== bhid) || known.has(String(row.sanad_id))) continue;
    sanadComparison.rows.push(row); known.add(String(row.sanad_id));
  }
  const rows = sanadComparison.rows;
  for (const [selector,index] of [['#sanad-compare-first',0],['#sanad-compare-second',1]]) {
    const select = $(selector), previous = select.value;
    select.replaceChildren();
    for (const row of rows) {
      const option = element('option','',`Sened ${row.sanad_id} · ${row.members.length} kaynak öğesi`);
      option.value = String(row.sanad_id); select.append(option);
    }
    select.value = rows.some(row=>String(row.sanad_id) === previous) ? previous : String(rows[index]?.sanad_id ?? '');
  }
  $('#compare-sanads').disabled = rows.length < 2;
  $('#sanad-comparison-coverage').textContent = `Yüklenen ${number(rows.length)} / kayıtta ${number(data.total)} sened. Seçimler yüklenen senedlerle sınırlıdır.`;
  // A later source page extends choices without replacing focused column nodes.
}
function sanadComparisonColumn(row, shared) {
  const column = element('section','sanad-comparison-column');
  column.setAttribute('aria-label',`Sened ${row.sanad_id}`);
  column.append(element('h4','',`Sened ${row.sanad_id}`));
  const grade = element('p','sanad-compare-grade');
  const original = element('span','',row.source_judgement.label); original.lang = 'ar'; original.dir = 'rtl';
  grade.append(element('span','','Kaynak hükmü: '),original,element('span','',row.source_judgement.label_tr));
  column.append(grade);
  const list = element('ol','sanad-compare-members'); list.dir = 'rtl';
  list.setAttribute('aria-label',`Sened ${row.sanad_id}, kaynakta kayıtlı sıra`);
  for (const member of row.members) {
    const item = element('li');
    const person = member.kind === 'narrator';
    const entry = person ? button('','sanad-compare-person',()=>showNarrator(member.source_id,
      {bhid:sanadComparison.bhid,sanadId:row.sanad_id,position:member.position,members:row.members})) : element('div','sanad-compare-marker');
    entry.append(element('span','narrator-source-position',`${member.position + 1}. sıra`));
    const name = element('span','sanad-compare-name',member.label || 'Kaynakta ravi kimliği yok');
    name.lang = member.label ? 'ar' : 'tr'; entry.append(name);
    if (person) {
      const nameTr = localizedText(member.localization,'shohra');
      if (nameTr) entry.append(element('small','sanad-compare-name-tr',nameTr));
      const common = shared.has(String(member.source_id));
      const identity = `${common ? 'Ortak kaynak ravi kimliği' : 'Kaynak ravi kimliği'}: ${member.source_id}`;
      entry.append(element('small',common ? 'sanad-shared-key' : 'sanad-source-key',identity));
      entry.setAttribute('aria-label',`Ravi bilgisi: ${member.label}, sened ${row.sanad_id}, ${member.position + 1}. sıra. ${identity}`);
      if (common) entry.dataset.shared = 'true';
    } else {
      if (member.kind === 'structural_marker' && member.label_tr) entry.append(element('small','',member.label_tr));
      entry.append(element('small','',member.kind === 'structural_marker' ? 'Yapısal işaret' : 'Çözümlenemeyen kaynak halkası'));
    }
    item.append(entry); list.append(item);
  }
  column.append(list); return column;
}
function renderSanadComparison() {
  const result = $('#sanad-comparison-result'); result.replaceChildren();
  if (!sanadComparison.open || sanadComparison.bhid !== state.hadith?.bhid) return;
  const rows = ['#sanad-compare-first','#sanad-compare-second'].map(selector=>sanadComparison.rows.find(row=>String(row.sanad_id) === $(selector).value));
  if (!rows[0] || !rows[1] || rows[0].sanad_id === rows[1].sanad_id) {
    $('#sanad-comparison-status').textContent = 'İki farklı sened seçin.'; return;
  }
  const ids = row=>new Set(row.members.filter(member=>member.kind === 'narrator' && member.source_id != null).map(member=>String(member.source_id)));
  const first = ids(rows[0]), second = ids(rows[1]);
  const shared = new Set([...first].filter(id=>second.has(id)));
  $('#sanad-comparison-status').textContent = `Ortak kaynak ravi kimliği: ${number(shared.size)}. Her liste kendi kaynak sırasını korur.`;
  result.append(...rows.map(row=>sanadComparisonColumn(row,shared)));
}
function toggleSanadComparison() {
  if (sanadComparison.rows.length < 2 || sanadComparison.bhid !== state.hadith?.bhid) return;
  sanadComparison.open = !sanadComparison.open;
  $('#sanad-comparison').hidden = !sanadComparison.open;
  $('#compare-sanads').setAttribute('aria-expanded',String(sanadComparison.open));
  $('#compare-sanads').textContent = sanadComparison.open ? 'Karşılaştırmayı kapat' : 'Senedleri karşılaştır';
  if (sanadComparison.open) { renderSanadComparison(); $('#sanad-compare-first').focus(); }
  else $('#compare-sanads').focus();
}
function renderSanads(data, append = false) {
  updateSanadComparison(data,append);
  $('#sanad-count').textContent = number(data.total);
  $('#sanad-top-count').textContent = number(data.total);
  if (!append) $('#sanad-list').replaceChildren();
  $('#expand-sanads').disabled = !data.total;
  if (!data.total) $('#sanad-list').append(element('p', 'empty-state', 'Bu kayıt için kaynak veritabanında sened kaydı bulunmuyor. Metin içindeki ravi bağlantıları ayrıca görülebilir.'));
  for (const row of data.items) {
    const details = element('details', 'sanad-item');
    details.open = !append && data.items.indexOf(row) === 0;
    const summary = element('summary');
    const label = element('span', 'sanad-label');
    label.append(element('span', 'chain-icon', '⌘'), element('span', '', `Sened ${row.sanad_id}`), element('small', '', `${row.members.length} sıralı kaynak öğesi`));
    const grade = element('span', 'judgement' + (row.source_judgement.code > 1 ? ' weak' : row.source_judgement.code < 0 ? ' unspecified' : ''));
    const arabicGrade = element('span', '', row.source_judgement.label); arabicGrade.lang = 'ar';
    grade.append(arabicGrade, element('small', '', row.source_judgement.label_tr));
    grade.title = row.source_judgement.translation_note;
    summary.append(label, grade); details.append(summary);
    const chain = element('ol', 'chain'); chain.dir = 'rtl';
    chain.setAttribute('aria-label', `Sened ${row.sanad_id}, kaynakta kayıtlı sıra`);
    for (const member of row.members) {
      const item = element('li');
      const node = member.kind === 'narrator' ? button('', 'chain-node', () => showNarrator(member.source_id,
        {bhid:row.bhid || state.hadith?.bhid, sanadId:row.sanad_id, position:member.position, members:row.members})) : element('div', 'chain-node marker');
      node.append(element('span', 'position-number', `${member.position + 1}. sıra`));
      const name = element('span', 'person-name', member.label || 'Kaynakta ravi kimliği yok'); name.lang = member.label ? 'ar' : 'tr';
      node.append(name);
      if (member.kind === 'structural_marker') {
        node.append(element('span', 'person-name-tr', member.label_tr), element('small', '', 'Yapısal işaret'));
        node.title = 'Terim kaynağı: ' + member.translation_source;
      } else if (member.kind === 'unresolved') {
        node.append(element('small','','Çözümlenemeyen kaynak halkası'));
        node.title = 'Kaynak satırında kişi kimliği çözümlenemedi; ravi eklenmedi veya tamamlanmadı.';
      } else {
        const turkishName = localizedText(member.localization, 'shohra');
        if (turkishName) node.append(element('span', 'person-name-tr', turkishName));
        if (member.source_rank) { const rank = element('small', '', member.source_rank); rank.lang = 'ar'; node.append(rank); }
        const termRank = controlledText(member.localization, 'wasf_rotba');
        const turkishRank = localizedText(member.localization, 'wasf_rotba') || termRank;
        if (turkishRank) node.append(element('small', 'rank-tr', turkishRank));
        if (termRank) { const note = element('small', 'rank-tr rank-derivation', 'Terim sözlüğü'); note.title = 'Otomatik terim karşılığı; kişiye özgü kaynak incelemesi bekliyor.'; node.append(note); }
      }
      if (member.kind === 'narrator') node.setAttribute('aria-label', `Ravi bilgisi: ${member.label}, zincirde ${member.position + 1}. sıra`);
      item.append(node); chain.append(item);
    }
    details.append(chain, element('p', 'chain-source', 'Sıra ve hüküm: Cevâmiu’l-Kelim 4.5 · 1. öğeden itibaren kaynak sırası, Arapça zincir sağdan sola okunur. Yapısal işaretler kişi değildir.'));
    $('#sanad-list').append(details);
  }
  $('#more-sanads').classList.toggle('hidden', data.offset + data.items.length >= data.total);
  if (data.offset + data.items.length < data.total) $('#more-sanads').textContent = `Diğer senedleri göster (${number(data.total - data.offset - data.items.length)} kaldı)`;
}

function renderTranslationReview(review, card) {
  if (!Array.isArray(review.events) || !review.events.length) return;
  const dimensions = {arabic_relation:'Arapça kaynak bağı', translation_meaning:'Matn anlamı',
    translation_completeness:'Çeviri bütünlüğü', notes_separation:'Metin ve açıklama ayrımı', bibliography:'Çevirmen ve baskı künyesi'};
  const outcomes = {pass:'Karşılaştırıldı', fail:'Sorun saptandı', pending:'İnceleme açık', not_applicable:'Uygulanamaz'};
  const actors = {assistant_source_review:'Asistan kaynak incelemesi', expert_review:'Uzman incelemesi', automated_check:'Otomatik kontrol'};
  const details = element('details', 'translation-review');
  details.append(element('summary', '', 'İnceleme ayrıntıları'));
  for (const event of review.events) {
    const section = element('div', 'translation-review-event');
    section.append(element('h4', '', `${dimensions[event.dimension] || event.dimension} · ${outcomes[event.outcome] || event.outcome}`));
    section.append(element('p', 'translation-provenance', actors[event.actor_kind] || 'Kaynak incelemesi'));
    section.append(element('p', '', event.rationale));
    const sources = element('ul', 'translation-review-sources');
    for (const ref of event.sources || []) {
      const item = element('li');
      if (typeof ref === 'string') item.textContent = ref;
      else if (ref && typeof ref === 'object') {
        let url;
        try { const parsed = new URL(ref.url); if (['http:', 'https:'].includes(parsed.protocol) && !parsed.username && !parsed.password) url = parsed.href; } catch {}
        if (url) {
          const link = element('a', '', ref.title || ref.url);
          link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; item.append(link);
        } else item.append(document.createTextNode(`${ref.title || 'Kaynak'} · ${ref.url || ''}`));
        item.append(document.createTextNode(` · ${ref.locator || ''}${ref.accessed_on ? ' · Erişim: ' + ref.accessed_on : ''}`));
      }
      sources.append(item);
    }
    section.append(sources); details.append(section);
  }
  card.append(details);
}

function readingView(row,key) {
  const original = row[key] || '', view = row.presentation;
  if (view && typeof view.text === 'string' && typeof view.navigation_note === 'string' &&
    (view.navigation_note ? original.endsWith(view.navigation_note) && original.slice(0,original.length-view.navigation_note.length).trimEnd() === view.text : view.text === original)) return view;
  return {text:original,navigation_note:''};
}
function appendSourceNavigation(card,details,view,original) {
  if (!view.navigation_note) return;
  card.append(element('p','source-navigation-hint','Özgün kaydın eski gezinme notu kaynak ayrıntısında korunur.'));
  details.append(element('p','source-navigation-label','Kaynağın eski gezinme notu'),element('blockquote','source-navigation-note',view.navigation_note));
  const raw = element('details','original-source-text');
  raw.append(element('summary','','Özgün kaynak metni'),element('p','original-source-body',original));
  details.append(raw);
}
function renderTranslations(data, hasComponentTranslation = false) {
  translationSummary.tr.status = data.available === false ? 'unavailable' : 'ready';
  translationSummary.tr.count = data.total || 0; updateTranslationIndicator();
  $('#translations-content').replaceChildren();
  if (!data.available || !data.items.length) {
    const message = hasComponentTranslation
      ? 'Türkçe bölümler yukarıda kaynaklarıyla gösterilir. ' + (data.available ? 'Ek eşleştirme listesinde başka aday bulunmuyor.' : (data.message || 'Ek çeviri adaylarına şu anda erişilemiyor.'))
      : (data.message || 'Bu rivayete bağlı Türkçe çeviri adayı henüz bulunmuyor. Arapça asıl metin ve kaynak bilgileri korunur.');
    $('#translations-content').append(element('p', 'empty-state', message));
    return;
  }
  let container = $('#translations-content');
  if (hasComponentTranslation) {
    const alternatives = element('details','translation-alternatives');
    alternatives.append(element('summary','','Diğer kaynak çevirileri')); container.append(alternatives); container = alternatives;
  } else container.append(element('p', 'translation-notice', 'Kaynak çevirisinin bu rivayetin tamamını kapsadığı henüz doğrulanmadı.'));
  for (const row of data.items) {
    const card = element('article', 'translation-card');
    const heading = element('div', 'translation-status');
    const status = row.review.status === 'source_compared' ? 'Kaynak karşılaştırması yapıldı' : row.review.status === 'problem_detected' ? 'İnceleme sorunu var' : row.review.events?.length ? 'İnceleme açık' : 'Asistan incelemesi bekliyor';
    heading.append(element('span', 'pending-badge', status), element('span', '', `Türkçe kaynak kaydı ${row.source_key}`));
    const check = row.evidence?.v2?.arabic_comparison;
    if (check) heading.append(element('span', '', comparisonNames[check] || 'Karşılaştırma adayı'));
    const view = readingView(row,'display_text');
    const text = element('p', 'translation-text', view.text || 'Bu kaynak kaydında ayrı bir okuma metni bulunmuyor; özgün metin kaynak ayrıntısındadır.'); text.lang = 'tr';
    const provenance = element('p', 'translation-provenance');
    provenance.append(document.createTextNode(`Kaynak: ${row.provider} · ${row.namespace.replace('fawaz:', '')} · Çevirmen/baskı doğrulaması bekliyor. `));
    const link = element('a', '', 'Kaynak sürümü ↗');
    link.href = `https://github.com/fawazahmed0/hadith-api/tree/${encodeURIComponent(row.revision)}`;
    link.target = '_blank'; link.rel = 'noopener noreferrer'; provenance.append(link);
    const sourceDetails = element('details','translation-source-details');
    sourceDetails.append(element('summary','','Çevirinin kaynağı ve kapsamı'),heading,provenance);
    if ((row.evidence?.v2?.translation_flags || []).includes('contains_editorial_or_navigation_text')) {
      card.append(element('p','translation-notice', row.review.dimensions?.notes_separation === 'fail'
        ? 'Kaynak incelemesinde hadis metnine karışmış açıklama veya gezinme yazısı saptandı. Ayrıntılar aşağıda; kaynak metni korunuyor.'
        : 'Kaynak kaydı, çeviriyle birlikte tahriç veya şerh içerebilir; bu bölümlerin ayrımı inceleme bekliyor.'));
    }
    if (row.review.status === 'problem_detected') {
      card.append(element('p','translation-notice','Bu çeviride kaynakla uyuşmayan veya metne karışmış ifadeler var. Ana çeviri olarak kullanılmamalı.'));
      const disputed = element('details','problem-text'); disputed.append(element('summary','','Sorunlu kaynak çevirisi'),text); card.append(disputed);
    } else card.append(text);
    appendSourceNavigation(card,sourceDetails,view,row.display_text);
    renderTranslationReview(row.review, sourceDetails); card.append(sourceDetails); container.append(card);
  }
}

async function selectTranslation(language) {
  state.translation = language;
  const english = language === 'en';
  $('#turkish-content').hidden = english; $('#english-content').hidden = !english;
  $('#read-tr').setAttribute('aria-pressed',String(!english)); $('#read-en').setAttribute('aria-pressed',String(english));
  const params = new URLSearchParams(location.search);
  if (english) params.set('translation','en'); else params.delete('translation');
  history.replaceState(null,'',location.pathname + (params.size?'?'+params:'') + location.hash);
  updateViewLink();
  updateTranslationIndicator();
  if (!english || !state.hadith || (state.loadingHadith && state.loadingHadith !== state.hadith.bhid) || $('#english-content').children.length) return;
  const content = $('#english-content'), job = state.job, bhid = state.hadith.bhid;
  const retry = () => {
    if (job !== state.job || bhid !== state.hadith?.bhid || translationSummary.en.status !== 'unavailable') return;
    content.replaceChildren(); return selectTranslation('en');
  };
  translationSummary.en = {status:'loading',count:0,components:0}; updateTranslationIndicator();
  content.append(element('p','empty-state','Kaynak çevirisi yükleniyor…'));
  try {
    const data = await getAuxiliary(`/api/hadith/${encodeURIComponent(bhid)}/search-translations?language=en`);
    if (job !== state.job || bhid !== state.hadith?.bhid) return;
    translationSummary.en = {status:data.available === false ? 'unavailable' : 'ready',count:data.items.length,components:0};
    updateTranslationIndicator();
    content.replaceChildren();
    if (!data.available || !data.items.length) {
      content.append(element('p','empty-state',data.available === false
        ? 'İngilizce kaynak dizinine şu anda erişilemiyor. Bu, çevirinin bulunmadığı anlamına gelmez.'
        : 'Bu kayda bağlı İngilizce kaynak çevirisi bulunmuyor. Arapça asıl metin okunabilir.'));
      if (data.available === false) content.append(button('Yeniden dene','text-button',retry));
      return;
    }
    content.append(element('p','translation-notice','Kaynak çevirisi. Bu rivayetin bütün bölümlerini kapsadığı henüz doğrulanmadı.'));
    for (const row of data.items) {
      const card = element('article','translation-card');
      const text = element('p','translation-text',row.text); text.lang = 'en'; text.dir = 'ltr';
      const evidence = element('details','translation-source-details');
      evidence.append(element('summary','','Çevirinin kaynağı ve kapsamı'),
        sourceLink({url:row.source_url,title:`Hadith API · ${row.edition} · ${row.source_key}`,locator:row.revision}),
        element('p','translation-provenance','Arapça kaynak metninin tam kelime eşleşmesi üzerinden ilişkilendirilmiştir. Anlam ve kapsam onayı değildir. Kaynağın çevirmen ve baskı künyesi ayrıca doğrulanmamıştır.'));
      card.append(text,evidence); content.append(card);
    }
  } catch (e) {
    if (job !== state.job || bhid !== state.hadith?.bhid) return;
    translationSummary.en = {status:'unavailable',count:0,components:0}; updateTranslationIndicator();
    content.replaceChildren(element('p','empty-state','İngilizce kaynak çevirisine şu anda erişilemiyor.'),
      button('Yeniden dene','text-button',retry));
  }
}

let narratorJob = 0, narratorContext = null;
function narratorNeighbor(context, step) {
  if (!context || ![-1,1].includes(step)) return null;
  let index = context.members.findIndex(member => member.position === context.position);
  for (index += step; index >= 0 && index < context.members.length; index += step) {
    if (context.members[index].kind === 'narrator') return context.members[index];
  }
  return null;
}
function setNarratorContext(id, context) {
  const valid = context?.bhid === state.hadith?.bhid && Array.isArray(context?.members) &&
    context.members.some(member => member.kind === 'narrator' && member.position === context.position && String(member.source_id) === String(id));
  narratorContext = valid ? {...context, members:context.members.slice()} : null;
  $('#narrator-context').hidden = !narratorContext;
  $('#narrator-context-label').textContent = narratorContext
    ? `Sened ${context.sanadId} · ${context.position + 1}. sıra · GK ${context.bhid}` : '';
  $('#previous-narrator').disabled = !narratorNeighbor(narratorContext, -1);
  $('#next-narrator').disabled = !narratorNeighbor(narratorContext, 1);
}
function dismissNarrator() {
  ++narratorJob; setNarratorContext(null, null);
  if ($('#narrator-dialog').open) $('#narrator-dialog').close();
}
function navigateNarratorChain(step) {
  const context = narratorContext, member = narratorNeighbor(context, step);
  if (!member || context.bhid !== state.hadith?.bhid) return;
  const control = $(step > 0 ? '#next-narrator' : '#previous-narrator');
  const hadFocus = document.activeElement === control;
  const request = showNarrator(member.source_id, {...context, position:member.position});
  if (control.disabled && hadFocus) $('#narrator-content').focus({preventScroll:true});
  return request;
}
function narratorChainPanel(context) {
  const panel = element('details', 'narrator-chain-panel');
  panel.append(element('summary', '', 'Kaynak zincirinin tamamı'));
  const list = element('ol', 'narrator-context-members'); list.dir = 'rtl';
  list.setAttribute('aria-label', `Sened ${context.sanadId}, kaynakta kayıtlı sıra`);
  for (const member of context.members) {
    const item = element('li');
    const name = member.label || 'Çözümlenemeyen kaynak halkası';
    let node;
    if (member.kind === 'narrator') {
      node = button('', 'narrator-context-person', () => {
        const request = showNarrator(member.source_id, {...context, position:member.position});
        $('#narrator-content').focus({preventScroll:true});
        return request;
      });
      if (member.position === context.position) node.setAttribute('aria-current', 'true');
      node.setAttribute('aria-label', `${member.position + 1}. sıra: ${name}`);
    } else node = element('div', 'narrator-context-marker');
    const label = element('span', '', name); label.lang = member.label ? 'ar' : 'tr';
    node.append(element('span', 'narrator-source-position', `${member.position + 1}. sıra`), label);
    if (member.kind === 'structural_marker') node.append(element('small', '', member.label_tr || 'Yapısal işaret'));
    if (member.kind === 'unresolved' && member.label) node.append(element('small', '', 'Çözümlenemeyen kaynak halkası'));
    item.append(node); list.append(item);
  }
  panel.append(list, element('p', 'muted', 'Kaynak sırası aynen gösterilir. Yapısal ve çözümlenemeyen öğeler kişi değildir; sıra, doğrudan işitme veya öğretmenlik hükmü sayılmaz.'));
  return panel;
}
function renderOpinions(profile, content, job) {
  if (!profile.opinions_total) return;
  const heading = element('h3', '', 'Kaynakta kayıtlı cerh ve ta‘dîl görüşleri');
  const count = element('p', 'localization-intro');
  const list = element('div', 'opinion-list');
  const pageStatus = element('p','opinion-page-status');
  pageStatus.id = `opinion-page-status-${job}`; pageStatus.setAttribute('role','status'); pageStatus.hidden = true;
  let offset = profile.opinions.length;
  let total = profile.opinions_total;
  let busy = false;
  function append(rows) {
    for (const opinion of rows) {
      const card = element('section', 'opinion');
      card.append(element('p', 'field-status', 'Kaynakta kayıtlı isim · kimlik: ' + opinion.alem_id));
      const critic = element('strong', '', opinion.critic || opinion.alem_id); critic.lang = 'ar'; critic.dir = 'rtl';
      const original = element('p', 'opinion-original', opinion.opinion); original.lang = 'ar'; original.dir = 'rtl';
      card.append(critic, original);
      if (opinion.source_occurrences > 1) card.append(element('small', '', `Kaynakta aynı içerikli ${opinion.source_occurrences} satır bulunuyor.`));
      renderLocalization(opinion, card, 'critic_opinion');
      list.append(card);
    }
  }
  function update() {
    count.textContent = `${number(offset)} / ${number(total)} farklı görüş gösteriliyor.`;
    more.hidden = offset >= total;
  }
  const more = button('Diğer görüşleri yükle', 'secondary-button opinion-more', async () => {
    if (busy || offset >= total) return;
    if (document.activeElement === more) $('#narrator-content').focus({preventScroll:true});
    busy = true; more.disabled = true; more.setAttribute('aria-busy','true');
    more.textContent = 'Görüşler yükleniyor…'; pageStatus.hidden = true; pageStatus.textContent = '';
    try {
      const page = await getAuxiliary(`/api/narrator/${profile.id}/opinions?offset=${offset}`);
      if (job !== narratorJob || !$('#narrator-dialog').open) return;
      append(page.items); offset += page.items.length; total = page.total; update();
    } catch {
      if (job === narratorJob && $('#narrator-dialog').open) {
        pageStatus.textContent = 'Diğer görüşler yüklenemedi. Gösterilen kaynak görüşleri korunuyor; aynı düğmeyle yeniden deneyebilirsiniz.';
        pageStatus.hidden = false;
      }
    } finally {
      busy = false;
      if (job === narratorJob) { more.disabled = false; more.setAttribute('aria-busy','false'); more.textContent = 'Diğer görüşleri yükle'; }
    }
  });
  more.setAttribute('aria-busy','false'); more.setAttribute('aria-describedby',pageStatus.id);
  append(profile.opinions);
  content.append(heading, count, list, pageStatus, more); update();
}
async function showNarrator(id, context = null) {
  const job = ++narratorJob;
  setNarratorContext(id, context);
  const selectedContext = narratorContext;
  const content = $('#narrator-content');
  const moveFocus = document.activeElement !== content && content.contains(document.activeElement);
  content.replaceChildren();
  if (selectedContext) content.append(narratorChainPanel(selectedContext));
  const profileBody = element('div', 'narrator-profile');
  profileBody.setAttribute('aria-busy','true');
  profileBody.append(element('h2', 'narrator-name', '…')); content.append(profileBody);
  content.scrollTop = 0;
  if (!$('#narrator-dialog').open) $('#narrator-dialog').showModal();
  else if (moveFocus) content.focus({preventScroll:true});
  try {
    const data = await getAuxiliary(`/api/narrator/${id}`);
    if (job !== narratorJob || !$('#narrator-dialog').open) return;
    if (String(data.id) !== String(id)) throw new Error('Unexpected narrator');
    profileBody.replaceChildren();
    const title = element('h2', 'narrator-name', data.shohra || data.name); title.id = 'narrator-title'; title.lang = 'ar'; title.dir = 'rtl';
    const name = element('p', 'narrator-long-name', data.name); name.lang = 'ar'; name.dir = 'rtl';
    profileBody.append(title, name);
    const turkishName = localizedText(data.localization, 'shohra');
    if (turkishName) profileBody.append(element('p', 'narrator-name-tr', turkishName));
    if (data.wasf_rotba) profileBody.append(element('p', 'narrator-rank', data.wasf_rotba));
    const facts = element('dl', 'narrator-facts');
    fact(facts, 'Künye', data.konya); fact(facts, 'Vefat — Hicrî kaynak kaydı', data.death_year);
    fact(facts, 'Yaşadığı yer', data.baladekama); fact(facts, 'Tabaka — kaynak kaydı', data.tabaka ? String(data.tabaka) : null);
    profileBody.append(facts);
    renderLocalization(data, profileBody);
    renderOpinions(data, profileBody, job);
    profileBody.append(element('p', 'dialog-source', `Kaynak: ${data.source} · Ravi kimliği: ${data.id}. Hüküm ve ifadeler kaynak veriden aktarılmıştır.`));
  } catch {
    if (job !== narratorJob || !$('#narrator-dialog').open) return;
    profileBody.replaceChildren(element('p', 'empty-state', 'Ravi bilgilerine şu anda erişilemiyor. Aynı kaydı yeniden deneyebilirsiniz.'),
      button('Ravi kaydını yeniden yükle', 'secondary-button', () => {
        if (job === narratorJob && $('#narrator-dialog').open) return showNarrator(id, selectedContext);
      }));
  } finally {
    if (job === narratorJob && $('#narrator-dialog').open) profileBody.setAttribute('aria-busy','false');
  }
}

let searchJob = 0, pendingSearch = null, failedSearch = null, searchContext = null;
let jumpJob = 0;
function cancelRecordJump() {
  ++jumpJob;
  $('#jump-status').textContent = '';
  $('#jump-number').removeAttribute('aria-invalid'); $('#query').removeAttribute('aria-invalid');
  $('#jump-form').setAttribute('aria-busy','false'); $('#search-form').setAttribute('aria-busy','false');
}
function normalizedDigits(value) {
  return value.trim().replace(/[\u0660-\u0669\u06f0-\u06f9]/g,char=>String(char.charCodeAt(0) - (char >= '\u06f0' ? 0x06f0 : 0x0660)));
}
async function jumpRecord(value,fromSearch = false) {
  closeResearchResults(false,false); cancelRecordJump(); ++bookSelectionJob;
  const job = ++jumpJob, readerJob = state.job;
  const input = $(fromSearch ? '#query' : '#jump-number');
  const status = $(fromSearch ? '#research-search-status' : '#jump-status');
  const form = $(fromSearch ? '#search-form' : '#jump-form');
  if (fromSearch) {
    $('#search-results').classList.remove('hidden'); $('#reopen-results').hidden = true;
    $('#search-title').textContent = 'Kayıt numarasıyla geçiş';
    $('#results-list').replaceChildren(); searchContext = null; $('#more-results').classList.add('hidden');
  }
  const normalized = normalizedDigits(value);
  const parts = normalized.split('_');
  const valid = (parts.length === 1 || (fromSearch && parts.length === 2)) &&
    parts.every(part=>/^\d{1,20}$/.test(part) && /[1-9]/.test(part));
  if (!valid) {
    status.textContent = 'İç sıra için pozitif tam sayı yazın (ör. 2).' + (fromSearch ? ' Doğrudan GK kimliği de yazabilirsiniz (ör. 146_2).' : '');
    input.setAttribute('aria-invalid','true'); return;
  }
  const canonical = parts.map(part=>part.replace(/^0+/,''));
  const bhid = canonical.length === 2 ? canonical.join('_') : `${state.book}_${canonical[0]}`;
  status.textContent = `${bhid} kaydı kontrol ediliyor…`; form.setAttribute('aria-busy','true');
  try {
    const data = await getAuxiliary(`/api/hadith/${encodeURIComponent(bhid)}`);
    if (job !== jumpJob || readerJob !== state.job) return;
    if (data.bhid !== bhid) throw new Error('Unexpected record');
    await loadHadith(bhid,true,data);
  } catch (e) {
    if (job !== jumpJob || readerJob !== state.job) return;
    status.textContent = e.status === 404 ? `${bhid} kaydı bulunamadı. Açık metin korunuyor.` : 'Kayıt bilgisine şu anda erişilemiyor. Aynı numarayla yeniden deneyebilirsiniz.';
    if (e.status === 404) input.setAttribute('aria-invalid','true');
  } finally {
    if (job === jumpJob) form.setAttribute('aria-busy','false');
  }
}
function closeResearchResults(discard = false,restoreFocus = true) {
  ++searchJob; ++jumpJob; pendingSearch = null; failedSearch = null;
  $('#results-list').setAttribute('aria-busy','false'); $('#more-results').disabled = false;
  $('#retry-research-search').hidden = true;
  if (discard) { searchContext = null; $('#results-list').replaceChildren(); }
  const inside = restoreFocus && $('#search-results').contains(document.activeElement);
  $('#search-results').classList.add('hidden');
  $('#reopen-results').hidden = !searchContext || searchContext.book !== state.book || readingMode;
  if (inside) $('#query').focus({preventScroll:true});
}
function reopenResearchResults() {
  if (!searchContext || searchContext.book !== state.book) return;
  cancelRecordJump();
  state.query = searchContext.q; $('#query').value = searchContext.q;
  $('#search-title').textContent = searchContext.title;
  $('#research-search-status').textContent = searchContext.message;
  $('#more-results').classList.toggle('hidden',searchContext.next >= searchContext.total);
  $('#search-results').classList.remove('hidden'); $('#reopen-results').hidden = true;
  $('#search-title').tabIndex = -1; $('#search-title').focus();
}
async function search(append = false) {
  if (append && pendingSearch) return;
  if (!append) {
    closeResearchResults(true,false); cancelRecordJump();
    const digits = normalizedDigits(state.query);
    if (/^[\d_+\-.,\s]+$/.test(digits) || /^[+-]?\d+(?:\.\d+)?e[+-]?\d+$/i.test(digits)) return jumpRecord(state.query,true);
    state.resultOffset = 0;
  }
  const job = ++searchJob, book = state.book, readerJob = state.job, q = state.query;
  const request = {job,book,readerJob,q,append,offset:append ? state.resultOffset : 0};
  pendingSearch = request; failedSearch = null;
  const current = ()=>job === searchJob && book === state.book && readerJob === state.job;
  $('#search-results').classList.remove('hidden'); $('#reopen-results').hidden = true;
  $('#retry-research-search').hidden = true; $('#more-results').disabled = true;
  if (!append) $('#more-results').classList.add('hidden');
  $('#results-list').setAttribute('aria-busy','true');
  $('#research-search-status').textContent = 'Aranıyor…';
  if (!append) $('#search-title').textContent = 'Bu eserde arama';
  try {
    if (q.length > 160) throw new Error('Query too long');
    const data = await getAuxiliary(q ? `/api/search?q=${encodeURIComponent(q)}&book_id=${book}&offset=${request.offset}` : `/api/books/${book}/hadiths?offset=${request.offset}`);
    if (!current()) return;
    if (data.available === false) throw new Error('Search unavailable');
    const title = q ? `“${q}” · ${number(data.total)} kayıt · bu eserde` : `Eserdeki kayıtlar · ${number(data.total)}`;
    $('#search-title').textContent = title;
    if (!data.items.length && !append) $('#results-list').append(element('p', 'empty-state', data.message || 'Bu eserde eşleşen kayıt bulunamadı.'));
    for (const row of data.items) {
      const node = button('', 'result-button', () => { closeResearchResults(false,false); loadHadith(row.bhid); });
      node.dataset.bhid = row.bhid;
      node.append(element('small', '', `${row.book_name_tr ? row.book_name_tr + ' · ' : ''}GK kaydı: ${row.bhid}`));
      const snippet = element('span'); snippet.dir = row.language && row.language !== 'ar' ? 'ltr' : 'rtl'; snippet.lang = row.language || 'ar';
      for (const part of row.snippet_parts || [{text:row.snippet,match:false}]) snippet.append(part.match ? element('mark','search-match',part.text) : document.createTextNode(part.text));
      node.append(element('small','source-record-label',row.record_label || 'Kaynak metni'),snippet);
      if (row.source_navigation_present) node.append(element('small','source-navigation-hint','Kaynakta eski gezinme notu bulunur.'));
      $('#results-list').append(node);
    }
    state.resultOffset = data.offset + data.items.length;
    const message = `${number(state.resultOffset)} / ${number(data.total)} kayıt gösteriliyor.`;
    searchContext = {book,q,title,total:data.total,next:state.resultOffset,message};
    $('#research-search-status').textContent = message;
    $('#more-results').classList.toggle('hidden', state.resultOffset >= data.total);
  } catch {
    if (!current()) return;
    failedSearch = request;
    $('#research-search-status').textContent = q.length > 160 ? 'En fazla 160 karakterle arama yapabilirsiniz.' : 'Arama sonuçları yüklenemedi. Yeniden deneyebilirsiniz; gösterilen kayıtlar korunuyor.';
    $('#retry-research-search').hidden = q.length > 160;
  } finally {
    if (pendingSearch === request) {
      pendingSearch = null; $('#results-list').setAttribute('aria-busy','false'); $('#more-results').disabled = false;
    }
  }
}

$('#book-search-form').addEventListener('submit', event => { event.preventDefault(); state.bookQuery = $('#book-search').value.trim(); loadBooks(); });
$('#more-books').addEventListener('click', () => loadBooks(true));
$('#retry-books').addEventListener('click', () => { if (failedBooks) loadBooks(failedBooks.append); });
$('#retry-book-selection').addEventListener('click', () => { if (selectedBookRequest) selectBook(selectedBookRequest); });
$('#search-form').addEventListener('submit', event => { event.preventDefault(); state.query = $('#query').value.trim(); state.resultOffset = 0; search(); });
$('#more-results').addEventListener('click', () => search(true));
$('#retry-research-search').addEventListener('click', () => { if (failedSearch) search(failedSearch.append); });
$('#close-results').addEventListener('click', () => { closeResearchResults(); cancelRecordJump(); });
$('#reopen-results').addEventListener('click',reopenResearchResults);
$('#jump-form').addEventListener('submit', event => { event.preventDefault(); jumpRecord($('#jump-number').value); });
$('#previous-record').addEventListener('click', () => { if (state.hadith?.previous) loadHadith(state.hadith.previous); });
$('#next-record').addEventListener('click', () => { if (state.hadith?.next) loadHadith(state.hadith.next); });
$('#translation-toggle').addEventListener('click', () => { const hidden = $('#translations-panel').classList.toggle('hidden'); $('#translation-toggle').setAttribute('aria-expanded', String(!hidden)); });
$('#read-tr').addEventListener('click',()=>selectTranslation('tr'));
$('#read-en').addEventListener('click',()=>selectTranslation('en'));
$('#compare-components').addEventListener('click',()=>setComparison(!comparison));
$('#arabic-tab').addEventListener('click', () => $('#arabic-text').scrollIntoView({ block: 'center', behavior: 'smooth' }));
$('#sanad-jump').addEventListener('click', () => $('.sanad-section').scrollIntoView({ block: 'start', behavior: 'smooth' }));
let pendingSanadJob = null;
$('#more-sanads').addEventListener('click', async () => {
  if (!state.hadith || (pendingSanadJob?.job === state.job && pendingSanadJob?.attempt === auxiliaryAttempt)) return;
  const job = state.job, bhid = state.hadith.bhid, offset = state.sanadOffset + 20;
  const request = {job,attempt:auxiliaryAttempt}; pendingSanadJob = request;
  $('#more-sanads').disabled = true;
  $('#more-sanads').setAttribute('aria-busy','true');
  $('#sanad-page-error').hidden = true; $('#sanad-page-error').textContent = '';
  try {
    const data = await getAuxiliary(`/api/hadith/${bhid}/sanads?offset=${offset}`);
    if (job !== state.job || bhid !== state.hadith?.bhid || request.attempt !== auxiliaryAttempt) return;
    renderSanads(data, true);
    state.sanadOffset = offset;
  } catch (e) {
    if (job === state.job && request.attempt === auxiliaryAttempt && bhid === state.hadith?.bhid) {
      $('#sanad-page-error').hidden = false;
      $('#sanad-page-error').textContent = 'Diğer senedler yüklenemedi. Aynı düğmeyle yeniden deneyebilirsiniz; gösterilen zincirler korunuyor.';
    }
  }
  finally {
    if (pendingSanadJob === request) pendingSanadJob = null;
    if (job === state.job && request.attempt === auxiliaryAttempt) { $('#more-sanads').disabled = false; $('#more-sanads').setAttribute('aria-busy','false'); }
  }
});
$('#expand-sanads').addEventListener('click', () => { const items = [...document.querySelectorAll('.sanad-item')]; const open = items.some(d => !d.open); items.forEach(d => d.open = open); $('#expand-sanads').textContent = open ? 'Tümünü kapat' : 'Tümünü aç'; });
$('#compare-sanads').addEventListener('click',toggleSanadComparison);
for (const selector of ['#sanad-compare-first','#sanad-compare-second']) $(selector).addEventListener('change',renderSanadComparison);
$('#font-up').addEventListener('click', () => { state.font = Math.min(40, state.font + 2); document.documentElement.style.setProperty('--arabic-size', `${state.font}px`); });
$('#font-down').addEventListener('click', () => { state.font = Math.max(23, state.font - 2); document.documentElement.style.setProperty('--arabic-size', `${state.font}px`); });
function recordLink() {
  if (!state.hadith) return null;
  const url = new URL(`/hadith/${encodeURIComponent(state.hadith.bhid)}`,location.origin);
  if (state.translation === 'en') url.searchParams.set('translation','en');
  if (['#arabic-text','#translations-panel','#sanad-list','#source-details'].includes(location.hash)) url.hash = location.hash;
  return url.href;
}
function clearPrintView() { $('#print-view').replaceChildren(); printContext = null; }
function finishPrintView() {
  const context = printContext; clearPrintView();
  if (!context || context.job !== state.job || context.bhid !== (state.hadith?.bhid || null)) return;
  if (context.active?.isConnected) context.active.focus({preventScroll:true});
  window.scrollTo(context.x,context.y);
}
function printableClone(source) {
  const copy = source.cloneNode(true);
  for (const node of copy.querySelectorAll('#compare-toolbar,.component-arabic-toggle,input,select,form')) node.remove();
  for (const node of copy.querySelectorAll('button')) {
    if (node.classList.contains('inline-narrator') || node.classList.contains('chain-node')) {
      const label = element('span',node.className); label.append(...node.childNodes); node.replaceWith(label);
    } else node.remove();
  }
  for (const details of copy.querySelectorAll('.translation-source-details,.component-evidence,.translation-review,.sanad-item')) details.open = true;
  for (const details of copy.querySelectorAll('details:not([open])')) {
    for (const child of [...details.children]) if (child.tagName !== 'SUMMARY') child.remove();
  }
  for (const node of [copy,...copy.querySelectorAll('*')]) {
    for (const attribute of ['id','tabindex','aria-controls','aria-describedby','aria-labelledby']) node.removeAttribute(attribute);
  }
  return copy;
}
function preparePrintView() {
  if (!printContext) printContext = {job:state.job,bhid:state.hadith?.bhid || null,active:document.activeElement,x:window.scrollX,y:window.scrollY};
  const root = $('#print-view'); root.replaceChildren();
  const data = state.hadith;
  if (!data) {
    root.append(element('h1','','Kayıt hazır değil'),element('p','','Hadis kaydı yüklenmeden kaynak çıktısı hazırlanamaz.'));
    return;
  }
  root.append(element('p','print-heading',`Cevâmi · Cevâmiu’l-Kelim 4.5 · GK ${data.bhid}`));
  const title = element('h1','',data.book.name); title.lang = 'ar'; title.dir = 'rtl'; root.append(title);
  const identity = element('dl');
  fact(identity,'GK kayıt kimliği',data.bhid,false);
  fact(identity,'İç kayıt sırası',String(data.internal_number),false);
  fact(identity,'Metinde görünen numara',data.display_number || 'Belirtilmemiş',false);
  fact(identity,'Kaynak indeksindeki atıf',data.citation.hadith_reference_raw || 'Belirtilmemiş',false);
  fact(identity,'Kaynak cilt / sayfa gösterimi',data.citation.page_reference_raw || 'Belirtilmemiş',false);
  root.append(identity,element('h2','','Arapça asıl metin'));
  const arabic = element('div','',$('#arabic-text').textContent);
  arabic.id = 'print-arabic'; arabic.lang = 'ar'; arabic.dir = 'rtl'; root.append(arabic);
  if (!$('#translations-panel').classList.contains('hidden')) {
    const language = state.translation === 'en' ? 'English' : 'Türkçe';
    const translation = element('section'); translation.id = 'print-translations';
    translation.append(element('h2','',`Çeviri · ${language}`),printableClone($(state.translation === 'en' ? '#english-content' : '#turkish-content')));
    root.append(translation);
  }
  const sanads = element('section'); sanads.id = 'print-sanads';
  const loaded = sanadComparison.bhid === data.bhid ? sanadComparison.rows.length : 0;
  const coverage = element('p'); coverage.id = 'print-sanad-coverage';
  coverage.textContent = loaded || ($('#sanad-count').textContent === '0' && data.sanad_count === 0)
    ? `Yüklenen sened: ${loaded} / ${data.sanad_count}. Çıktı yalnız yüklenmiş senedleri içerir; kaynak sırası korunur.`
    : `Senedler henüz yüklenmedi. Kaynakta kayıtlı sened: ${data.sanad_count}. Aşağıda yükleme veya erişim durumu gösterilir.`;
  sanads.append(element('h2','','Senedler'),coverage,printableClone($('#sanad-list')));
  if (pendingSanadJob?.job === state.job && pendingSanadJob?.attempt === auxiliaryAttempt) {
    sanads.append(element('p','','Ek sened sayfası yükleniyor. Bu çıktı yalnız yukarıda sayılan yüklenmiş senedleri içerir.'));
  }
  if (!$('#sanad-page-error').hidden) sanads.append(element('p','',$('#sanad-page-error').textContent));
  root.append(sanads);
  const source = element('section','print-source'); source.append(element('h2','','Kaynak künyesi'));
  const references = element('dl');
  fact(references,'Eser',data.book.name);
  fact(references,'Müellif',data.book.author);
  fact(references,'Yayınevi',data.book.publisher);
  fact(references,'Baskı / yıl',[data.book.edition,data.book.year_pub].filter(Boolean).join(' · '));
  fact(references,'Muhakkik',data.book.editor);
  fact(references,'Kaynak hükmü',data.source_judgement?.label);
  fact(references,'Kaynak hükmü — Türkçe karşılığı',data.source_judgement?.label_tr,false);
  source.append(references);
  const link = element('a','print-link',recordLink()); link.href = recordLink(); source.append(link); root.append(source);
}
$('#print-record').addEventListener('click',()=>{ if (state.hadith) window.print(); });
window.addEventListener('beforeprint',preparePrintView);
window.addEventListener('afterprint',finishPrintView);
function clearCopyFallback() {
  ++copyAttempt;
  $('#copy-fallback').hidden = true; $('#copy-text').value = '';
}
async function copyText(text,message) {
  if (!state.hadith || !text) return;
  const job = state.job, bhid = state.hadith.bhid, attempt = ++copyAttempt;
  try {
    await navigator.clipboard.writeText(text);
    if (job !== state.job || bhid !== state.hadith?.bhid || attempt !== copyAttempt) return;
    clearCopyFallback(); toast(message);
  } catch {
    if (job !== state.job || bhid !== state.hadith?.bhid || attempt !== copyAttempt) return;
    $('#copy-fallback').hidden = false;
    $('#copy-text').value = text; $('#copy-text').focus(); $('#copy-text').select();
    toast('Otomatik kopyalama yapılamadı. Seçili metni kopyalayabilirsiniz.');
  }
}
$('#copy-link').addEventListener('click',()=>copyText(recordLink(),'Hadis bağlantısı kopyalandı.'));
$('#close-copy-fallback').addEventListener('click',clearCopyFallback);
$('#copy-citation').addEventListener('click', () => {
  if (!state.hadith) return;
  const d = state.hadith;
  const citation = `${d.book.name} · ${d.book.publisher || ''} · ${d.book.edition || ''} · ${d.book.year_pub || ''}\nKaynak atfı: ${d.citation.hadith_reference_raw || 'belirtilmemiş'} · Cilt/sayfa (kaynak): ${d.citation.page_reference_raw?.trim() || 'belirtilmemiş'}\nGK kayıt kimliği: ${d.bhid}\nİç kayıt sırası: ${d.internal_number}\nMetinde görünen numara: ${d.display_number || 'belirtilmemiş'}\nVeri: Cevâmiu’l-Kelim 4.5 (Offok / Islamweb)\n${recordLink()}`;
  return copyText(citation,'Kaynak atfı kopyalandı.');
});
$('#close-narrator').addEventListener('click', () => $('#narrator-dialog').close());
$('#previous-narrator').addEventListener('click', () => navigateNarratorChain(-1));
$('#next-narrator').addEventListener('click', () => navigateNarratorChain(1));
$('#retry-hadith').addEventListener('click',()=>{ const request=state.lastHadithRequest; if (request && !state.loadingHadith) loadHadith(request.bhid,request.push); });
$('#retry-auxiliary').addEventListener('click',()=>{ if (state.hadith) loadAuxiliary(state.hadith.bhid,state.job); });
$('#narrator-dialog').addEventListener('close', () => {
  if (!$('#narrator-dialog').open) { ++narratorJob; setNarratorContext(null, null); }
});
$('#narrator-dialog').addEventListener('keydown', event => {
  if (event.key !== 'Tab') return;
  const controls = [...event.currentTarget.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex]:not([tabindex="-1"])')]
    .filter(node => node.getClientRects().length);
  const first = controls[0], last = controls.at(-1);
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault(); last?.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault(); first?.focus();
  }
});
$('#about-button').addEventListener('click', () => $('#about-dialog').showModal());
$('#close-about').addEventListener('click', () => $('#about-dialog').close());
const libraryMedia = window.matchMedia?.('(max-width:760px)');
let libraryOpen = false, libraryTrigger = null;
function setLibraryOpen(open,{restoreFocus=true,cancelSelection=true}={}) {
  const mobile = Boolean(libraryMedia?.matches) && !readingMode;
  const wasOpen = libraryOpen;
  libraryOpen = mobile && open;
  if (libraryOpen && !wasOpen) libraryTrigger = document.activeElement;
  document.body.classList.toggle('library-open',libraryOpen);
  $('#library').inert = mobile && !libraryOpen;
  if (mobile) $('#library').setAttribute('aria-hidden',String(!libraryOpen));
  else $('#library').removeAttribute('aria-hidden');
  if (libraryOpen) {
    $('#library').setAttribute('role','dialog'); $('#library').setAttribute('aria-modal','true');
  } else {
    $('#library').removeAttribute('role'); $('#library').removeAttribute('aria-modal');
  }
  $('#mobile-library').setAttribute('aria-expanded',String(libraryOpen));
  $('#library-backdrop').hidden = !libraryOpen;
  for (const selector of ['#reading','#source-details','.topbar','.skip-link']) $(selector).inert = libraryOpen;
  if (!libraryOpen && cancelSelection) {
    ++bookSelectionJob; selectedBookRequest = null;
    $('#book-selection-status').textContent = ''; $('#retry-book-selection').hidden = true;
  }
  if (libraryOpen && !wasOpen) $('#book-search').focus();
  else if (wasOpen && restoreFocus) {
    const target = libraryTrigger?.getClientRects().length ? libraryTrigger : mobile ? $('#mobile-library') : $('#book-search');
    target?.focus({preventScroll:true});
  }
}
$('#mobile-library').addEventListener('click', () => setLibraryOpen(!libraryOpen));
$('#close-library').addEventListener('click', () => setLibraryOpen(false));
$('#library-backdrop').addEventListener('click', () => setLibraryOpen(false));
$('#library-nav').addEventListener('click', () => { setLibraryOpen(true); if (!libraryOpen) $('#book-search').focus(); });
document.addEventListener('keydown', event => {
  if (!libraryOpen) return;
  if (event.key === 'Escape') { event.preventDefault(); setLibraryOpen(false); return; }
  if (event.key !== 'Tab') return;
  const controls = [...$('#library').querySelectorAll('button:not(:disabled), input:not(:disabled), a[href], [tabindex="0"]')]
    .filter(node => node.getClientRects().length && !node.classList.contains('sr-only'));
  const first = controls[0], last = controls.at(-1);
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
});
libraryMedia?.addEventListener('change', () => {
  const inside = $('#library').contains(document.activeElement);
  setLibraryOpen(false,{restoreFocus:false});
  if (inside) (libraryMedia.matches ? $('#mobile-library') : $('#book-search')).focus({preventScroll:true});
});
setLibraryOpen(false,{restoreFocus:false});
function currentHadith() {
  return location.pathname?.match(/^\/hadith\/(\d+_\d+)$/)?.[1] || new URLSearchParams(location.search).get('hadith') || document.body.dataset.hadith || '146_1';
}
function navigateSection(hash, updateUrl = true) {
  if (!['#arabic-text','#translations-panel','#sanad-list','#source-details'].includes(hash)) return;
  if (hash === '#translations-panel') {
    $('#translations-panel').classList.remove('hidden'); $('#translation-toggle').setAttribute('aria-expanded','true');
  }
  const target = hash === '#sanad-list' && sanadComparison.open ? $('#sanad-comparison') : $(hash); target.tabIndex = -1;
  target.scrollIntoView({block:'start'}); target.focus({preventScroll:true});
  if (updateUrl) history.replaceState(null,'',location.pathname + location.search + hash);
  updateViewLink();
}
for (const link of document.querySelectorAll('#section-navigation a')) link.addEventListener('click',event=>{
  event.preventDefault(); navigateSection(link.hash);
});
for (const type of ['pointerdown','keydown','wheel','touchmove','focusin']) document.addEventListener(type,()=>{++readerInteraction;},{capture:true,passive:true});
window.addEventListener('popstate', () => loadHadith(currentHadith(), false));
window.addEventListener('hashchange', updateViewLink);
loadBooks();
loadHadith(currentHadith(), false);
