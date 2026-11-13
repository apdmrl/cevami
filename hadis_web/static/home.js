const query = document.querySelector('#home-query');
const form = document.querySelector('#home-search');
const panel = document.querySelector('#suggestion-panel');
const list = document.querySelector('#suggestions');
const status = document.querySelector('#search-status');
const more = document.querySelector('#home-more');
const book = document.querySelector('#search-book');
const scope = document.querySelector('#search-scope');
const clearBook = document.querySelector('#clear-book');
const retry = document.querySelector('#home-retry');
const pageRetry = document.querySelector('#home-page-retry');
const pageStatus = document.querySelector('#home-page-status');
const languageNames = {tr:'Türkçe',en:'English',ar:'العربية'};
let generation = 0, controller, timer, active = -1, offset = 0, busy = false;
let failedSearch = null;
const language = () => form.elements.language.value;
function node(tag, cls, text) {
  const n = document.createElement(tag); n.className = cls; n.textContent = text; return n;
}
function selected(index) {
  const items = [...list.children];
  active = index;
  items.forEach((item, i) => item.setAttribute('aria-selected', String(i === active)));
  if (items[active]) {
    query.setAttribute('aria-activedescendant', items[active].id);
    items[active].scrollIntoView({block:'nearest'});
  } else query.removeAttribute('aria-activedescendant');
}
function saveQuery() {
  const params = new URLSearchParams();
  if (query.value.trim()) params.set('q',query.value.trim());
  if (language() !== 'auto') params.set('language',language());
  if (book.value) params.set('book_id',book.value);
  history.replaceState(null,'','/'+(params.size?'?'+params:''));
}
function cancelSearch() {
  controller?.abort(); clearTimeout(timer); ++generation;
  timer = null; busy = false; more.disabled = false;
  list.setAttribute('aria-busy','false');
}
function reset() {
  cancelSearch(); more.hidden = true;
  failedSearch = null; retry.hidden = true; pageRetry.hidden = true; pageStatus.textContent = '';
  list.replaceChildren(); panel.hidden = true; selected(-1);
  query.setAttribute('aria-expanded','false'); list.setAttribute('aria-busy','false');
}
async function search(append = false) {
  if (append && busy) return;
  clearTimeout(timer); timer = null; controller?.abort();
  const job = ++generation, q = query.value.trim(), lang = language(), bookId = book.value;
  status.classList.remove('error');
  failedSearch = null;
  if ([retry,pageRetry,more].includes(document.activeElement)) query.focus({preventScroll:true});
  retry.hidden = true; pageRetry.hidden = true; pageStatus.textContent = '';
  if (q.length < 2) {
    reset(); status.textContent = q ? 'Aramak için en az iki karakter yazın.' : 'Türkçe, İngilizce veya Arapça yazmaya başlayın.';
    return;
  }
  if (!append) { list.replaceChildren(); offset = 0; selected(-1); panel.hidden = true; }
  busy = true; more.disabled = true; list.setAttribute('aria-busy','true');
  status.textContent = 'Aranıyor…';
  const requestController = new AbortController(); controller = requestController;
  let timedOut = false;
  const deadline = setTimeout(()=>{ timedOut = true; requestController.abort(); },8000);
  const requestedOffset = append ? offset : 0;
  try {
    const params = new URLSearchParams({q,language:lang,limit:12,offset:requestedOffset});
    if (bookId) params.set('book_id',bookId);
    const response = await fetch('/api/search?'+params,{signal:requestController.signal});
    if (!response.ok) throw new Error('Arama yapılamadı. Tekrar deneyin.');
    const data = await response.json();
    if (job !== generation) return;
    if (data.available === false) throw new Error('Search unavailable');
    updateBooks(data.books || [],bookId,data.available !== false);
    offset = data.offset + data.items.length;
    for (const row of data.items) {
      const link = node('a','suggestion',''); link.id = 'suggestion-'+list.children.length;
      link.setAttribute('role','option'); link.setAttribute('aria-selected','false');
      const from = new URLSearchParams({q,language:lang});
      if (bookId) from.set('book_id',bookId);
      if (row.language === 'en') from.set('translation','en');
      link.href = '/hadith/'+encodeURIComponent(row.bhid)+'?'+from;
      const meta = node('div','suggestion-meta','');
      const book = node('div','suggestion-book','');
      if (row.book_name_tr) book.append(node('strong','',row.book_name_tr));
      const original = node('span','',row.book_name); original.lang = 'ar'; original.dir = 'rtl'; book.append(original);
      meta.append(book,node('b','',`GK kaydı: ${row.bhid} · ${languageNames[row.language] || ''}`));
      const snippet = node('p','suggestion-snippet','');
      for (const part of row.snippet_parts || [{text:row.snippet,match:false}]) {
        snippet.append(part.match ? node('mark','search-match',part.text) : document.createTextNode(part.text));
      }
      snippet.lang = row.language; snippet.dir = row.language === 'ar' ? 'rtl' : 'ltr';
      link.append(meta,node('span','source-record-label',row.record_label || 'Kaynak metni'),snippet);
      if (row.source_navigation_present) link.append(node('p','source-navigation-hint','Kaynakta eski gezinme notu bulunur.'));
      list.append(link);
    }
    panel.hidden = !data.items.length && !append;
    more.hidden = offset >= data.total;
    if (more.hidden && document.activeElement === more) query.focus({preventScroll:true});
    query.setAttribute('aria-expanded',String(!panel.hidden));
    status.textContent = data.available === false ? data.message : data.total
      ? `${data.total.toLocaleString('tr-TR')} kayıt bulundu · ${offset} gösteriliyor`
      : bookId ? 'Seçili eserde eşleşen kayıt bulunamadı. Eser filtresini kaldırabilir veya sorguyu değiştirebilirsiniz.'
        : 'Eşleşen kayıt bulunamadı. Başka bir kelime veya dil deneyin.';
  } catch (error) {
    if ((timedOut || error.name !== 'AbortError') && job === generation) {
      failedSearch = {q,lang,bookId,append,offset:requestedOffset};
      retry.hidden = append; pageRetry.hidden = !append; selected(-1);
      if (append) {
        more.hidden = true;
        pageStatus.textContent = timedOut ? 'Diğer sonuçlar uzun sürdü. Gösterilen kayıtlar korunuyor; bu sayfayı yeniden deneyebilirsiniz.' : 'Diğer sonuçlar yüklenemedi. Gösterilen kayıtlar korunuyor; bu sayfayı yeniden deneyebilirsiniz.';
      }
      status.textContent = timedOut ? 'Arama uzun sürdü. Yeniden deneyebilirsiniz.' : 'Arama şu anda yapılamıyor. Yeniden deneyebilirsiniz.';
      status.classList.add('error');
    }
  } finally {
    clearTimeout(deadline);
    if (job === generation) { busy = false; more.disabled = false; list.setAttribute('aria-busy','false'); }
  }
}
function changed() {
  reset(); saveQuery();
  document.querySelector('#search-examples').hidden = !!query.value;
  scope.hidden = query.value.trim().length < 2 && !book.value;
  clearBook.hidden = !book.value;
  status.textContent = query.value.trim().length >= 2 ? 'Aranıyor…' : 'Türkçe, İngilizce veya Arapça yazmaya başlayın.';
  timer = setTimeout(()=>{timer = null; search();},220);
}
query.addEventListener('input',changed);
form.addEventListener('change',event=>{ if (['language','book_id'].includes(event.target.name)) changed(); });
clearBook.addEventListener('click',()=>{ book.value=''; changed(); });
form.addEventListener('submit',event=>{
  event.preventDefault();
  if (active >= 0 && !panel.hidden) { list.children[active]?.click(); return; }
  saveQuery(); search();
});
query.addEventListener('keydown',event=>{
  if (['ArrowDown','ArrowUp'].includes(event.key) && list.children.length) {
    event.preventDefault(); panel.hidden = false; query.setAttribute('aria-expanded','true');
    selected(active < 0 ? (event.key === 'ArrowDown' ? 0 : list.children.length - 1)
      : (active + (event.key === 'ArrowDown' ? 1 : -1) + list.children.length) % list.children.length);
  }
});
function dismissSuggestions() {
  const pending = busy || timer != null;
  const restoreFocus = panel.contains(document.activeElement) || [retry,pageRetry].includes(document.activeElement);
  cancelSearch();
  if (failedSearch?.append) more.hidden = false;
  failedSearch = null; retry.hidden = true; pageRetry.hidden = true; pageStatus.textContent = '';
  panel.hidden = true; query.setAttribute('aria-expanded','false'); selected(-1);
  if (restoreFocus) query.focus({preventScroll:true});
  if (pending) status.textContent = 'Arama durduruldu. Yeniden aramak için Ara’ya basın.';
}
document.querySelector('#home-main').addEventListener('keydown',event=>{
  if (event.key === 'Escape') { event.preventDefault(); dismissSuggestions(); }
});
function retrySearch() {
  const failed = failedSearch;
  if (!failed || failed.q !== query.value.trim() || failed.lang !== language() || failed.bookId !== book.value ||
      failed.offset !== (failed.append ? offset : 0)) return;
  return search(failed.append);
}
retry.addEventListener('click',retrySearch);
pageRetry.addEventListener('click',retrySearch);
more.addEventListener('click',()=>search(true));
for (const example of document.querySelectorAll('[data-query]')) example.addEventListener('click',()=>{
  query.value = example.dataset.query; changed(); query.focus();
});
function restore() {
  const params = new URLSearchParams(location.search);
  query.value = (params.get('q') || '').slice(0,160);
  const lang = params.get('language');
  form.elements.language.value = ['tr','en','ar'].includes(lang) ? lang : 'auto';
  const selectedBook = params.get('book_id');
  if (selectedBook && /^\d+$/.test(selectedBook)) {
    if (![...book.options].some(option=>option.value===selectedBook)) {
      const option=node('option','',`Kaynak eser ${selectedBook}`); option.value=selectedBook; book.append(option);
    }
    book.value=selectedBook;
  } else book.value='';
  changed();
}
function updateBooks(rows,selectedBook,available = true) {
  const previous=book.selectedOptions[0]?.textContent;
  const all=node('option','','Tüm eserler'); all.value=''; book.replaceChildren(all);
  for (const row of rows) {
    const option=node('option','',`${row.name_tr || row.name} · ${row.count.toLocaleString('tr-TR')} kayıt`);
    option.value=row.book_id; book.append(option);
  }
  if (selectedBook && !rows.some(row=>row.book_id===selectedBook)) {
    const title=previous?.replace(/ · [\d.,]+ kayıt$/,'') || `Kaynak eser ${selectedBook}`;
    const option=node('option','',title + (available ? ' · 0 kayıt' : '')); option.value=selectedBook; book.append(option);
  }
  book.value=selectedBook; clearBook.hidden=!selectedBook;
}
window.addEventListener('popstate',restore);
restore();
