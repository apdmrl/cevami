// Run the actual client event handler against delayed/rejected transport.
// This is a DOM boundary stub, not browser automation.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function client() {
  const nodes = new Map();
  function node() {
    return {children: [], handlers: {}, dataset: {}, style: {}, attributes: {},
      classList: {toggle(){},add(){},remove(){}},
      addEventListener(event, fn){this.handlers[event] = fn;},
      setAttribute(key,value){this.attributes[key]=String(value);},removeAttribute(key){delete this.attributes[key];},
      getAttribute(key){return this.attributes[key]??null;},
      contains(other){return descendants(this).includes(other);},
      showModal(){this.open=true;},close(){this.open=false;this.handlers.close?.();},
      focus(){document.activeElement=this;},
      scrollIntoView(){this.scrolled=true;},
      append(...items){this.children.push(...items);},
      replaceChildren(...items){
        if(this.children.some(child=>descendants(child).includes(document.activeElement))) document.activeElement=document.body;
        this.children = items;
      }};
  }
  const document = {querySelector(selector){if (!nodes.has(selector)) nodes.set(selector,node()); return nodes.get(selector);},
    querySelectorAll(){return [];},addEventListener(){},createElement:node,createTextNode:text=>({textContent:text}),
    body:node()};
  let respond;
  const pending = [];
  const urls = [];
  const context = vm.createContext({document,Intl,URL,URLSearchParams,encodeURIComponent,AbortController,
    location:{search:''},window:{addEventListener(){}},history:{pushState(){}},
    setTimeout,clearTimeout,
    fetch(url){urls.push(url); return new Promise(resolve=>{respond=resolve;pending.push({url,resolve});});}});
  vm.runInContext(fs.readFileSync(process.env.HADIS_TEST_READER_SCRIPT || path.join(__dirname,'../hadis_web/static/app.js'),'utf8'),context);
  // Initial loads are intentionally left pending. Test the real paging handler
  // from the point a hadith has already loaded.
  vm.runInContext("state.hadith={bhid:'978_1'}; state.job=10; state.sanadOffset=0;",context);
  return {context,nodes,urls,run:()=>document.querySelector('#more-sanads').handlers.click(),
    reply(data,ok=true){respond({ok,json:async()=>data});},
    replyTo(url,data,ok=true){const request=pending.find(p=>p.url===url&&!p.done);assert.ok(request,url);request.done=true;request.resolve({ok,json:async()=>data});}};
}

function flattened(node){return [node?.textContent||'',...(node?.children||[]).map(flattened)].join(' ');}
function descendants(node){return [node,...(node?.children||[]).flatMap(descendants)];}
function readerLocation(c){
  c.context.location={origin:'http://localhost',pathname:'/research',search:'',hash:''};
  c.context.history={pushState(){},replaceState(){}};
  vm.runInContext('state.loadingHadith=null',c.context);
}
function sourceContext(sanadId=9001,position=0){return {bhid:'978_1',sanadId,position,members:[
  {kind:'narrator',source_id:6817,position:0,label:'ألف'},
  {kind:'structural_marker',source_id:30001,position:1,label:'موضع تعليق',label_tr:'Ta‘lik'},
  {kind:'narrator',source_id:4864,position:2,label:'باء'},
  {kind:'unresolved',source_id:null,position:3,label:null},
  {kind:'narrator',source_id:6817,position:4,label:'ألف'}]};}
function profile(id,name='PROFILE'){return {id,name,shohra:name,source:'fixture',opinions:[],opinions_total:0};}
function opinionClient(total=2){
  const c=client();
  vm.runInContext(`narratorJob=7;document.querySelector('#narrator-dialog').open=true;
    var recoveryOpinion={alem_id:'924',critic:'عبد الرحمن',opinion:'كلام المصدر'};
    renderOpinions({id:4698,opinions:[recoveryOpinion],opinions_total:${total}},document.querySelector('#opinion-recovery'),7);`,c.context);
  const root=c.nodes.get('#opinion-recovery');
  return {...c,root,more:root.children.at(-1)};
}

test('a stalled opinion page times out and can retry the same source offset',async()=>{
  const c=opinionClient();let expire,deliver;
  c.context.setTimeout=(callback,ms)=>{assert.equal(ms,8000);expire=callback;return -1;};c.context.clearTimeout=()=>{};
  c.context.fetch=(_url,options)=>new Promise((resolve,reject)=>{
    options?.signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true});
    deliver=data=>resolve({ok:true,json:async()=>data});
  });
  const request=c.more.handlers.click();
  assert.equal(typeof expire,'function','opinion lookup has an8s deadline');
  expire();await request;
  const status=c.root.children.find(n=>n.className==='opinion-page-status');
  assert.equal(status.hidden,false);assert.match(status.textContent,/yüklenemedi/);
  assert.match(flattened(c.root),/كلام المصدر/);assert.equal(c.more.disabled,false);
  const retry=c.more.handlers.click();deliver({total:2,offset:1,items:[{alem_id:'925',critic:'ثان',opinion:'النص التالي'}]});await retry;
  assert.match(flattened(c.root),/النص التالي/);assert.equal(status.hidden,true);
});

test('opinion page failure is local and closing ignores old errors and data',async()=>{
  const c=opinionClient();let request=c.more.handlers.click();
  c.reply({detail:'unavailable'},false);await request;
  const status=c.root.children.find(n=>n.className==='opinion-page-status');
  assert.ok(status);assert.equal(status.hidden,false);
  request=c.more.handlers.click();
  vm.runInContext("document.querySelector('#narrator-dialog').open=false",c.context);
  c.reply({detail:'CLOSED ERROR'},false);await request;
  assert.equal(status.hidden,true,'old error cannot reopen local status after close');
  assert.doesNotMatch(flattened(c.nodes.get('#toast')),/CLOSED ERROR/);
});

test('last opinion page transfers focus before hiding its load button',async()=>{
  const c=opinionClient();c.more.focus();
  const request=c.more.handlers.click();
  assert.equal(c.more.getAttribute('aria-busy'),'true');
  assert.equal(vm.runInContext('document.activeElement',c.context),c.nodes.get('#narrator-content'));
  c.reply({total:2,offset:1,items:[{alem_id:'925',critic:'ثان',opinion:'النص التالي'}]});await request;
  assert.equal(c.more.hidden,true);assert.equal(c.more.getAttribute('aria-busy'),'false');
  assert.equal(vm.runInContext('document.activeElement',c.context),c.nodes.get('#narrator-content'));
});
async function openProfile(c,id,context){
  const pending=vm.runInContext(`showNarrator(${id},${JSON.stringify(context)})`,c.context);
  c.replyTo(`/api/narrator/${id}`,profile(id));await pending;
}

