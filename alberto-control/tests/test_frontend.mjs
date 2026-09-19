import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('../alberto/static/app.js',import.meta.url),'utf8');
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
