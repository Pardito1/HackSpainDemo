const csrf=document.querySelector('meta[name="csrf-token"]').content;
let toastTimer;function toast(message){const t=document.getElementById('toast');clearTimeout(toastTimer);t.textContent=message;t.hidden=false;toastTimer=setTimeout(()=>t.hidden=true,9000);}
async function api(url,body){let response;try{response=await fetch(url,{method:'POST',headers:{'X-CSRF-Token':csrf,...(body instanceof FormData?{}:{'Content-Type':'application/json'})},body:body instanceof FormData?body:JSON.stringify(body||{})});}catch{throw Error('No se puede conectar con la aplicación. Comprueba que está encendida y vuelve a intentarlo.');}const raw=await response.text();let value;try{value=JSON.parse(raw);}catch{throw Error(`El servidor devolvió una respuesta no válida (${response.status}). No des por guardado el cambio; recarga y comprueba su estado.`);}if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail||value));return value;}
document.querySelectorAll('[data-toggle]').forEach(b=>b.addEventListener('click',()=>{const p=document.getElementById(b.dataset.toggle);p.hidden=!p.hidden;}));
document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;try{await api(`/api/batches/${b.dataset.batch}/${b.dataset.action}`);toast('Trabajo iniciado. Puedes seguir su estado en la bandeja.');poll(b.dataset.batch);}catch(e){toast(e.message);}finally{b.disabled=false;}}));
const ingest=document.getElementById('ingest-form');if(ingest)ingest.addEventListener('submit',async e=>{e.preventDefault();const b=ingest.querySelector('button');b.disabled=true;try{const r=await api('/api/batches',new FormData(ingest));location.href='/?batch='+r.batch_id;}catch(e){toast(e.message);b.disabled=false;}});
let pollTimer;async function poll(batch){clearTimeout(pollTimer);try{const response=await fetch(`/api/batches/${batch}/status`);if(!response.ok)throw Error('estado');const r=await response.json();const status=document.getElementById('run-status');if(status){status.hidden=false;status.textContent=r.run.active?`${r.run.task}: ${r.metrics.decisions} decisiones, ${r.metrics.pending} pendientes.`:r.run.error||'Trabajo completado.';}if(r.run.error){toast(r.run.error);return;}if(r.run.active)pollTimer=setTimeout(()=>poll(batch),1800);else location.reload();}catch(e){toast('No se puede consultar el estado. Los trabajos conservan su último checkpoint.');}}
const pageSelect=document.getElementById('page-select');const paper=document.querySelector('.paper');const evidence=document.getElementById('evidence-box');const pageImage=document.getElementById('page-image');
function changePage(number){if(!paper)return;pageSelect.value=String(number);pageImage.src=`/api/documents/${paper.dataset.document}/pages/${number}`;evidence.hidden=true;}
if(pageSelect)pageSelect.addEventListener('change',()=>changePage(pageSelect.value));
document.querySelectorAll('button.evidence').forEach(button=>button.addEventListener('click',()=>{changePage(button.dataset.page);const option=pageSelect.selectedOptions[0];const box=JSON.parse(button.dataset.bbox);evidence.style.left=100*box[0]/Number(option.dataset.width)+'%';evidence.style.top=100*box[1]/Number(option.dataset.height)+'%';evidence.style.width=100*(box[2]-box[0])/Number(option.dataset.width)+'%';evidence.style.height=100*(box[3]-box[1])/Number(option.dataset.height)+'%';evidence.hidden=false;paper.scrollIntoView({behavior:'smooth',block:'center'});}));
document.querySelectorAll('.review-form').forEach(form=>{let pending=null;const preview=form.querySelector('.preview'),commit=form.querySelector('.commit');form.addEventListener('input',()=>{pending=null;commit.hidden=true;preview.hidden=true;});form.addEventListener('submit',async e=>{e.preventDefault();const data=new FormData(form);const body={document_ids:form.dataset.document?[form.dataset.document]:data.getAll('document_ids'),field:data.get('field'),value:data.get('value'),actor:data.get('actor'),reason:data.get('reason')};try{const r=await api('/api/reviews/preview',body);pending={...body,preview_token:r.preview_token};preview.textContent=r.previews.map(p=>`${p.file_id}: ${p.before||'pendiente'} → ${p.after||'pendiente'}\n${p.remaining_questions.join('\n')}`).join('\n\n');preview.hidden=false;commit.hidden=false;}catch(e){toast(e.message);}});commit.addEventListener('click',async()=>{if(!pending)return;commit.disabled=true;try{await api('/api/reviews/commit',pending);location.reload();}catch(e){toast(e.message);commit.disabled=false;}});});