function comparisonRows(){
  const context=sourceContext();
  context.members[3]={kind:'unresolved',source_id:914001,position:3,label:'914001'};
  const row={bhid:context.bhid,sanad_id:context.sanadId,members:context.members,
    source_judgement:{code:0,label:'صحيح',label_tr:'Sahih'}};
  return [row,{...row,sanad_id:9002,members:[
    {kind:'narrator',source_id:6817,position:0,label:'ألف آخر'},
    {kind:'narrator',source_id:9008,position:1,label:'باء'},
    {kind:'structural_marker',source_id:30001,position:2,label:'موضع تعليق',label_tr:'Ta‘lik'},
    {kind:'unresolved',source_id:914001,position:3,label:'914001'}]}];
}
function loadComparison(c,rows=comparisonRows(),append=false,total=rows.length){
  vm.runInContext(`renderSanads(${JSON.stringify({total,offset:append?20:0,items:rows})},${append})`,c.context);
}

test('two source chains retain exact positions, repeated identities, markers and ID-only overlap',()=>{
  const c=client();loadComparison(c);
  c.nodes.get('#compare-sanads').handlers.click();
  assert.equal(c.nodes.get('#sanad-comparison').hidden,false);
  assert.equal(c.nodes.get('#sanad-compare-first').value,'9001');
  assert.equal(c.nodes.get('#sanad-compare-second').value,'9002');
  const columns=c.nodes.get('#sanad-comparison-result').children;
  assert.equal(columns.length,2);
  assert.match(flattened(columns[0]),/Sened 9001.*1\. sıra.*2\. sıra.*3\. sıra.*4\. sıra.*5\. sıra/);
  assert.match(flattened(columns[1]),/Sened 9002.*1\. sıra.*2\. sıra.*3\. sıra.*4\. sıra/);
  assert.match(flattened(columns[0]),/Çözümlenemeyen kaynak halkası/);
  const shared=descendants(c.nodes.get('#sanad-comparison-result')).filter(n=>n?.className==='sanad-shared-key');
  assert.equal(shared.length,3,'two occurrences in first chain and one in second');
  assert.ok(shared.every(n=>n.textContent.includes('6817')),'equal names and marker/unresolved IDs do not match');
  assert.match(c.nodes.get('#sanad-comparison-status').textContent,/Ortak kaynak ravi kimliği: 1/);
});

test('comparison narrator opens its exact column source context; non-people stay non-interactive',async()=>{
  const c=client();loadComparison(c);c.nodes.get('#compare-sanads').handlers.click();
  const columns=c.nodes.get('#sanad-comparison-result').children;
  const people=descendants(columns[0]).filter(n=>n?.className==='sanad-compare-person');
  assert.equal(people.length,3);
  assert.equal(descendants(columns[1]).filter(n=>n?.className==='sanad-compare-person').length,2);
  const request=people[2].handlers.click();
  c.replyTo('/api/narrator/6817',profile(6817));await request;
  assert.match(c.nodes.get('#narrator-context-label').textContent,/9001.*5\. sıra.*978_1/);
  assert.ok(!c.urls.some(url=>/narrator\/(30001|914001)/.test(url)));
});

test('equal source selection is explicit and clearing/closing removes old comparison',()=>{
  const c=client();loadComparison(c);c.nodes.get('#compare-sanads').handlers.click();
  c.nodes.get('#sanad-compare-second').value='9001';
  c.nodes.get('#sanad-compare-second').handlers.change();
  assert.match(c.nodes.get('#sanad-comparison-status').textContent,/İki farklı sened seçin/);
  assert.equal(c.nodes.get('#sanad-comparison-result').children.length,0);
  assert.equal(c.nodes.get('#sanad-compare-second').value,'9001','do not silently select another source');
  c.nodes.get('#compare-sanads').handlers.click();
  assert.equal(c.nodes.get('#sanad-comparison').hidden,true);
  assert.equal(c.nodes.get('#compare-sanads').getAttribute('aria-expanded'),'false');
  assert.equal(vm.runInContext('document.activeElement',c.context),c.nodes.get('#compare-sanads'));
});

test('zero or one source chain cannot open a misleading comparison',()=>{
  const c=client();loadComparison(c,[]);
  assert.equal(c.nodes.get('#compare-sanads').disabled,true);
  loadComparison(c,comparisonRows().slice(0,1));
  assert.equal(c.nodes.get('#compare-sanads').disabled,true);
  assert.equal(c.nodes.get('#sanad-comparison').hidden,true);
});

test('appending source pages retains both chosen chains and reports only loaded coverage',async()=>{
  const c=client();loadComparison(c,comparisonRows(),false,3);
  c.nodes.get('#compare-sanads').handlers.click();
  c.nodes.get('#sanad-compare-first').value='9002';c.nodes.get('#sanad-compare-first').handlers.change();
  c.nodes.get('#sanad-compare-second').value='9001';c.nodes.get('#sanad-compare-second').handlers.change();
  const request=c.run();
  assert.match(c.nodes.get('#sanad-comparison-coverage').textContent,/Yüklenen 2 \/ kayıtta 3/);
  c.reply({total:3,offset:20,items:[{...comparisonRows()[0],sanad_id:9003}]});await request;
  assert.equal(c.nodes.get('#sanad-compare-first').value,'9002');
  assert.equal(c.nodes.get('#sanad-compare-second').value,'9001');
  assert.match(c.nodes.get('#sanad-comparison-coverage').textContent,/Yüklenen 3 \/ kayıtta 3/);
  assert.match(flattened(c.nodes.get('#sanad-comparison-result').children[0]),/Sened 9002/);
});

