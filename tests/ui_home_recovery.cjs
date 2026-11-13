// Real home.js handlers with deterministic transport and timer boundaries.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function client() {
  const nodes=new Map(), pending=[], timers=new Map();let nextTimer=0;
  function node(tag='') {
    return {tagName:tag.toUpperCase(),value:'',children:[],handlers:{},attributes:{},dataset:{},
      classList:{add(){},remove(){}},
      get options(){return this.children;},get selectedOptions(){return this.children.filter(n=>n.value===this.value);},
      contains(other){return this===other || this.children.some(n=>n===other || n.contains?.(other));},
      append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},
      setAttribute(key,value){this.attributes[key]=String(value);},removeAttribute(key){delete this.attributes[key];},
      getAttribute(key){return this.attributes[key]??null;},
      addEventListener(event,fn){this.handlers[event]=fn;},
      scrollIntoView(){},focus(){document.activeElement=this;},click(){return this.handlers.click?.({preventDefault(){}});}};
  }
  const document={activeElement:null,querySelector(selector){if(!nodes.has(selector))nodes.set(selector,node());return nodes.get(selector);},
    querySelectorAll(){return [];},createElement:node,createTextNode:text=>({textContent:text})};
  document.querySelector('#home-search').elements={language:{value:'auto'}};
  const context=vm.createContext({document,URLSearchParams,AbortController,encodeURIComponent,
    location:{search:''},history:{replaceState(){}},window:{addEventListener(){}},
    setTimeout(fn,ms){const id=++nextTimer;timers.set(id,{fn,ms});return id;},clearTimeout(id){timers.delete(id);},
    fetch(url,options){return new Promise((resolve,reject)=>{
      const request={url,resolve,reject,signal:options.signal};pending.push(request);
      options.signal.addEventListener('abort',()=>reject(Object.assign(new Error('aborted'),{name:'AbortError'})),{once:true});
    });}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../hadis_web/static/home.js'),'utf8'),context);
  return {context,nodes,pending,timers,
    search(q,append=false){nodes.get('#home-query').value=q;return vm.runInContext(`search(${append})`,context);},
    reply(data,index=pending.length-1,ok=true){pending[index].resolve({ok,json:async()=>data});},
    expire(){const entry=[...timers].find(([,t])=>t.ms===8000);assert.ok(entry,'request deadline exists');timers.delete(entry[0]);entry[1].fn();},
    key(key){const event={key,preventDefault(){}};nodes.get('#home-query').handlers.keydown(event);return nodes.get('#home-main').handlers.keydown(event);}};
}
function page(offset=0,items=['146_1','146_2'],total=3){return {offset,total,available:true,books:[],items:items.map(bhid=>({bhid,book_name:'البخاري',language:'tr',snippet:'kaynak metni'}))};}

test('home search times out after8s and retries the same query instead of reporting zero results',async()=>{
  const c=client();const request=c.search('niyet');c.expire();await request;
  assert.match(c.nodes.get('#search-status').textContent,/sürdü|süre/);
  assert.equal(c.nodes.get('#home-retry').hidden,false);
  assert.equal(c.nodes.get('#suggestions').getAttribute('aria-busy'),'false');
  const retry=c.nodes.get('#home-retry').click();
  assert.equal(c.pending[0].url,c.pending[1].url);
  c.reply(page());await retry;
  assert.equal(c.nodes.get('#home-retry').hidden,true);
  assert.equal(c.nodes.get('#suggestions').children.length,2);
});

test('home page failure preserves source results and retries the same offset once',async()=>{
  const c=client();let request=c.search('niyet');c.reply(page());await request;
  c.key('ArrowDown');
  request=c.search('niyet',true);const before=c.pending.length;
  await c.search('niyet',true);assert.equal(c.pending.length,before);
  c.reply({},c.pending.length-1,false);await request;
  assert.equal(c.nodes.get('#suggestions').children.length,2);
  assert.equal(c.nodes.get('#home-query').getAttribute('aria-activedescendant'),null);
  assert.equal(c.nodes.get('#home-page-retry').hidden,false);
  const retry=c.nodes.get('#home-page-retry').click();
  assert.equal(c.pending.at(-1).url,c.pending.at(-2).url);
  assert.match(c.pending.at(-1).url,/offset=2/);
  c.reply(page(2,['146_3']));await retry;
  assert.equal(c.nodes.get('#suggestions').children.length,3);
});

test('Escape cancels pending search and late data cannot reopen suggestions',async()=>{
  const c=client();const request=c.search('niyet');c.key('Escape');
  c.reply(page());await request;
  assert.equal(c.nodes.get('#suggestion-panel').hidden,true);
  assert.equal(c.nodes.get('#home-query').getAttribute('aria-expanded'),'false');
  assert.equal(c.nodes.get('#suggestions').getAttribute('aria-busy'),'false');
});

test('first ArrowUp chooses the last source suggestion and first ArrowDown the first',async()=>{
  const c=client();const request=c.search('niyet');c.reply(page());await request;
  c.key('ArrowUp');
  assert.equal(c.nodes.get('#home-query').getAttribute('aria-activedescendant'),'suggestion-1');
  c.key('Escape');c.key('ArrowDown');
  assert.equal(c.nodes.get('#home-query').getAttribute('aria-activedescendant'),'suggestion-0');
});

test('old request deadline cannot abort a newer query or show a stale retry',async()=>{
  const c=client();const old=c.search('niyet');
  const oldDeadline=[...c.timers.values()].find(t=>t.ms===8000);assert.ok(oldDeadline);
  const current=c.search('mercy');oldDeadline.fn();await old;
  assert.equal(c.pending.at(-1).signal.aborted,false);
  c.reply(page());await current;
  assert.equal(c.nodes.get('#home-retry').hidden,true);
});

test('unavailable search index is retryable and stays distinct from genuine zero results',async()=>{
  const c=client();let request=c.search('niyet');c.reply({...page(0,[],0),available:false,message:'unavailable'});await request;
  assert.equal(c.nodes.get('#home-retry').hidden,false);
  request=c.nodes.get('#home-retry').click();c.reply(page(0,[],0));await request;
  assert.equal(c.nodes.get('#home-retry').hidden,true);
  assert.match(c.nodes.get('#search-status').textContent,/bulunamadı/);
});

test('search cards identify source records and disclose removed legacy navigation',async()=>{
  const c=client(),request=c.search('niyet');
  const response=page();response.items[0].record_label='Kaynak metni';response.items[0].source_navigation_present=true;
  c.reply(response);await request;
  const flatten=n=>[n.textContent||'',...(n.children||[]).map(flatten)].join(' ');
  const text=flatten(c.nodes.get('#suggestions').children[0]);
  assert.match(text,/Kaynak metni/);
  assert.match(text,/gezinme notu/i);
});
