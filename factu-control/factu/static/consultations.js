/* Progressive disclosure: no external messages are sent by this page. */
const supplierCards = [...document.querySelectorAll('.supplier-card')];
supplierCards.forEach(card => card.addEventListener('toggle', () => {
  if (card.open) supplierCards.forEach(other => { if (other !== card) other.open = false; });
}));
const supplierSearch = document.getElementById('supplier-search');
const supplierPriority = document.getElementById('supplier-priority');
function supplierMatches(name, priority, query, selected) {
  const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es');
  return normalize(name).includes(normalize(query.trim())) && (!selected || priority === selected);
}
function filterSuppliers() {
  let count = 0;
  supplierCards.forEach(card => {
    const visible = supplierMatches(card.dataset.supplier, card.dataset.priority, supplierSearch.value, supplierPriority.value);
    card.hidden = !visible;
    if (!visible) card.open = false;
    count += Number(visible);
  });
  document.getElementById('supplier-filter-status').textContent = `${count} de ${supplierCards.length} proveedores`;
  document.getElementById('supplier-empty').hidden = count !== 0;
  document.getElementById('open-first-supplier').disabled = count === 0;
}
if (supplierSearch) {
  supplierSearch.addEventListener('input', filterSuppliers);
  supplierPriority.addEventListener('change', filterSuppliers);
  document.getElementById('open-first-supplier').addEventListener('click', () => {
    const first = supplierCards.find(card => !card.hidden);
    if (first) { first.open = true; first.scrollIntoView({behavior:'smooth', block:'start'}); first.querySelector('summary').focus(); }
  });
}
document.querySelectorAll('[data-copy-draft]').forEach(button => button.addEventListener('click', async () => {
  const editor = document.getElementById('draft-' + button.dataset.copyDraft);
  try { await navigator.clipboard.writeText(editor.value); toast('Borrador copiado. No se ha enviado ningún mensaje.'); }
  catch { editor.focus(); editor.select(); toast('Seleccionado el texto. Usa Copiar en tu equipo.'); }
}));
document.querySelectorAll('[data-download-draft]').forEach(button => button.addEventListener('click', () => {
  const editor = document.getElementById('draft-' + button.dataset.downloadDraft);
  const url = URL.createObjectURL(new Blob([editor.value], {type:'text/plain;charset=utf-8'}));
  const link = document.createElement('a'); link.href = url; link.download = 'consulta-proveedor.txt';
  document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast('Texto preparado para descargar. No se ha enviado al proveedor.');
}));
function supplierPreviewTable(previews) {
  const wrapper = document.createElement('div'); wrapper.className = 'tablewrap';
  const table = document.createElement('table'); const head = table.createTHead().insertRow();
  ['Factura','Campo','Antes','Confirmado','Evidencia','Resultado previsto'].forEach(label => {
    const th = document.createElement('th'); th.textContent = label; head.append(th);
  });
  const body = table.createTBody();
  previews.forEach(item => {
    const row = body.insertRow();
    [item.file_id, item.field, item.current || 'Sin confirmar', item.proposed, item.reference,
      (resultLabels[item.before] || 'Pendiente') + ' → ' + (resultLabels[item.after] || 'Pendiente')].forEach(value => {
        row.insertCell().textContent = value;
      });
  });
  wrapper.append(table); return wrapper;
}
document.querySelectorAll('.supplier-response-form').forEach(form => {
  let pending = null;
  const scope = form.querySelector('.response-scope'), verified = form.querySelector('[name=verified]');
  const preview = form.querySelector('.response-preview'), commit = form.querySelector('.commit'), submit = form.querySelector('[type=submit]');
  const required = ['response','reference','actor','value'].map(name => form.querySelector(`[name=${name}]`));
  const reset = () => { pending = null; preview.hidden = true; commit.hidden = true; };
  const update = () => {
    const ready = verified.checked && required.every(input => input.value.trim() && input.checkValidity());
    scope.hidden = !ready; scope.disabled = !ready;
    form.querySelectorAll('.proposed-currency').forEach(cell => cell.textContent = form.querySelector('[name=value]').value.trim().toUpperCase() || '—');
  };
  const read = () => {
    const data = new FormData(form);
    return {group_id:form.dataset.group, topic_id:form.dataset.topic, batch_id:form.dataset.batch || null,
      document_ids:data.getAll('document_ids'), value:data.get('value').trim().toUpperCase(), actor:data.get('actor'),
      response:data.get('response'), reference:data.get('reference'), verified:verified.checked};
  };
  form.addEventListener('input', event => { reset(); if (required.includes(event.target)) verified.checked = false; update(); });
  verified.addEventListener('change', () => { reset(); update(); if (verified.checked && scope.hidden) toast('Completa la respuesta, la referencia, tu nombre y la moneda antes de seleccionar facturas.'); });
  form.addEventListener('submit', async event => {
    event.preventDefault(); reset(); const body = read();
    if (!body.document_ids.length) { toast('Selecciona las facturas cubiertas por la respuesta.'); return; }
    submit.disabled = true;
    try {
      const result = await api('/api/consultations/response/preview', body);
      if (JSON.stringify(body) !== JSON.stringify(read())) { toast('La respuesta ha cambiado. Revisa su efecto de nuevo.'); return; }
      pending = {...body, preview_token:result.preview_token}; preview.replaceChildren(supplierPreviewTable(result.previews));
      const note = document.createElement('p'); note.textContent = 'Se confirmará la moneda y se recalculará cada expediente. No se registra una aprobación de pago.'; preview.append(note);
      preview.hidden = false; commit.hidden = false;
    } catch (error) { toast(error.message); } finally { submit.disabled = false; }
  });
  commit.addEventListener('click', async () => {
    if (!pending) return;
    commit.disabled = true;
    try { await api('/api/consultations/response/commit', pending); location.reload(); }
    catch (error) { reset(); toast(error.message); commit.disabled = false; }
  });
  update();
});