test('failed and obsolete source pages cannot erase or repopulate another comparison',async()=>{
  const c=client();loadComparison(c,comparisonRows(),false,3);c.nodes.get('#compare-sanads').handlers.click();
  const failed=c.run();c.replyTo('/api/hadith/978_1/sanads?offset=20',{detail:'failed'},false);await failed;
  assert.equal(c.nodes.get('#sanad-comparison').hidden,false);
  assert.equal(c.nodes.get('#sanad-comparison-result').children.length,2);
  assert.match(c.nodes.get('#sanad-comparison-coverage').textContent,/Yüklenen 2 \/ kayıtta 3/);
  const old=c.run();
  vm.runInContext("loadHadith('146_1',false)",c.context);
  c.replyTo('/api/hadith/978_1/sanads?offset=20',{total:3,offset:20,items:[{...comparisonRows()[0],sanad_id:9003}]});await old;
  assert.equal(c.nodes.get('#sanad-comparison').hidden,true);
  assert.equal(c.nodes.get('#compare-sanads').disabled,true);
  assert.equal(c.nodes.get('#sanad-comparison-result').children.length,0);
});

test('auxiliary reload clears old chain comparison before new source data arrives',()=>{
  const c=client();loadComparison(c);c.nodes.get('#compare-sanads').handlers.click();
  vm.runInContext("loadAuxiliary('978_1',10)",c.context);
  assert.equal(c.nodes.get('#sanad-comparison').hidden,true);
  assert.equal(c.nodes.get('#compare-sanads').disabled,true);
  assert.equal(c.nodes.get('#sanad-comparison-result').children.length,0);
});

test('comparison buttons expose shared status and exact source identity to assistive technology',()=>{
  const c=client();loadComparison(c);c.nodes.get('#compare-sanads').handlers.click();
  const people=descendants(c.nodes.get('#sanad-comparison-result')).filter(n=>n?.className==='sanad-compare-person');
  const shared=people.find(n=>flattened(n).includes('Ortak kaynak ravi kimliği: 6817'));
  const distinct=people.find(n=>flattened(n).includes('Kaynak ravi kimliği: 9008'));
  assert.match(shared.getAttribute('aria-label'),/Ortak kaynak ravi kimliği: 6817/);
  assert.match(distinct.getAttribute('aria-label'),/Kaynak ravi kimliği: 9008/);
  assert.doesNotMatch(distinct.getAttribute('aria-label'),/Ortak/);
});

test('late page append preserves selected column nodes and focused narrator trigger',async()=>{
  const c=client();loadComparison(c,comparisonRows(),false,3);c.nodes.get('#compare-sanads').handlers.click();
  const columns=[...c.nodes.get('#sanad-comparison-result').children];
  const trigger=descendants(columns[0]).find(n=>n?.className==='sanad-compare-person');
  const request=c.run();trigger.focus();
  c.reply({total:3,offset:20,items:[{...comparisonRows()[0],sanad_id:9003}]});await request;
  assert.equal(c.nodes.get('#sanad-comparison-result').children[0],columns[0]);
  assert.equal(c.nodes.get('#sanad-comparison-result').children[1],columns[1]);
  assert.equal(vm.runInContext('document.activeElement',c.context),trigger);
});

test('section navigation targets the open comparison instead of skipping to lists below it',()=>{
  const c=client();loadComparison(c);c.nodes.get('#compare-sanads').handlers.click();
  vm.runInContext("navigateSection('#sanad-list',false)",c.context);
  assert.equal(c.nodes.get('#sanad-comparison').scrolled,true);
  assert.equal(vm.runInContext('document.activeElement',c.context),c.nodes.get('#sanad-comparison'));
});

test('the source chain button passes its own branch context into the narrator dialog',async()=>{
  const c=client();const context=sourceContext();
  vm.runInContext(`renderSanads(${JSON.stringify({total:1,offset:0,items:[{bhid:context.bhid,sanad_id:context.sanadId,members:context.members,source_judgement:{code:0,label:'صحيح',label_tr:'Sahih'}}]})})`,c.context);
  const sourceButton=descendants(c.nodes.get('#sanad-list')).find(n=>n?.className==='chain-node');
  assert.ok(sourceButton);
  const pending=sourceButton.handlers.click();c.replyTo('/api/narrator/6817',profile(6817));await pending;
  assert.equal(c.nodes.get('#narrator-context').hidden,false);
  assert.match(c.nodes.get('#narrator-context-label').textContent,/9001.*1\. sıra.*978_1/);
});

test('narrator card keeps selected branch and actual position when a person occurs again',async()=>{
  const c=client();await openProfile(c,6817,sourceContext());
  assert.equal(c.nodes.get('#narrator-context')?.hidden,false);
  assert.match(c.nodes.get('#narrator-context-label').textContent,/9001.*1\. sıra/);
  await openProfile(c,6817,sourceContext(9002,4));
  assert.match(c.nodes.get('#narrator-context-label').textContent,/9002.*5\. sıra/);
  const list=descendants(c.nodes.get('#narrator-content'));
  assert.match(flattened(c.nodes.get('#narrator-content')),/موضع تعليق/);
  assert.match(flattened(c.nodes.get('#narrator-content')),/Çözümlenemeyen/);
  assert.equal(list.filter(n=>n?.getAttribute?.('aria-current')==='true').length,1);
  assert.equal(c.nodes.get('#next-narrator').disabled,true);
});

test('chain navigation skips non-people without renumbering or requesting their profiles',async()=>{
  const c=client();await openProfile(c,6817,sourceContext());
  assert.equal(c.nodes.get('#previous-narrator')?.disabled,true);
  const next=c.nodes.get('#next-narrator').handlers.click();
  c.replyTo('/api/narrator/4864',profile(4864));await next;
  assert.match(c.nodes.get('#narrator-context-label').textContent,/3\. sıra/);
  assert.ok(!c.urls.some(url=>/narrator\/(30001|null)/.test(url)));
  const inline=vm.runInContext('showNarrator(6817)',c.context);
  c.replyTo('/api/narrator/6817',profile(6817));await inline;
  assert.equal(c.nodes.get('#narrator-context').hidden,true);
});