const resultLabels={PAGAR:'Propuesta de pago',NO_PAGAR:'No pagar',ESCALAR:'Consultar a Alberto'};
document.querySelectorAll('.human-form').forEach(form=>{
  let pending=null;
  const preview=form.querySelector('.preview'),commit=form.querySelector('.commit'),submit=form.querySelector('[type=submit]');
  form.addEventListener('input',()=>{pending=null;commit.hidden=true;preview.hidden=true;});
  form.addEventListener('submit',async event=>{
    event.preventDefault();submit.disabled=true;
    const data=new FormData(form),body={result:data.get('result'),actor:data.get('actor'),reason:data.get('reason'),evidence:data.get('evidence'),acknowledged:data.getAll('acknowledged'),seconds:Number(data.get('minutes'))*60};
    try{const r=await api(`/api/documents/${form.dataset.document}/answer/preview`,body);pending={...body,preview_token:r.preview_token};preview.textContent=`Antes: ${resultLabels[r.before]}\nCon tu respuesta: ${resultLabels[r.result]}\n\nQuedará registrada a nombre de ${r.actor}, con tu motivo y la evidencia indicada. No se ejecuta ningún pago.`;preview.hidden=false;commit.hidden=false;}catch(e){toast(e.message);}finally{submit.disabled=false;}
  });
  commit.addEventListener('click',async()=>{if(!pending)return;commit.disabled=true;try{await api(`/api/documents/${form.dataset.document}/answer/commit`,pending);location.reload();}catch(e){toast(e.message);commit.disabled=false;}});
});
function showChange(batch,id){location.href=`/sources?batch=${encodeURIComponent(batch)}&change=${encodeURIComponent(id)}#change-${encodeURIComponent(id)}`;}
document.querySelectorAll('.source-form,.erp-change-form').forEach(form=>form.addEventListener('submit',async event=>{
  event.preventDefault();const button=form.querySelector('button[type=submit]');button.disabled=true;
  toast('Consultando las fuentes y calculando el alcance. Aún no se ha aplicado ningún cambio.');
  try{const data=new FormData(form),isERP=form.classList.contains('erp-change-form');const body=isERP?{actor:data.get('actor'),reason:data.get('reason')}:data;
    const r=await api(`/api/batches/${form.dataset.batch}/changes/${isERP?'erp':'upload'}`,body);showChange(form.dataset.batch,r.id);
  }catch(e){toast(e.message);button.disabled=false;}
}));
document.querySelectorAll('[data-commit-change]').forEach(button=>button.addEventListener('click',async()=>{
  button.disabled=true;try{const r=await api(`/api/changes/${button.dataset.commitChange}/commit`);showChange(r.batch_id,r.id);}catch(e){toast(e.message);button.disabled=false;}
}));
const costForm=document.getElementById('cost-form');if(costForm)costForm.addEventListener('submit',event=>{
  event.preventDefault();const data=new FormData(costForm),count=Number(costForm.dataset.documents);
  const output=document.getElementById('cost-result');output.hidden=false;
  if(!count){output.textContent='Añade un lote para calcular el coste por factura.';return;}
  const total=Number(costForm.dataset.external)+Number(data.get('hours'))*Number(data.get('infra'))+Number(costForm.dataset.human)*Number(data.get('human'));
  const money=value=>value.toLocaleString('es-ES',{style:'currency',currency:'EUR',minimumFractionDigits:4});
  output.textContent=`Estimación con tus tarifas: ${money(total)} en total · ${money(total/count)} por factura.\nIncluye ${Number(costForm.dataset.human).toFixed(1)} minutos humanos declarados y ${count} documentos. Las tarifas no se guardan.`;
});
