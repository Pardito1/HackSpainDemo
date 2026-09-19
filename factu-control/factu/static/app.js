const csrf=document.querySelector('meta[name="csrf-token"]').content;
let toastTimer;function toast(message){const t=document.getElementById('toast');clearTimeout(toastTimer);t.textContent=message;t.hidden=false;toastTimer=setTimeout(()=>t.hidden=true,9000);}
async function api(url,body){let response;try{response=await fetch(url,{method:'POST',headers:{'X-CSRF-Token':csrf,...(body instanceof FormData?{}:{'Content-Type':'application/json'})},body:body instanceof FormData?body:JSON.stringify(body||{})});}catch{throw Error('No se puede conectar con la aplicación. Comprueba que está encendida y vuelve a intentarlo.');}const raw=await response.text();let value;try{value=JSON.parse(raw);}catch{throw Error(`El servidor devolvió una respuesta no válida (${response.status}). No des por guardado el cambio; recarga y comprueba su estado.`);}if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail||value));return value;}
document.querySelectorAll('[data-toggle]').forEach(b=>b.addEventListener('click',()=>{const p=document.getElementById(b.dataset.toggle);p.hidden=!p.hidden;document.querySelectorAll(`[data-toggle="${b.dataset.toggle}"]`).forEach(t=>t.setAttribute('aria-expanded',String(!p.hidden)));if(!p.hidden)p.querySelector('input,select,textarea,button')?.focus();}));
document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;working(true);try{await api(`/api/batches/${b.dataset.batch}/${b.dataset.action}`);toast('Trabajo iniciado. Puedes seguir su estado en la bandeja.');poll(b.dataset.batch);}catch(e){working(false);toast(e.message);}finally{b.disabled=false;}}));
const ingest=document.getElementById('ingest-form');if(ingest)ingest.addEventListener('submit',async e=>{e.preventDefault();const b=ingest.querySelector('button');b.disabled=true;try{const r=await api('/api/batches',new FormData(ingest));location.href='/?batch='+r.batch_id;}catch(e){toast(e.message);b.disabled=false;}});
// Mientras hay un trabajo en marcha las cifras de la pantalla son las de antes
// de empezar: `readable.css` las atenúa en vez de dejarlas pasar por buenas.
function working(on){document.body.classList.toggle('working',on);}
let pollTimer;async function poll(batch){clearTimeout(pollTimer);try{const response=await fetch(`/api/batches/${batch}/status`);if(!response.ok)throw Error('estado');const r=await response.json();working(!!r.run.active);const status=document.getElementById('run-status');if(status){status.hidden=false;status.textContent=r.run.active?`${r.run.task}: ${r.metrics.decisions} decisiones, ${r.metrics.pending} pendientes.`:r.run.error||'Trabajo completado.';}if(r.run.error){toast(r.run.error);return;}if(r.run.active)pollTimer=setTimeout(()=>poll(batch),1800);else location.reload();}catch(e){working(false);toast('No se puede consultar el estado. Los trabajos conservan su último checkpoint.');}}
const pageSelect=document.getElementById('page-select');const paper=document.querySelector('.paper');const evidence=document.getElementById('evidence-box');const pageImage=document.getElementById('page-image');
function changePage(number){if(!paper)return;pageSelect.value=String(number);pageImage.src=`/api/documents/${paper.dataset.document}/pages/${number}`;evidence.hidden=true;}
if(pageSelect)pageSelect.addEventListener('change',()=>changePage(pageSelect.value));
document.querySelectorAll('button.evidence').forEach(button=>button.addEventListener('click',()=>{changePage(button.dataset.page);const option=pageSelect.selectedOptions[0];const box=JSON.parse(button.dataset.bbox);evidence.style.left=100*box[0]/Number(option.dataset.width)+'%';evidence.style.top=100*box[1]/Number(option.dataset.height)+'%';evidence.style.width=100*(box[2]-box[0])/Number(option.dataset.width)+'%';evidence.style.height=100*(box[3]-box[1])/Number(option.dataset.height)+'%';evidence.hidden=false;paper.scrollIntoView({behavior:'smooth',block:'center'});}));
document.querySelectorAll('.review-form').forEach(form=>{
  let pending=null;const preview=form.querySelector('.preview'),commit=form.querySelector('.commit'),submit=form.querySelector('[type=submit],button:not([type])');
  const resetPreview=()=>{pending=null;commit.hidden=true;preview.hidden=true;};
  const read=()=>{const data=new FormData(form);return {document_ids:form.dataset.document?[form.dataset.document]:data.getAll('document_ids'),field:data.get('field'),value:data.get('value'),actor:data.get('actor'),reason:data.get('reason')};};
  form.addEventListener('input',resetPreview);
  form.addEventListener('submit',async e=>{
    e.preventDefault();resetPreview();submit.disabled=true;const body=read();
    try{const r=await api('/api/reviews/preview',body);
      if(JSON.stringify(read())!==JSON.stringify(body)){toast('Has cambiado la corrección. Comprueba su efecto de nuevo.');return;}
      pending={...body,preview_token:r.preview_token};
      preview.textContent=r.previews.map(p=>`${p.file_id}\nAntes: ${resultLabels[p.before]||'Pendiente de comprobar'}\nDespués: ${resultLabels[p.after]||'Pendiente de comprobar'}\n${p.remaining_questions.join('\n')}\n\nGuardar el dato no registra una aprobación de pago.`).join('\n\n');preview.hidden=false;commit.hidden=false;
    }catch(e){toast(e.message);}finally{submit.disabled=false;}
  });
  commit.addEventListener('click',async()=>{if(!pending)return;commit.disabled=true;try{await api('/api/reviews/commit',pending);location.reload();}catch(e){toast(e.message);commit.disabled=false;}});
});