test('delayed narrator data and errors cannot replace a newer chain selection',async()=>{
  const c=client();
  const old=vm.runInContext(`showNarrator(6817,${JSON.stringify(sourceContext())})`,c.context);
  await openProfile(c,4864,sourceContext(9002,2));
  c.replyTo('/api/narrator/6817',profile(6817,'OLD PERSON'));await old;
  assert.doesNotMatch(flattened(c.nodes.get('#narrator-content')),/OLD PERSON/);
  assert.match(c.nodes.get('#narrator-context-label').textContent,/9002.*3\. sıra/);
  const failed=vm.runInContext(`showNarrator(6817,${JSON.stringify(sourceContext())})`,c.context);
  await openProfile(c,4864,sourceContext(9002,2));
  c.replyTo('/api/narrator/6817',{detail:'OLD ERROR'},false);await failed;
  assert.doesNotMatch(flattened(c.nodes.get('#narrator-content')),/OLD ERROR/);
});

test('failed narrator requests retry the same person and source context',async()=>{
  const c=client();const request=vm.runInContext(`showNarrator(4864,${JSON.stringify(sourceContext(9002,2))})`,c.context);
  c.replyTo('/api/narrator/4864',{detail:'Unavailable'},false);await request;
  const retry=descendants(c.nodes.get('#narrator-content')).find(n=>n?.textContent==='Ravi kaydını yeniden yükle');
  assert.ok(retry,'retry remains available for a failed profile');
  const pending=retry.handlers.click();c.replyTo('/api/narrator/4864',profile(4864));await pending;
  assert.match(c.nodes.get('#narrator-context-label').textContent,/9002.*3\. sıra/);
  assert.match(flattened(c.nodes.get('#narrator-content')),/PROFILE/);
});

test('closing or changing the hadith clears narrator context and ignores pending data',async()=>{
  const c=client();
  let pending=vm.runInContext(`showNarrator(6817,${JSON.stringify(sourceContext())})`,c.context);
  c.nodes.get('#narrator-dialog').close();c.replyTo('/api/narrator/6817',profile(6817,'CLOSED DATA'));await pending;
  assert.equal(c.nodes.get('#narrator-context')?.hidden,true);
  assert.doesNotMatch(flattened(c.nodes.get('#narrator-content')),/CLOSED DATA/);
  pending=vm.runInContext(`showNarrator(4864,${JSON.stringify(sourceContext(9001,2))})`,c.context);
  vm.runInContext("loadHadith('146_1',false)",c.context);
  c.replyTo('/api/narrator/4864',profile(4864,'OLD HADITH'));await pending;
  assert.equal(c.nodes.get('#narrator-dialog').open,false);
  assert.equal(c.nodes.get('#narrator-context').hidden,true);
  assert.doesNotMatch(flattened(c.nodes.get('#narrator-content')),/OLD HADITH/);
});

test('a timed-out narrator lookup remains retryable and ignores its eventual response',async()=>{
  const c=client();let expire,deliver;
  c.context.setTimeout=(callback,ms)=>{assert.equal(ms,8000);expire=callback;return -1;};
  c.context.clearTimeout=()=>{};
  c.context.fetch=(_url,options)=>new Promise((resolve,reject)=>{
    options.signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true});
    deliver=data=>resolve({ok:true,json:async()=>data});
  });
  const request=vm.runInContext(`showNarrator(6817,${JSON.stringify(sourceContext())})`,c.context);
  const oldResponse=deliver;assert.ok(expire);expire();await request;
  assert.match(flattened(c.nodes.get('#narrator-content')),/şu anda erişilemiyor/);
  oldResponse(profile(6817,'TOO LATE'));await Promise.resolve();
  assert.doesNotMatch(flattened(c.nodes.get('#narrator-content')),/TOO LATE/);
  const retry=descendants(c.nodes.get('#narrator-content')).find(n=>n?.textContent==='Ravi kaydını yeniden yükle');
  const next=retry.handlers.click();deliver(profile(6817));await next;
  assert.match(flattened(c.nodes.get('#narrator-content')),/PROFILE/);
});

test('a queued close event from an earlier opening cannot cancel the reopened narrator',async()=>{
  const c=client();await openProfile(c,6817,sourceContext());
  const dialog=c.nodes.get('#narrator-dialog');
  // Native dialog close events are queued; unlike the default stub they need not fire in close().
  dialog.close=()=>{dialog.open=false;};dialog.close();
  const newer=vm.runInContext(`showNarrator(4864,${JSON.stringify(sourceContext(9002,2))})`,c.context);
  dialog.handlers.close();
  c.replyTo('/api/narrator/4864',profile(4864,'REOPENED'));await newer;
  assert.equal(c.nodes.get('#narrator-context').hidden,false);
  assert.match(c.nodes.get('#narrator-context-label').textContent,/9002.*3\. sıra/);
  assert.match(flattened(c.nodes.get('#narrator-content')),/REOPENED/);
});

test('already loaded chain members remain usable while a profile is pending or unavailable',async()=>{
  const c=client();const request=vm.runInContext(`showNarrator(6817,${JSON.stringify(sourceContext())})`,c.context);
  const sourceText=flattened(c.nodes.get('#narrator-content'));
  assert.match(sourceText,/Kaynak zincirinin tamamı/);
  assert.match(sourceText,/موضع تعليق/);
  c.replyTo('/api/narrator/6817',{detail:'Unavailable'},false);await request;
  assert.match(flattened(c.nodes.get('#narrator-content')),/Kaynak zincirinin tamamı/);
  const other=descendants(c.nodes.get('#narrator-content')).find(n=>n?.className==='narrator-context-person'&&n.getAttribute('aria-label').startsWith('3. sıra'));
  const pending=other.handlers.click();c.replyTo('/api/narrator/4864',profile(4864));await pending;
  assert.match(c.nodes.get('#narrator-context-label').textContent,/3\. sıra/);
});

test('keyboard focus survives disabling the final next button',async()=>{
  const c=client();await openProfile(c,4864,sourceContext(9001,2));
  const next=c.nodes.get('#next-narrator');let disabled=next.disabled;
  Object.defineProperty(next,'disabled',{get:()=>disabled,set:value=>{
    disabled=value;
    if(value&&c.context.document.activeElement===next)c.context.document.activeElement=c.context.document.body;
  }});
  next.focus();const pending=next.handlers.click();c.replyTo('/api/narrator/6817',profile(6817));await pending;
  assert.equal(c.context.document.activeElement,c.nodes.get('#narrator-content'));
});

