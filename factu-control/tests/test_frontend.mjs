import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('../factu/static/app.js',import.meta.url),'utf8');
function client(fetch){
  const sandbox={fetch,FormData,document:{querySelector:()=>({content:'test'})}};
  vm.runInNewContext(source.slice(0,source.indexOf("document.querySelectorAll"))+';this.callAPI=api;',sandbox);
  return sandbox.callAPI;
}
test('Non-JSON error has a readable message, never a JSON parse exception',async()=>{
  await assert.rejects(client(async()=>new Response('Internal Server Error',{status:500}))('/test',{}),/respuesta no válida \(500\)/);
});
test('Network failure does not claim the change was saved',async()=>{
  await assert.rejects(client(async()=>{throw Error('offline')})('/test',{}),/No se puede conectar/);
});
test('JSON validation message is preserved',async()=>{
  await assert.rejects(client(async()=>Response.json({detail:'Excel dañado'},{status:400}))('/test',{}),/Excel dañado/);
});
test('Valid JSON response is returned',async()=>{
  assert.equal((await client(async()=>Response.json({accepted:true}))('/test',{})).accepted,true);
});

function navigate(location){
  const sandbox={location};
  const start=source.indexOf('function showChange(');
  const end=source.indexOf("document.querySelectorAll('.source-form')",start);
  vm.runInNewContext(source.slice(start,end)+';this.show=showChange;',sandbox);
  return sandbox.show;
}
test('Applying the current preview refreshes its saved status',()=>{
  let reloads=0;
  const location={pathname:'/sources',search:'?batch=abc&change=123',reload:()=>reloads++};
  navigate(location)('abc','123');
  assert.equal(reloads,1);
  assert.equal(location.href,undefined);
});
test('A new preview navigates to its own summary',()=>{
  const location={pathname:'/sources',search:'?batch=abc',reload:()=>assert.fail('Unexpected reload')};
  navigate(location)('abc','123');
  assert.equal(location.href,'/sources?batch=abc&change=123#change-123');
});

const sourceSandbox={};
vm.runInNewContext(source.slice(source.indexOf('function sourceMode('),source.indexOf("document.querySelectorAll('.source-form')"))+';this.mode=sourceMode;this.request=sourceRequest;',sourceSandbox);
test('ERP mode has no required upload or policy confirmation',()=>{
  const mode=sourceSandbox.mode('erp');
  assert.equal(mode.erp,true);assert.equal(mode.upload,false);assert.equal(mode.policy,false);
  assert.match(mode.submit,/Consultar ERP/);
});
test('Switching back to Excel or policy restores the matching upload',()=>{
  for(const kind of ['master','policy']){
    const mode=sourceSandbox.mode(kind);
    assert.equal(mode.upload,true);assert.equal(mode.erp,false);
    assert.equal(mode.accept,kind==='policy'?'.json':'.xlsx');
    assert.equal(mode.policy,kind==='policy');
  }
});
test('ERP uses JSON preview endpoint; files still use multipart upload',()=>{
  const data=new FormData();data.set('kind','erp');data.set('actor','Marta');data.set('reason','Revisión');
  const request=sourceSandbox.request(data);
  assert.equal(request.endpoint,'erp');
  assert.equal(JSON.stringify(request.body),JSON.stringify({actor:'Marta',reason:'Revisión'}));
  for(const kind of ['master','policy']){
    data.set('kind',kind);
    assert.equal(sourceSandbox.request(data).endpoint,'upload');
    assert.equal(sourceSandbox.request(data).body,data);
  }
});

const consultationSource=fs.readFileSync(new URL('../factu/static/consultations.js',import.meta.url),'utf8');
const matcherSandbox={};
vm.runInNewContext(consultationSource.slice(consultationSource.indexOf('function supplierMatches('),consultationSource.indexOf('function filterSuppliers('))+';this.matches=supplierMatches;',matcherSandbox);
test('Supplier search ignores accents and spaces',()=>{
  assert.equal(matcherSandbox.matches('Informática Benimámet B123','high',' informatica ',''),true);
  assert.equal(matcherSandbox.matches('Informática Benimámet B123','high','B123','high'),true);
});
test('Priority filter and text search combine without broadening results',()=>{
  assert.equal(matcherSandbox.matches('Proveedor A','high','Proveedor','normal'),false);
  assert.equal(matcherSandbox.matches('Proveedor A','high','Otro','high'),false);
  assert.equal(matcherSandbox.matches('Proveedor A','normal','','normal'),true);
});