const resultLabels={PAGAR:'Propuesta de pago',NO_PAGAR:'No pagar',ESCALAR:'Requiere revisión'};
document.querySelectorAll('.human-form').forEach(form=>{
  let pending=null;
  const preview=form.querySelector('.preview'),commit=form.querySelector('.commit'),submit=form.querySelector('[type=submit]');
  const resetPreview=()=>{pending=null;commit.hidden=true;preview.hidden=true;};
  const choices=form.querySelectorAll('[data-human-choice]'),fields=form.querySelector('.answer-fields'),result=form.querySelector('[name=result]');
  const actionLabels={PAGAR:'Aprobar para pago',NO_PAGAR:'No pagar'};
  choices.forEach(button=>button.addEventListener('click',()=>{
    if(button.disabled)return;
    resetPreview();result.value=button.dataset.humanChoice;
    choices.forEach(choice=>choice.setAttribute('aria-pressed',String(choice===button)));
    fields.hidden=false;fields.disabled=false;
    form.querySelector('.chosen-action').textContent=actionLabels[result.value];
    commit.textContent={PAGAR:'Confirmar aprobación para pago',NO_PAGAR:'Confirmar que no se pagará'}[result.value];
    fields.querySelector('[name=actor]').focus();
  }));
  form.addEventListener('input',resetPreview);
  form.addEventListener('submit',async event=>{
    event.preventDefault();resetPreview();
    if(!actionLabels[result.value]){toast('Elige primero qué quieres hacer con esta factura.');return;}
    submit.disabled=true;choices.forEach(b=>b.setAttribute('aria-busy','true'));
    const data=new FormData(form),body={result:data.get('result'),actor:data.get('actor'),reason:data.get('reason'),evidence:data.get('evidence'),acknowledged:data.getAll('acknowledged')};
    const submitted=JSON.stringify(body);
    try{const r=await api(`/api/documents/${form.dataset.document}/answer/preview`,body);
      const current=new FormData(form),live={result:current.get('result'),actor:current.get('actor'),reason:current.get('reason'),evidence:current.get('evidence'),acknowledged:current.getAll('acknowledged')};
      if(JSON.stringify(live)!==submitted){toast('Has cambiado tu respuesta. Compruébala de nuevo antes de guardarla.');return;}
      pending={...body,preview_token:r.preview_token};preview.textContent=`Vas a registrar: ${actionLabels[r.result]}\nA nombre de: ${r.actor}\nMotivo: ${r.reason}\nEvidencia: ${r.evidence}\n\nNo se ejecuta ningún pago. Confirma abajo para guardar esta decisión.`;preview.hidden=false;commit.hidden=false;
    }catch(e){toast(e.message);}finally{submit.disabled=false;choices.forEach(b=>b.removeAttribute('aria-busy'));}
  });
  commit.addEventListener('click',async()=>{if(!pending)return;commit.disabled=true;try{await api(`/api/documents/${form.dataset.document}/answer/commit`,pending);location.reload();}catch(e){toast(e.message);commit.disabled=false;}});
});
document.querySelectorAll('.retract-form').forEach(form=>form.addEventListener('submit',async event=>{
  event.preventDefault();const button=form.querySelector('[type=submit]');button.disabled=true;
  const data=new FormData(form);
  try{await api(`/api/documents/${form.dataset.document}/answer/retract`,{actor:data.get('actor'),reason:data.get('reason')});location.reload();}
  catch(e){toast(e.message);button.disabled=false;}
}));
function showChange(batch,id){const path=`/sources?batch=${encodeURIComponent(batch)}&change=${encodeURIComponent(id)}`;if(location.pathname+location.search===path)location.reload();else location.href=path+`#change-${encodeURIComponent(id)}`;}
function sourceMode(kind){
  const erp=kind==='erp',policy=kind==='policy';
  return {erp,policy,upload:!erp,accept:policy?'.json':'.xlsx',label:policy?'Archivo de reglas actualizado':'Excel actualizado',submit:erp?'Consultar ERP y ver facturas afectadas':'Ver facturas afectadas'};
}
function sourceRequest(data){
  const erp=data.get('kind')==='erp';
  return {endpoint:erp?'erp':'upload',body:erp?{actor:data.get('actor')||'',reason:data.get('reason')||''}:data};
}
document.querySelectorAll('.source-form').forEach(form=>{
  const kind=form.querySelector('[name=kind]'),file=form.querySelector('[name=file]'),confirmation=form.querySelector('.policy-confirm');
  const update=()=>{
    const mode=sourceMode(kind.value);
    file.accept=mode.accept;file.value='';file.disabled=!mode.upload;file.required=mode.upload;
    form.querySelector('.upload-label').hidden=!mode.upload;
    form.querySelector('[data-upload-label]').textContent=mode.label;
    form.querySelector('[data-erp-help]').hidden=!mode.erp;
    form.querySelector('[data-source-submit]').textContent=mode.submit;
    confirmation.hidden=!mode.policy;confirmation.disabled=!mode.policy;
    confirmation.querySelector('input').checked=false;confirmation.querySelector('input').required=mode.policy;
    form.querySelector('.policy-help').hidden=!mode.policy;
  };
  kind.addEventListener('change',update);update();
});
document.querySelectorAll('.source-form').forEach(form=>form.addEventListener('submit',async event=>{
  event.preventDefault();const button=form.querySelector('button[type=submit]');button.disabled=true;
  toast('Consultando las fuentes y calculando el alcance. Aún no se ha aplicado ningún cambio.');
  try{const request=sourceRequest(new FormData(form));
    const r=await api(`/api/batches/${form.dataset.batch}/changes/${request.endpoint}`,request.body);showChange(form.dataset.batch,r.id);
  }catch(e){toast(e.message);button.disabled=false;
    if(e.message.includes('norma del Excel ha cambiado')){
      const confirmation=form.querySelector('.policy-confirm');
      if(confirmation){confirmation.hidden=false;confirmation.disabled=false;confirmation.querySelector('input').required=true;
        const help=form.querySelector('.policy-help');help.hidden=false;help.textContent='El Excel también cambia la norma de pagos. Pide al equipo que revise la correspondencia con las reglas antes de confirmar.';}
    }
  }
}));
document.querySelectorAll('[data-commit-change]').forEach(button=>button.addEventListener('click',async()=>{
  button.disabled=true;try{const r=await api(`/api/changes/${button.dataset.commitChange}/commit`);showChange(r.batch_id,r.id);}catch(e){toast(e.message);button.disabled=false;}
}));
const costForm=document.getElementById('cost-form');if(costForm)costForm.addEventListener('submit',event=>{
  event.preventDefault();const data=new FormData(costForm),count=Number(costForm.dataset.documents);
  const output=document.getElementById('cost-result');output.hidden=false;
  if(!count){output.textContent='Añade un lote para calcular el coste por factura.';return;}
  const inputs=[count,Number(costForm.dataset.external),Number(data.get('hours')),Number(data.get('infra')),Number(costForm.dataset.human),Number(data.get('human'))];
  if(inputs.some(value=>!Number.isFinite(value)||value<0)){output.textContent='Introduce importes y tiempos válidos, iguales o mayores que cero.';return;}
  const total=inputs[1]+inputs[2]*inputs[3]+inputs[4]*inputs[5];
  if(!Number.isFinite(total)){output.textContent='Las cifras son demasiado grandes para calcular esta estimación.';return;}
  const money=value=>value.toLocaleString('es-ES',{style:'currency',currency:'EUR',minimumFractionDigits:4});
  output.textContent=`Estimación con tus tarifas: ${money(total)} en total · ${money(total/count)} por factura.\nIncluye ${Number(costForm.dataset.human).toFixed(1)} minutos humanos declarados y ${count} documentos. Las tarifas no se guardan.`;
});