test('keyboard focus survives replacing the retry button during a fresh lookup',async()=>{
  const c=client();
  const failed=vm.runInContext(`showNarrator(4864,${JSON.stringify(sourceContext(9001,2))})`,c.context);
  c.replyTo('/api/narrator/4864',{detail:'Unavailable'},false);await failed;
  const retry=descendants(c.nodes.get('#narrator-content')).find(n=>n?.textContent==='Ravi kaydını yeniden yükle');
  retry.focus();const retried=retry.handlers.click();c.replyTo('/api/narrator/4864',profile(4864));await retried;
  assert.equal(c.context.document.activeElement,c.nodes.get('#narrator-content'));
});

test('an unresolved source label retains its raw value and explicit non-person status',async()=>{
  const c=client(),context=sourceContext();context.members[3].label='914001';
  await openProfile(c,6817,context);
  const unresolved=descendants(c.nodes.get('#narrator-content')).find(n=>n?.className==='narrator-context-marker'&&flattened(n).includes('914001'));
  assert.ok(unresolved);assert.match(flattened(unresolved),/Çözümlenemeyen kaynak halkası/);
  assert.equal(unresolved.handlers.click,undefined);
});

test('withheld or unavailable components explain why while ordinary absence stays hidden',()=>{
  const c=client();
  function text(n){return [n.textContent||'',...(n.children||[]).map(text)].join(' ');}
  const cases=[
    ['source_binding_invalid',true,/kaynak bağı.*doğrulanamadı/i],
    ['multiple_source_versions_require_review',true,/birden çok kaynak sürümü/i],
    ['working_data_unavailable',false,/şu anda erişilemiyor/i]
  ];
  for (const [blocker,available,reason] of cases){
    vm.runInContext(`renderComponents(${JSON.stringify({available,items:[],hadith_core_complete:false,blockers:[blocker]})})`,c.context);
    assert.equal(c.nodes.get('#components-section').hidden,false,blocker);
    assert.match(text(c.nodes.get('#components-content')),reason);
    assert.doesNotMatch(text(c.nodes.get('#components-content')),/karşılaştırıldı|tamamlandı/);
  }
  vm.runInContext("renderComponents({available:true,items:[],hadith_core_complete:false,blockers:['no_component_review']})",c.context);
  assert.equal(c.nodes.get('#components-section').hidden,true);
  assert.equal(c.nodes.get('#components-content').children.length,0);
});

test('shared record link is canonical and omits the search and research context',()=>{
  const c=client();
  vm.runInContext("location.origin='https://reader.example';location.pathname='/research';location.search='?hadith=146_1&q=private&book_id=158';location.hash='#sanad-list';state.hadith={bhid:'146_1'};state.translation='en';",c.context);
  assert.equal(vm.runInContext('recordLink()',c.context),'https://reader.example/hadith/146_1?translation=en#sanad-list');
  vm.runInContext("state.translation='tr';location.hash='#unrelated';",c.context);
  assert.equal(vm.runInContext('recordLink()',c.context),'https://reader.example/hadith/146_1');
});

test('no record link is manufactured without a loaded record',()=>{
  const c=client();vm.runInContext('state.hadith=null;',c.context);
  assert.equal(vm.runInContext('recordLink()',c.context),null);
});

test('component-only translations are not followed by a claim that no Turkish candidate exists',()=>{
  const c=client();
  vm.runInContext("renderTranslations({available:true,total:0,items:[]},true)",c.context);
  function text(n){return [n.textContent||'',...(n.children||[]).map(text)].join(' ');}
  const message=text(c.nodes.get('#translations-content'));
  assert.doesNotMatch(message,/Türkçe çeviri adayı henüz bulunmuyor/);
  assert.match(message,/Türkçe bölümler/);
});

test('a delayed page cannot append chains after changing the hadith',async()=>{
  const c=client();
  const pending=c.run();
  vm.runInContext("state.hadith={bhid:'146_1'}; state.job++; state.sanadOffset=0;",c.context);
  c.reply({total:374,offset:20,items:[{sanad_id:999,source_judgement:{code:0,label:'صحيح'},members:[]}]});
  await pending;
  assert.equal(c.nodes.get('#sanad-list')?.children.length || 0,0);
  assert.equal(vm.runInContext('state.sanadOffset',c.context),0);
});

test('opinion cards retain Arabic, draft provenance and retryable race-safe paging',async()=>{
  const c=client();
  vm.runInContext(`
    narratorJob=7;
    var opinionFixture={alem_id:'924',critic:'عبد الرحمن',opinion:'تسع عشرة سنة',source_occurrences:2,
      localization:{available:true,language:'tr',complete:false,conflicting_fields:[],pending_fields:['critic','opinion'],
       fields:{opinion:[{text:'On dokuz yıl',status:'needs_review',rendering_kind:'translation',translation_origin:'assistant_translation',
         turkish_availability:'partial_support',expert_reviewed:false,rationale:'Kaynak atfı korunur.',
         sources:[{url:'https://example.org/source',title:'Deneme kaynağı',locator:'s.1',support_scope:'supports_part_of_field',evidence_note:'Yalnız tarih bilgisi.'}]}]}}};
    renderOpinions({id:4698,opinions:[opinionFixture],opinions_total:3},document.querySelector('#opinion-test'),7);
  `,c.context);
  const root=c.nodes.get('#opinion-test');
  function flatten(node){return [node.textContent||'',...(node.children||[]).map(flatten)].join(' ');}
  assert.match(flatten(root),/عبد الرحمن/);
  assert.match(flatten(root),/تسع عشرة سنة/);
  assert.match(flatten(root),/On dokuz yıl/);
  assert.match(flatten(root),/Asistanın Arapçadan çeviri taslağı/);
  assert.match(flatten(root),/Asistan incelemesi bekliyor/);
  assert.match(flatten(root),/Bu kaynağın desteği: yalnız alanın bir kısmı/);
  assert.match(flatten(root),/Yalnız tarih bilgisi/);
  const next=root.children.at(-1);
  const pending=next.handlers.click();
  const requests=c.urls.length;
  await next.handlers.click();
  assert.equal(c.urls.length,requests);
  c.reply({detail:'Temporary error'},false);
  await pending;
  assert.equal(next.disabled,false);
  const retry=next.handlers.click();
  assert.match(c.urls.at(-1),/4698\/opinions\?offset=1$/);
  vm.runInContext('narratorJob=8',c.context);
  c.reply({total:3,offset:1,items:[{...vm.runInContext('opinionFixture',c.context),opinion:'YANLIŞ ESKİ PENCERE'}]});
  await retry;
  assert.doesNotMatch(flatten(root),/YANLIŞ ESKİ PENCERE/);
});