function estimate({documents='10',external='1',minutes='20',hours='2',infra='3',human='0.5'}={}){
  const result={};let handler;
  const form={dataset:{documents,external,human:minutes},addEventListener:(_,fn)=>handler=fn};
  const sandbox={document:{getElementById:id=>id==='cost-form'?form:result},FormData:class{get(k){return {hours,infra,human}[k]}}};
  vm.runInNewContext(source.slice(source.indexOf("const costForm=")),sandbox);
  handler({preventDefault(){}});return result.textContent;
}
test('Cost estimate adds external, equipment and human time exactly once',()=>{
  assert.match(estimate(),/17,0000/);
  assert.match(estimate(),/1,7000/);
});
test('Cost estimate rejects nonfinite, negative and overflowing figures',()=>{
  for(const hours of ['Infinity','NaN','-1'])assert.match(estimate({hours}),/válidos/);
  assert.match(estimate({hours:'1e308',infra:'1e308'}),/demasiado grandes/);
});

// La pantalla «En vivo»: paint() con un DOM mínimo, que es donde vive la
// decisión de qué se enseña en cada sondeo.
const liveSource=fs.readFileSync(new URL('../factu/static/live.js',import.meta.url),'utf8');
function element(){
  const node={textContent:'',hidden:false,className:'',style:{},children:[],parent:null,
    classList:{toggle(){},add(){},remove(){}},setAttribute(){},
    append(...kids){for(const kid of kids){kid.parent=node;node.children.push(kid)}},
    prepend(kid){kid.parent=node;node.children.unshift(kid)},
    replaceChildren(...kids){for(const kid of node.children)kid.parent=null;node.children=kids},
    get lastElementChild(){return node.children[node.children.length-1]},
    remove(){if(node.parent)node.parent.children.splice(node.parent.children.indexOf(node),1)}};
  return node;
}
function screen(){
  const nodes={};
  const sandbox={still:true,counters:new Map(),METHODS:{},RULES:{},
    seen:new Set(),baseline:0,runStarted:undefined,
    label:id=>id,count:(node,value)=>{node.textContent=value},
    $:id=>nodes[id]??=element(),
    text:(id,value)=>{(nodes[id]??=element()).textContent=value},
    root:{classList:{toggle(){}},querySelector:()=>element(),querySelectorAll:()=>[]},
    document:{createElement:()=>element()}};
  vm.runInNewContext(liveSource.slice(liveSource.indexOf('function paint('),liveSource.indexOf('async function tick('))+';this.paint=paint;',sandbox);
  return {paint:sandbox.paint,nodes};
}
const reading=(started,warnings={})=>({
  run:{active:false,task:'Procesar',started,elapsed_s:1},
  totals:{documents:2,extracted:2,decided:2,pending:0,running:0,human_review:0,failed:0},
  results:{PAGAR:1,NO_PAGAR:0,ESCALAR:1},throughput_docs_per_s:2,stages:{},pipeline:[],
  cost:{neurons:0,external_eur:0,model_pages:0},warnings,
  recent:[{doc_id:'d1',file_id:'a.pdf',result:'PAGAR',first_failed_rule:null,seconds:1,method:'texto'},
          {doc_id:'d2',file_id:'b.pdf',result:'ESCALAR',first_failed_rule:'currency',seconds:1,method:'texto'}]});

test('Repeating a batch shows its decisions again instead of stale rows',()=>{
  const {paint,nodes}=screen();
  const list=()=>[...nodes['live-recent'].children];
  paint(reading('2026-09-19T20:00:00'));
  const first=list();
  assert.equal(first.length,2);
  paint(reading('2026-09-19T20:00:00'));
  assert.deepEqual(list(),first,'El mismo trabajo no repite filas ya enseñadas');
  // Un segundo trabajo sobre el mismo lote devuelve el mismo documento con el
  // mismo resultado: sin estrenar lista, sus filas serían las de antes.
  paint(reading('2026-09-19T21:00:00'));
  assert.equal(list().length,2);
  assert.notEqual(list()[0],first[0],'Un trabajo nuevo estrena lista');
});
test('Provider alert follows this job, not the warnings it inherited',()=>{
  const {paint,nodes}=screen();
  paint(reading('2026-09-19T20:00:00'));
  assert.equal(nodes['live-provider'].hidden,true);
  paint(reading('2026-09-19T20:00:00',{MODELO_NO_DISPONIBLE:3}));
  assert.equal(nodes['live-provider'].hidden,false,'El proveedor cae durante el trabajo');
  paint(reading('2026-09-19T21:00:00',{MODELO_NO_DISPONIBLE:3}));
  assert.equal(nodes['live-provider'].hidden,true,'Los avisos heredados son historia');
});
