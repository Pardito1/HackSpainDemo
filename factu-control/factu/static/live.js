// Pantalla «En vivo». Sondea /live cada 500 ms mientras el lote corre y cada
// 3 s en reposo. No recarga nunca: al terminar deja los números finales y el
// tiempo total en pantalla, que es lo que se enseña en la demo.
const root = document.getElementById('live');
if (root) {
  const batch = root.dataset.batch;
  // Etiqueta corta de la primera regla que no pasa: cabe en una línea de la
  // lista. El motivo completo está en /documents/{id}.
  const RULES = {
    document_instructions: 'orden sospechosa en el PDF',
    document_coverage: 'documento leído a medias',
    currency: 'moneda', supplier_identity: 'identidad del proveedor',
    iban_matches_master: 'IBAN del maestro',
    order_exists: 'pedido contable', order_supplier: 'proveedor del pedido',
    source_identity_conflict: 'Excel y ERP no coinciden',
    amount_matches_order: 'importe del pedido',
    tax_arithmetic: 'cálculo del IVA', total_arithmetic: 'total = base + IVA',
    invoice_date: 'fecha de emisión', erp_pending: 'pedido pendiente en el ERP',
    duplicate_obligation: 'pedido repetido',
    historical_order: 'pedido en el archivo histórico',
    order_read_by_model: 'pedido leído por el modelo',
  };
  const label = id => RULES[id] || (id?.startsWith('field:') ? 'falta ' + id.slice(6) : id);
  const METHODS = {texto: 'texto', ocr: 'OCR', modelo: 'modelo'};
  const $ = id => document.getElementById(id);
  const text = (id, value) => { const n = $(id); if (n) n.textContent = value; };
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let baselineWarnings = null, seen = new Set(), timer;

  // Conteo animado: el número sube en ~400 ms en vez de saltar. Con
  // prefers-reduced-motion el salto es inmediato.
  const counters = new Map();
  function count(node, target) {
    const from = counters.get(node) ?? (Number(node.textContent) || 0);
    counters.set(node, target);
    if (still || from === target) { node.textContent = target; return; }
    const t0 = performance.now();
    const step = t => {
      const k = Math.min(1, (t - t0) / 400);
      node.textContent = Math.round(from + (target - from) * k);
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  function paint(d) {
    const total = d.totals.documents || 1;
    const percent = Math.round(100 * d.totals.decided / total);
    $('live-fill').style.width = percent + '%';
    $('live-read').style.width = Math.round(100 * d.totals.extracted / total) + '%';
    $('live-bar').setAttribute('aria-valuenow', percent);
    $('live-bar').setAttribute('aria-valuetext', `${d.totals.extracted} leídas, ${d.totals.decided} decididas de ${d.totals.documents}`);
    count($('live-decided'), d.totals.decided);
    text('live-documents', d.totals.documents);
    text('live-pending', [
      `${d.totals.extracted} leídas`,
      `${d.totals.pending} sin decidir`,
      `${d.totals.running} en curso`,
      `${d.totals.human_review} en revisión humana`,
      ...(d.totals.failed ? [`${d.totals.failed} con error`] : []),
    ].join(' · '));
    text('live-task', d.run.task || 'En reposo');
    text('live-elapsed', d.run.elapsed_s.toFixed(1));
    $('live-dot').hidden = !d.run.active;
    $('live-process').disabled = d.run.active;
    root.classList.toggle('running', !!d.run.active);

    for (const [result, n] of Object.entries(d.results)) {
      count(root.querySelector(`[data-count="${result}"]`), n);
    }
    root.querySelectorAll('[data-stage]').forEach(li => {
      li.classList.toggle('on', d.pipeline.some(s => s.id === li.dataset.stage && s.active));
    });

    text('live-neurons', d.cost.neurons);
    text('live-eur', d.cost.external_eur.toFixed(4) + ' €');
    text('live-pages', d.cost.model_pages);
    text('live-throughput', d.throughput_docs_per_s === null ? '—' : d.throughput_docs_per_s.toFixed(2));
    $('live-stage-rows').replaceChildren(...Object.entries(d.stages).map(([stage, s]) => {
      const tr = document.createElement('tr');
      for (const value of [stage, s.count, s.p50_s.toFixed(3) + ' s', s.max_s.toFixed(3) + ' s']) {
        const td = document.createElement('td');
        td.textContent = value;
        tr.append(td);
      }
      return tr;
    }));

    const warnings = Object.entries(d.warnings);
    text('live-warnings', warnings.length
      ? 'Avisos registrados en la extracción: ' + warnings.map(([c, n]) => `${c} (${n})`).join(' · ')
      : 'Sin avisos registrados en la extracción.');
    // El indicador se enciende solo si el proveedor falla DURANTE este run:
    // los avisos que ya estaban al abrir la pantalla son historia, no noticia.
    // Si la pantalla se abre con el lote ya corriendo no hay historia que
    // descontar, así que cualquier aviso cuenta.
    const down = d.warnings.MODELO_NO_DISPONIBLE || 0;
    if (baselineWarnings === null) baselineWarnings = d.run.active ? 0 : down;
    $('live-provider').hidden = down <= baselineWarnings;

    const list = $('live-recent');
    for (const row of [...d.recent].reverse()) {
      const key = row.doc_id + ':' + row.result;
      if (seen.has(key)) continue;
      seen.add(key);
      const li = document.createElement('li');
      if (!still) li.className = 'enter';
      const link = document.createElement('a');
      link.href = '/documents/' + row.doc_id;
      link.textContent = row.file_id;
      const badge = document.createElement('span');
      badge.className = 'badge ' + row.result;
      badge.textContent = row.result;
      const why = document.createElement('small');
      why.textContent = [
        row.first_failed_rule ? 'falla ' + label(row.first_failed_rule) : 'todas las comprobaciones pasan',
        METHODS[row.method] || row.method,
        row.seconds.toFixed(2) + ' s',
      ].join(' · ');
      li.append(badge, link, why);
      list.prepend(li);
      while (list.children.length > 12) list.lastElementChild.remove();
    }
  }

  async function tick() {
    clearTimeout(timer);
    let active = false;
    try {
      const response = await fetch(`/api/batches/${batch}/live`);
      if (!response.ok) throw Error('estado');
      const data = await response.json();
      paint(data);
      active = data.run.active;
      if (data.run.error) toast(data.run.error);
    } catch {
      text('live-task', 'Sin conexión con la aplicación');
    }
    timer = setTimeout(tick, active ? 500 : 3000);
  }

  $('live-process').addEventListener('click', async () => {
    $('live-process').disabled = true;
    baselineWarnings = null;
    try {
      await api(`/api/batches/${batch}/process`);
      root.classList.add('running');
    } catch (e) {
      toast(e.message);
      $('live-process').disabled = false;
    }
    tick();
  });

  tick();
}