test('a failed page retries the same offset and prevents simultaneous requests',async()=>{
  const c=client();
  const pending=c.run();
  const requests=c.urls.length;
  // A rapid second click must not create a second request.
  const duplicate=c.run();
  assert.equal(c.urls.length,requests);
  c.reply({detail:'Temporary error'},false);
  await pending;
  await duplicate;
  assert.equal(vm.runInContext('state.sanadOffset',c.context),0);
  const retry=c.run();
  assert.match(c.urls.at(-1),/offset=20$/);
  c.reply({total:374,offset:20,items:[]});
  await retry;
  assert.equal(vm.runInContext('state.sanadOffset',c.context),20);
});

test('translation candidates disclose editorial or commentary material',()=>{
  const c=client();
  vm.runInContext(`renderTranslations({available:true,total:1,items:[{source_key:'3',namespace:'fawaz:tur-muslim',
    provider:'fawazahmed0',revision:'pinned',display_text:'Hadis metni. NEVEVİ ŞERHİ: Açıklama.',
    review:{status:'needs_review'},evidence:{v2:{arabic_comparison:'same_tokens_after_orthographic_folding',
    translation_flags:['contains_editorial_or_navigation_text']}}}]});`,c.context);
  function flatten(node){return [node.textContent||'',...(node.children||[]).map(flatten)].join(' ');}
  assert.match(flatten(c.nodes.get('#translations-content')),/tahriç veya şerh içerebilir/);
  assert.match(flatten(c.nodes.get('#translations-content')),/ayrımı inceleme bekliyor/);
});

test('chain vocabulary renderings disclose automatic origin without claiming personal review',()=>{
  const c=client();
  vm.runInContext(`renderSanads({total:1,offset:0,items:[{sanad_id:1,source_judgement:{code:0,label:'صحيح',label_tr:'Sahih'},
    members:[{position:0,kind:'narrator',source_id:1,label:'اسم',source_rank:'ثقة',localization:{conflicting_fields:[],
      fields:{wasf_rotba:[{text:'Sika (güvenilir).',status:'needs_review',translation_origin:'controlled_vocabulary',actor_kind:'automated_check'}]}}}]}]});`,c.context);
  function flatten(node){return [node.textContent||'',...(node.children||[]).map(flatten)].join(' ');}
  const text=flatten(c.nodes.get('#sanad-list'));
  assert.match(text,/ثقة/);
  assert.match(text,/Sika \(güvenilir\)/);
  assert.match(text,/Terim sözlüğü/);
  function all(node){return [node,...(node.children||[]).flatMap(all)];}
  assert.ok(all(c.nodes.get('#sanad-list')).some(n=>/Otomatik terim karşılığı; kişiye özgü kaynak incelemesi bekliyor/.test(n.title||'')));
});

test('an unresolved empty source member stays visibly missing and is never named as a person',()=>{
  const c=client();
  vm.runInContext(`renderSanads({total:1,offset:0,items:[{sanad_id:639097,source_judgement:{code:-1,label:'',label_tr:''},
    members:[{position:0,kind:'unresolved',source_id:null,source_value:'',label:'',name:null,source_rank:null}]}]});`,c.context);
  function all(node){return [node,...(node.children||[]).flatMap(all)];}
  const nodes=all(c.nodes.get('#sanad-list'));
  assert.match(nodes.map(n=>n.textContent||'').join(' '),/Kaynakta ravi kimliği yok/);
  assert.match(nodes.map(n=>n.title||'').join(' '),/ravi eklenmedi/);
});

test('completed assistant comparisons do not claim expert certification',()=>{
  const c=client();
  vm.runInContext(`renderLocalization({wasf_rotba:'ثقة',localization:{available:true,language:'tr',pending_fields:[],conflicting_fields:[],
    fields:{wasf_rotba:[{text:'Sika (güvenilir).',status:'source_compared',rendering_kind:'translation',expert_reviewed:false,
    translation_origin:'assistant_reviewed_translation',turkish_availability:'source_support_found',sources:[],rationale:'Arapça alan karşılaştırıldı.'}]}}},
    document.querySelector('#review-test'));`,c.context);
  function flatten(node){return [node.textContent||'',...(node.children||[]).map(flatten)].join(' ');}
  const text=flatten(c.nodes.get('#review-test'));
  assert.match(text,/Asistan kaynak karşılaştırması/);
  assert.match(text,/Arapça aslıyla karşılaştırılmış asistan aktarımı/);
  assert.doesNotMatch(text,/Uzman incelemesi/);
});

test('a corrected source reading is explicitly labelled in Turkish',()=>{
  const c=client();
  vm.runInContext(`renderLocalization({wasf_rotba:'ثقة ثبتت حجة',localization:{available:true,language:'tr',pending_fields:[],conflicting_fields:[],
    fields:{wasf_rotba:[{text:'Sika; sebt; hüccet.',status:'source_compared',rendering_kind:'translation',expert_reviewed:false,
    translation_origin:'assistant_source_corrected_rendering',turkish_availability:'source_support_found',
    sources:[{url:'https://example.test/taqrib',title:'Arapça kaynak',locator:'s.158',support_scope:'arabic_source_comparison'}],
    rationale:'Yazım farkı ayrı Arapça şahit ile açıklandı.'}]}}},
    document.querySelector('#correction-test'));`,c.context);
  function flatten(node){return [node.textContent||'',...(node.children||[]).map(flatten)].join(' ');}
  const text=flatten(c.nodes.get('#correction-test'));
  assert.match(text,/Kaynak yazımı açıklanarak yapılan asistan aktarımı/);
  assert.match(text,/ثقة ثبتت حجة/);
  assert.match(text,/Arapça karşılaştırma kaynağı; yayımlanmış Türkçe çeviri değildir/);
  assert.doesNotMatch(text,/Uzman incelemesi/);
});

