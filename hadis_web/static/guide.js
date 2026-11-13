// Optional help: no fetches, persisted preferences, or changes to the loaded record.
const guideTrigger = document.querySelector('#open-guide');
if (guideTrigger && !document.querySelector('#usage-dialog')) {
  const home = document.body.classList.contains('search-home');
  const reading = document.body.dataset.page === 'hadith';
  const node = (tag, cls, text) => {
    const item = document.createElement(tag);
    if (cls) item.className = cls;
    if (text !== undefined) item.textContent = text;
    return item;
  };
  const dialog = node('dialog','usage-dialog'); dialog.id = 'usage-dialog';
  dialog.setAttribute('aria-labelledby','usage-title'); dialog.setAttribute('aria-describedby','usage-intro');
  const header = node('div','usage-top');
  const title = node('h2','','Kullanım rehberi'); title.id = 'usage-title';
  const close = node('button','icon-button','×'); close.id = 'close-guide'; close.type = 'button';
  close.setAttribute('aria-label','Kullanım rehberini kapat'); close.autofocus = true;
  header.append(title,close);
  const body = node('div','usage-body'); body.id = 'usage-body'; body.tabIndex = 0;
  body.setAttribute('role','region'); body.setAttribute('aria-label','Rehber içeriği');
  const intro = node('p','usage-intro',home
    ? 'Bir kelimeden başlayın; bulduğunuz kaydı aslı ve kaynaklarıyla inceleyin.'
    : reading ? 'Bu görünüm tek bir kaydı rahatça okumak içindir. Ayrıntılı inceleme için araştırma alanına geçebilirsiniz.'
      : 'Bu alan eser, metin, sened ve ravi bilgilerini birlikte incelemek içindir. Sade okumaya da geçebilirsiniz.');
  intro.id = 'usage-intro'; body.append(intro);
  const steps = node('ol','usage-steps');
  const instructions = home ? [
    ['Kelimeyle başlayın','En az iki karakter yazın. Türkçe, İngilizce veya Arapça kelimeyle arayabilirsiniz.'],
    ['Sonuçları daraltın','Dili seçin. Sonuçlar gelince eser filtresiyle aramayı daraltabilirsiniz.'],
    ['Kaydı açın','Bir sonuca tıklayın. Açılan sayfada Arapça asıl metin, mevcut çeviriler ve kaynak bilgileri bulunur.'],
  ] : reading ? [
    ['Asıl metni okuyun','A− ve A+ düğmeleri Arapça yazı boyutunu değiştirir. Ravi adlarına dokunarak kaynak kaydını açabilirsiniz.'],
    ['Bölümler arasında geçin','Üstteki Arapça metin, Çeviri, Senedler ve Kaynak bağlantıları sizi ilgili bölüme götürür.'],
    ['Kaynakla paylaşın','Bağlantıyı veya atfı kopyalayın. İç sıra, kaynakta görünen hadis numarasından farklı olabilir.'],
  ] : [
    ['Eseri seçin','Eser listesinden kitap seçin. Telefonda liste sağ üstteki ☰ düğmesiyle açılır.'],
    ['Metni bulun','Kelimeyle bu eserde arayın veya iç sıra girin. Sonuçtan kayda geçtiğinizde son aramaya geri dönebilirsiniz.'],
    ['Sened ve raviyi inceleyin','Seneddeki ravi düğmesi kendi kaynak sırasıyla kartı açar. Birden fazla sened varsa iki senedi yan yana inceleyebilirsiniz.'],
  ];
  for (const [label,text] of instructions) {
    const step = node('li'); step.append(node('h3','',label),node('p','',text)); steps.append(step);
  }
  body.append(steps);
  const actions = node('div','usage-actions');
  const sectionButtons = [];
  if (home) {
    const example = node('a','usage-action','Örnek arama: niyet'); example.id = 'guide-example'; example.href = '/?q=niyet';
    example.addEventListener('click',()=>dialog.close()); actions.append(example);
  } else {
    for (const [hash,label] of [['#arabic-text','Metne git'],['#translations-panel','Çeviriye git'],['#sanad-list','Senedlere git'],['#source-details','Kaynağa git']]) {
      const action = node('button','usage-action',label); action.type = 'button'; action.dataset.guideSection = hash;
      action.addEventListener('click',()=>{
        syncAvailability();
        if (action.disabled) return;
        const link = document.querySelector(`#section-navigation a[href="${hash}"]`);
        dialog.close(); link.click();
      });
      actions.append(action); sectionButtons.push(action);
    }
  }
  body.append(actions);
  const readyNote = node('p','usage-ready-note'); readyNote.setAttribute('role','status');
  if (!home) body.append(readyNote);
  const terms = node('details','usage-terms');
  terms.append(node('summary','','Terimler ve inceleme durumları'));
  const definitions = node('dl');
  for (const [term,text] of [
    ['İç sıra ve GK kimliği','İç sıra eserdeki kayıt sırasıdır; GK kimliği verideki kaydı ayırt eder. Bunlar başka baskının hadis numarasıyla otomatik eşitlenmez.'],
    ['Sened ve ravi','Sened, kaynağın kaydettiği rivayet zinciridir. Ravi bağlantısı kaynakta o kişi için tutulan bilgileri açar. Yapısal işaretler kişi değildir.'],
    ['İnceleme bekliyor','İlgili aktarımın incelemesi henüz tamamlanmamıştır.'],
    ['Kaynak karşılaştırması','Gösterilen alan veya bölüm için kaynak karşılaştırması vardır; uzman onayı değildir. Rivayetin tamamının çevirisi veya sıhhat onayı anlamına gelmez.'],
    ['İnceleme sorunu var','Kaynak farkı veya aktarım sorunu belirtilmiştir. Kapalı ayrıntılardaki gerekçeyi inceleyebilirsiniz.'],
    ['Bulunmuyor ve erişilemiyor','Kaynakta kayıt bulunmaması ile yüklemenin başarısız olması farklıdır. Erişim hatasında yeniden deneme seçeneğini kullanın.'],
  ]) definitions.append(node('dt','',term),node('dd','',text));
  terms.append(definitions); body.append(terms);
  let guideView;
  if (!home) {
    guideView = node('a','usage-view-link'); guideView.id = 'guide-view';
    guideView.addEventListener('click',()=>dialog.close()); body.append(guideView);
  }
  function syncAvailability() {
    if (home) return;
    const navigation = document.querySelector('#section-navigation');
    const paper = document.querySelector('#hadith-paper');
    const ready = !paper.hidden && paper.getAttribute('aria-busy') === 'false' && !navigation.hidden && navigation.getClientRects().length > 0;
    for (const action of sectionButtons) action.disabled = !ready;
    readyNote.textContent = ready ? '' : 'Kayıt henüz açık değil. Yüklendiğinde bölüm bağlantıları kullanılabilir. Rehberi kapatıp Hadis ara bağlantısıyla bir kayıt arayabilirsiniz.';
    const link = document.querySelector('#open-research');
    guideView.hidden = !ready || link.hidden;
    if (ready) { guideView.href = link.href; guideView.textContent = reading ? 'Bu kaydı araştırma alanında aç ↗' : 'Bu kaydı sade okumada aç ↗'; }
  }
  dialog.append(header,body); document.body.append(dialog);
  close.addEventListener('click',()=>dialog.close());
  guideTrigger.setAttribute('aria-haspopup','dialog'); guideTrigger.setAttribute('aria-controls',dialog.id);
  guideTrigger.addEventListener('click',()=>{
    syncAvailability();
    if (!dialog.open) { dialog.showModal(); body.scrollTop = 0; }
  });
  dialog.addEventListener('click',event=>{
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
  });
  dialog.addEventListener('keydown',event=>{
    if (event.key !== 'Tab') return;
    const controls = [...dialog.querySelectorAll('button:not(:disabled),a[href],summary,[tabindex="0"]')]
      .filter(item=>item.getClientRects().length);
    if (event.shiftKey && document.activeElement === controls[0]) { event.preventDefault(); controls.at(-1)?.focus(); }
    else if (!event.shiftKey && document.activeElement === controls.at(-1)) { event.preventDefault(); controls[0]?.focus(); }
  });
  if (!home) {
    const observer = new MutationObserver(syncAvailability);
    observer.observe(document.querySelector('#section-navigation'),{attributes:true,attributeFilter:['hidden']});
    observer.observe(document.querySelector('#open-research'),{attributes:true,attributeFilter:['hidden','href']});
    observer.observe(document.querySelector('#hadith-paper'),{attributes:true,attributeFilter:['hidden','aria-busy']});
    syncAvailability();
  }
}