test('hadith review details show decisions and safely render old and structured sources',()=>{
  const c=client();
  vm.runInContext(`renderTranslations({available:true,total:1,items:[{source_key:'6',namespace:'fawaz:tur-bukhari',provider:'fawazahmed0',revision:'pinned',
    display_text:'Preserved original translation',review:{status:'problem_detected',events:[
      {dimension:'notes_separation',outcome:'fail',actor_kind:'assistant_source_review',rationale:'<img src=x onerror=alert(1)> Notlar karışmış.',sources:[
        {url:'https://example.test/book',title:'Kaynak kitap',locator:'s. 9'},
        {url:'javascript:alert(1)',title:'Unsafe source',locator:'legacy'},
        {url:'gk45:hadith:146_5',title:'Arapça asıl',locator:'146_5'},'Old source reference']},
      {dimension:'translation_completeness',outcome:'pending',rationale:'Üst sened eksik.',sources:[]}
    ]}}]});`,c.context);
  function all(n){return [n,...(n.children||[]).flatMap(all)];}
  const nodes=all(c.nodes.get('#translations-content'));
  const text=nodes.map(n=>n.textContent||'').join(' ');
  assert.match(text,/İnceleme ayrıntıları/);
  assert.match(text,/Asistan kaynak incelemesi/);
  assert.match(text,/Metin ve açıklama ayrımı/);
  assert.match(text,/Sorun saptandı/);
  assert.match(text,/Çeviri bütünlüğü/);
  assert.match(text,/İnceleme açık/);
  assert.match(text,/<img src=x onerror=alert\(1\)> Notlar karışmış/);
  assert.match(text,/Old source reference/);
  assert.match(text,/s\. 9/);
  assert.ok(nodes.some(n=>n.href==='https://example.test/book'));
  assert.ok(!nodes.some(n=>n.href?.startsWith('javascript:')||n.href?.startsWith('gk45:')));
  assert.ok(nodes.every(n=>!n.innerHTML));
  assert.match(text,/Preserved original translation/);
});

test('English source count remains selected while Turkish data arrives or is retried',async()=>{
  const c=client();readerLocation(c);
  const selected=vm.runInContext("selectTranslation('en')",c.context);
  vm.runInContext('renderTranslations({available:true,total:0,items:[]})',c.context);
  c.replyTo('/api/hadith/978_1/search-translations?language=en',{
    available:true,items:[{text:'Published English',edition:'eng-fixture',source_key:'1',source_url:'https://example.test/1',revision:'pin'}]});
  await selected;
  assert.equal(c.nodes.get('#translation-count').textContent,'1 kaynak');
  vm.runInContext('renderTranslations({available:false,total:0,items:[]})',c.context);
  assert.equal(c.nodes.get('#translation-count').textContent,'1 kaynak');
  await vm.runInContext("selectTranslation('tr')",c.context);
  assert.equal(c.nodes.get('#translation-count').textContent,'—');
  await vm.runInContext("selectTranslation('en')",c.context);
  assert.equal(c.nodes.get('#translation-count').textContent,'1 kaynak');
});

test('component-only Turkish count describes parts without claiming complete translations',()=>{
  const c=client();readerLocation(c);
  vm.runInContext("state.translation='tr';renderTranslations({available:true,total:0,items:[]})",c.context);
  const components=Array.from({length:2},(_,i)=>({id:String(i),kind:'matn',translation_text:'Kaynak bölümü '+i,
    status:'needs_review',origin:'assistant_translation',bibliography_ok:false,reviews:[]}));
  vm.runInContext(`renderComponents(${JSON.stringify({available:true,items:components,hadith_core_complete:false,blockers:[]})})`,c.context);
  assert.equal(c.nodes.get('#translation-count').textContent,'2 bölüm');
  assert.match(flattened(c.nodes.get('#components-content')),/kısmi olabilir/);
  assert.notEqual(c.nodes.get('#translation-count').textContent,'✓');
});

test('English unavailable state and retry never borrow a Turkish source count',async()=>{
  const c=client();readerLocation(c);
  vm.runInContext('renderTranslations({available:true,total:4,items:[]})',c.context);
  const request=vm.runInContext("selectTranslation('en')",c.context);
  c.replyTo('/api/hadith/978_1/search-translations?language=en',{available:false,items:[]});
  await request;
  assert.equal(c.nodes.get('#translation-count').textContent,'—');
  assert.match(flattened(c.nodes.get('#english-content')),/erişilemiyor/);
});

test('an unavailable English index retries in place and caches genuine empty results',async()=>{
  const c=client();readerLocation(c);
  const request=vm.runInContext("selectTranslation('en')",c.context);
  c.replyTo('/api/hadith/978_1/search-translations?language=en',{available:false,items:[]});
  await request;
  const retry=descendants(c.nodes.get('#english-content')).find(n=>n.textContent==='Yeniden dene');
  assert.ok(retry,'Temporary index unavailability needs a retry control');
  const pending=retry.handlers.click(),requests=c.urls.length;
  await retry.handlers.click();
  assert.equal(c.urls.length,requests,'A retry already loading cannot start twice');
  c.replyTo('/api/hadith/978_1/search-translations?language=en',{available:true,items:[]});
  await pending;
  assert.equal(c.nodes.get('#translation-count').textContent,'0 kaynak');
  assert.doesNotMatch(flattened(c.nodes.get('#english-content')),/erişilemiyor|Yeniden dene/);
  await vm.runInContext("selectTranslation('tr')",c.context);
  await vm.runInContext("selectTranslation('en')",c.context);
  assert.equal(c.urls.length,requests,'A successful empty result stays cached');
});

test('printed partial chains disclose only the current pending page and keep exact coverage',()=>{
  const c=client();readerLocation(c);
  vm.runInContext(`
    state.hadith={bhid:'978_1',internal_number:1,sanad_count:24,book:{name:'مصدر'},citation:{}};
    sanadComparison={bhid:'978_1',rows:Array(20).fill({}),total:24,open:false};
    document.querySelector('#translations-panel').classList.contains=()=>true;
    document.querySelector('#sanad-page-error').hidden=true;
    var printClone=document.querySelector('#print-clone-fixture'); printClone.querySelectorAll=()=>[];
    document.querySelector('#sanad-list').cloneNode=()=>printClone;
    pendingSanadJob={job:state.job,attempt:auxiliaryAttempt};
    preparePrintView();
  `,c.context);
  const output=()=>flattened(c.nodes.get('#print-view'));
  assert.match(output(),/Yüklenen sened: 20 \/ 24/);
  assert.match(output(),/Ek sened sayfası yükleniyor/);
  vm.runInContext('pendingSanadJob=null;preparePrintView()',c.context);
  assert.doesNotMatch(output(),/Ek sened sayfası yükleniyor/);
  vm.runInContext('pendingSanadJob={job:state.job-1,attempt:auxiliaryAttempt};preparePrintView()',c.context);
  assert.doesNotMatch(output(),/Ek sened sayfası yükleniyor/);
  vm.runInContext('pendingSanadJob={job:state.job,attempt:auxiliaryAttempt-1};preparePrintView()',c.context);
  assert.doesNotMatch(output(),/Ek sened sayfası yükleniyor/);
  vm.runInContext(`pendingSanadJob=null;document.querySelector('#sanad-page-error').hidden=false;
    document.querySelector('#sanad-page-error').textContent='Ek senedler yüklenemedi.';preparePrintView()`,c.context);
  assert.match(output(),/Ek senedler yüklenemedi/);
});

test('source links reject executable and credential-bearing URLs while preserving literal labels',()=>{
  const c=client();
  for(const url of ['javascript:alert(1)','data:text/html,<script>alert(1)</script>','https://name:secret@example.test/book']){
    c.context.sourceUrl=url;
    const result=vm.runInContext("sourceLink({url:sourceUrl,title:'Kaynak <img src=x>',locator:'s.1'})",c.context);
    assert.equal(result.href,undefined);
    assert.match(result.textContent,/Kaynak <img src=x>/);
    assert.equal(result.innerHTML,undefined);
  }
  const link=vm.runInContext("sourceLink({url:'https://example.test/book',title:'Kitap',locator:'s.1'})",c.context);
  assert.equal(link.href,'https://example.test/book');
  assert.equal(link.rel,'noopener noreferrer');
});

function stalledCore(c,body=false){
  readerLocation(c);let expires;const requests=[];
  c.context.setTimeout=(fn,ms)=>{if(ms===10000)expires=fn;return -1;};
  c.context.clearTimeout=()=>{};
  c.context.fetch=(url,options)=>{requests.push({url,signal:options?.signal});
    return body ? Promise.resolve({ok:true,json:()=>new Promise(()=>{})}) : new Promise(()=>{});};
  return {requests,expire(){assert.ok(expires,'Core fetch/body needs an application deadline');expires();}};
}

test('never-ending core transport exposes retry after its own deadline',async()=>{
  const c=client(),clock=stalledCore(c);
  const request=vm.runInContext("loadHadith('146_2',false)",c.context);
  clock.expire();await request;
  assert.equal(clock.requests[0].signal.aborted,true);
  assert.equal(c.nodes.get('#retry-hadith').hidden,false);
  assert.match(c.nodes.get('#error-banner').textContent,/yeniden/i);
  assert.equal(vm.runInContext('state.hadith',c.context),null);
  const retry=c.nodes.get('#retry-hadith').handlers.click();
  assert.equal(clock.requests[1].url,'/api/hadith/146_2');clock.expire();await retry;
});

test('core deadline also bounds a JSON body that ignores abort signals',async()=>{
  const c=client(),clock=stalledCore(c,true);
  const request=vm.runInContext("loadHadith('146_2',false)",c.context);
  await Promise.resolve();await Promise.resolve();clock.expire();await request;
  assert.equal(c.nodes.get('#retry-hadith').hidden,false);
  assert.equal(vm.runInContext('state.loadingHadith',c.context),null);
});

test('new core navigation aborts the old request without replacing its loading state',async()=>{
  const c=client(),clock=stalledCore(c);
  const first=vm.runInContext("loadHadith('146_2',false)",c.context);
  const second=vm.runInContext("loadHadith('146_3',false)",c.context);
  assert.equal(clock.requests[0].signal?.aborted,true);
  assert.equal(clock.requests[1].signal?.aborted,false);
  await first;
  assert.equal(vm.runInContext('state.loadingHadith',c.context),'146_3');
  assert.equal(c.nodes.get('#retry-hadith').hidden,true);
  clock.expire();await second;
  assert.match(c.nodes.get('#error-banner').textContent,/146_3/);
});

test('the auxiliary deadline rejects even a non-cooperative JSON body',async()=>{
  const c=client();let expire;
  c.context.setTimeout=(fn,ms)=>{assert.equal(ms,8000);expire=fn;return -1;};c.context.clearTimeout=()=>{};
  c.context.fetch=async()=>({ok:true,json:()=>new Promise(()=>{})});
  const result=vm.runInContext("getAuxiliary('/fixture')",c.context);
  await Promise.resolve();await Promise.resolve();expire();
  await assert.rejects(Promise.race([result,new Promise((_,reject)=>setTimeout(()=>reject(new Error('Deadline did not settle')),30))]),error=>error.message!=='Deadline did not settle');
});

test('legacy navigation is separate from the reading text and original remains literal',()=>{
  const c=client();const original='<img src=x onerror=alert(1)> Kaynak metni. İzah için buraya tıklayın';
  const row={source_key:'1',namespace:'fawaz:tur-fixture',provider:'fawazahmed0',revision:'pin',display_text:original,
    presentation:{text:'<img src=x onerror=alert(1)> Kaynak metni.',navigation_note:'İzah için buraya tıklayın'},review:{status:'needs_review'}};
  vm.runInContext(`renderTranslations(${JSON.stringify({available:true,total:1,items:[row]})})`,c.context);
  const nodes=descendants(c.nodes.get('#translations-content'));
  assert.equal(nodes.find(n=>n.className==='translation-text').textContent,row.presentation.text);
  assert.equal(nodes.find(n=>n.className==='original-source-body').textContent,original);
  assert.equal(nodes.find(n=>n.className==='source-navigation-note').textContent,row.presentation.navigation_note);
  assert.ok(nodes.every(n=>!n.innerHTML));
  row.presentation.text='Unrelated text';
  vm.runInContext(`renderTranslations(${JSON.stringify({available:true,total:1,items:[row]})})`,c.context);
  assert.equal(descendants(c.nodes.get('#translations-content')).find(n=>n.className==='translation-text').textContent,original);
});
