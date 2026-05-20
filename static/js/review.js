const runId = new URLSearchParams(location.search).get('run_id');
let pollTimer = null;
let currentState = null;

const FIELD_LABELS = {
  vendor: 'Leverancier', invoice_number: 'Factuurnummer', invoice_date: 'Factuurdatum',
  due_date: 'Vervaldatum', amount_gross: 'Totaal incl. BTW', amount_vat: 'BTW-bedrag',
  vat_rate: 'BTW-tarief', amount_net: 'Subtotaal excl. BTW', currency: 'Valuta',
  description: 'Omschrijving', suggested_account_code: 'Rekening', kostenplaats: 'Kostenplaats',
};

// ── Polling ───────────────────────────────────────────────────────────────────
function startPolling() {
  pollTimer = setInterval(async () => {
    const res = await fetch(`/api/runs/${runId}/status`);
    if (!res.ok) { showError('Fout bij ophalen status.'); clearInterval(pollTimer); return; }
    const data = await res.json();
    if (data.phase === 'proposed') {
      clearInterval(pollTimer);
      hideSpinner();
      currentState = data;
      renderReview(data);
    } else if (data.phase === 'error') {
      clearInterval(pollTimer);
      hideSpinner();
      showError(data.error || 'Onbekende fout tijdens verwerking.');
    }
  }, 1500);
}

function hideSpinner() { document.getElementById('spinner-overlay').classList.add('hidden'); }
function showError(msg) {
  hideSpinner();
  document.getElementById('review-area').innerHTML =
    `<div class="result-banner error">Fout: ${msg} <a href="/" style="margin-left:auto">← Terug naar inbox</a></div>`;
}

// ── Render ────────────────────────────────────────────────────────────────────
function confClass(c) { return c >= 0.95 ? '' : c >= 0.80 ? 'medium' : 'low'; }

function confBar(c) {
  const cls = confClass(c);
  const pct = Math.round(c * 100);
  return `<div class="conf-wrap">
    <div class="conf-bar"><div class="conf-fill ${cls}" style="width:${pct}%"></div></div>
    <span class="conf-text">${pct}%${c < 0.80 ? ' ⚠' : ''}</span>
  </div>`;
}

function renderFields(fields) {
  const order = ['vendor','invoice_number','invoice_date','due_date','amount_gross','amount_vat','vat_rate','amount_net','currency','description','suggested_account_code','kostenplaats'];
  let rows = '';
  order.forEach(key => {
    const f = fields[key];
    if (!f) return;
    const val = f.value !== null && f.value !== undefined ? f.value : '—';
    const lowCls = f.confidence < 0.80 ? ' class="low-confidence"' : '';
    rows += `<tr${lowCls}>
      <td>${FIELD_LABELS[key] || key}</td>
      <td class="text-mono">${val}</td>
      <td>${confBar(f.confidence)}</td>
      <td><button class="btn btn-outline corr-btn" onclick="openCorrectModal('${key}')">Corrigeer</button></td>
    </tr>`;
  });
  return rows;
}

function renderConcerns(concerns) {
  if (!concerns.length) return '<p class="text-muted" style="font-size:12px">Geen bevindingen.</p>';
  const sorted = [...concerns].sort((a,b) => {
    const o = {blocking:0,warning:1,info:2};
    return (o[a.severity]??9) - (o[b.severity]??9);
  });
  return sorted.map(c => {
    const steps = c.suggested_next_steps?.length
      ? `<ul class="concern-steps">${c.suggested_next_steps.map(s=>`<li>${s}</li>`).join('')}</ul>` : '';
    return `<div class="concern-card ${c.severity}">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
        <span class="badge badge-${c.severity}">${c.severity}</span>
        ${c.field ? `<span class="concern-field">[${c.field}]</span>` : ''}
        <span class="text-muted" style="font-size:11px">(${c.source})</span>
      </div>
      <div class="concern-reason">${c.reason}</div>
      ${steps}
    </div>`;
  }).join('');
}

function renderJournal(lines, amountGross) {
  const rows = lines.map(l =>
    `<tr class="journal-table"><td class="badge badge-${l.side==='D'?'blocking':'ok'}">${l.side}</td><td class="text-mono">${l.account}</td><td>${l.description}</td><td class="text-right">€ ${l.amount.toFixed(2)}</td></tr>`
  ).join('');
  return `<table class="journal-table">
    <thead><tr><th>D/C</th><th>Rekening</th><th>Omschrijving</th><th class="text-right">Bedrag</th></tr></thead>
    <tbody>${rows}<tr class="total-row"><td colspan="3" class="text-right">Totaal incl. BTW</td><td class="text-right">€ ${amountGross.toFixed(2)}</td></tr></tbody>
  </table>`;
}

function renderLineItems(items) {
  if (!items.length) return '';
  const rows = items.map(li => `<tr>
    <td>${li.description}</td>
    <td class="text-right">${li.quantity ?? '—'}</td>
    <td class="text-right">${li.unit_price != null ? '€ '+li.unit_price.toFixed(2) : '—'}</td>
    <td class="text-right">€ ${li.amount.toFixed(2)}</td>
    <td class="text-right">${li.vat_rate != null ? Math.round(li.vat_rate*100)+'%' : '—'}</td>
  </tr>`).join('');
  return `<div class="section-title mt-16">Factuurregels</div>
  <table>
    <thead><tr><th>Omschrijving</th><th class="text-right">Aantal</th><th class="text-right">Prijs</th><th class="text-right">Bedrag</th><th class="text-right">BTW</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function renderReview(data) {
  const confPct = Math.round(data.overall_confidence * 100);
  const confCls = confClass(data.overall_confidence);
  document.getElementById('header-vendor').textContent = data.vendor || '—';
  document.getElementById('header-meta').textContent =
    `Run: ${data.run_id}  ·  Tenant: ${data.tenant_slug}  ·  Bestand: ${data.source_file}`;
  document.getElementById('header-confidence').innerHTML =
    `<span class="badge badge-${confCls==='low'?'blocking':confCls==='medium'?'warning':'ok'}">Confidence ${confPct}%</span>`;

  document.getElementById('fields-body').innerHTML = renderFields(data.fields);
  document.getElementById('line-items-section').innerHTML = renderLineItems(data.line_items);
  document.getElementById('journal-section').innerHTML = renderJournal(data.journal_lines, data.amount_gross);
  document.getElementById('concerns-panel').innerHTML = renderConcerns(data.concerns);

  const approveBtn = document.getElementById('btn-approve');
  approveBtn.disabled = data.has_blocking;
  if (data.has_blocking) approveBtn.title = 'Geblokkeerd door blocking concerns';

  document.getElementById('raw-text-content').textContent = data.raw_text || '';
  document.getElementById('review-area').classList.remove('hidden');
  document.getElementById('action-bar').classList.remove('hidden');
}

function toggleRawText() {
  const card = document.getElementById('raw-text-card');
  const visible = card.style.display !== 'none';
  card.style.display = visible ? 'none' : 'block';
  document.getElementById('btn-view-raw').textContent = visible ? 'Bekijk factuur' : 'Verberg factuur';
}

function refreshReview(data) {
  currentState = { ...currentState, ...data };
  document.getElementById('fields-body').innerHTML = renderFields(data.updated_fields);
  document.getElementById('journal-section').innerHTML = renderJournal(data.updated_journal_lines, currentState.amount_gross);
  document.getElementById('concerns-panel').innerHTML = renderConcerns(data.updated_concerns);
  const approveBtn = document.getElementById('btn-approve');
  approveBtn.disabled = data.has_blocking;
  currentState.has_blocking = data.has_blocking;
  currentState.fields = data.updated_fields;
}

// ── Actions ───────────────────────────────────────────────────────────────────
async function doApprove() {
  const res = await fetch(`/api/runs/${runId}/action`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'approve' }),
  });
  const data = await res.json();
  if (!res.ok) { alert(data.detail || 'Fout'); return; }
  showDoneBanner('booked', `Geboekt — Booking ID: ${data.booking_id}`);
}

async function doForceApprove() {
  const phrase = prompt('Typ ter bevestiging:\nJA IK NEEM VERANTWOORDELIJKHEID');
  if (!phrase) return;
  const res = await fetch(`/api/runs/${runId}/action`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'force_approve', confirmation: phrase }),
  });
  const data = await res.json();
  if (!res.ok) {
    if (data.detail?.error === 'confirmation_required') alert('Bevestigingszin incorrect.');
    else alert(data.detail || 'Fout');
    return;
  }
  showDoneBanner('booked', `Force-approved — Booking ID: ${data.booking_id}`);
}

async function doEscalate() {
  const reason = prompt('Reden voor escalatie:');
  if (!reason) return;
  const res = await fetch(`/api/runs/${runId}/action`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'escalate', note: reason }),
  });
  if (!res.ok) { alert('Fout bij escalatie'); return; }
  showDoneBanner('escalated', `Factuur geëscaleerd: ${reason}`);
}

async function doCancel() {
  if (!confirm('Annuleren? Er wordt niets opgeslagen.')) return;
  await fetch(`/api/runs/${runId}/action`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'cancel' }),
  });
  window.location.href = '/';
}

function showDoneBanner(type, msg) {
  document.getElementById('action-bar').classList.add('hidden');
  document.getElementById('review-area').insertAdjacentHTML('afterbegin',
    `<div class="result-banner ${type}">${msg} <a href="/" style="margin-left:auto">← Terug naar inbox</a></div>`
  );
}

// ── Correction modal ──────────────────────────────────────────────────────────
let correctingField = null;
let pendingRule = null;

function openCorrectModal(fieldKey) {
  correctingField = fieldKey;
  const f = currentState.fields[fieldKey];
  const modal = document.getElementById('correct-modal');
  document.getElementById('modal-field-name').textContent = FIELD_LABELS[fieldKey] || fieldKey;
  document.getElementById('modal-current-val').textContent =
    `Huidige waarde: ${f?.value ?? '—'}  (confidence: ${f ? Math.round(f.confidence*100)+'%' : '?'})`;
  document.getElementById('modal-new-val').value = f?.value ?? '';
  document.getElementById('modal-note').value = '';
  document.getElementById('modal-save-rule').checked = false;
  document.getElementById('modal-step1').classList.remove('hidden');
  document.getElementById('modal-step2').classList.add('hidden');
  pendingRule = null;
  modal.showModal();
}

async function submitCorrection() {
  const newVal = document.getElementById('modal-new-val').value.trim();
  if (!newVal) { alert('Nieuwe waarde mag niet leeg zijn.'); return; }
  const note = document.getElementById('modal-note').value.trim();
  const saveRule = document.getElementById('modal-save-rule').checked;

  const submitBtn = document.getElementById('modal-submit');
  submitBtn.disabled = true; submitBtn.textContent = 'Bezig…';

  const res = await fetch(`/api/runs/${runId}/action`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action: 'correct', field: correctingField,
      new_value: newVal, note: note, save_as_rule: saveRule,
    }),
  });
  const data = await res.json();
  submitBtn.disabled = false; submitBtn.textContent = 'Opslaan';

  if (!res.ok) { alert(data.detail || 'Fout'); return; }
  refreshReview(data);

  if (saveRule && data.rule_proposal) {
    pendingRule = data.rule_proposal;
    showStep2(data.rule_proposal);
  } else {
    document.getElementById('correct-modal').close();
  }
}

function showStep2(proposal) {
  document.getElementById('modal-step1').classList.add('hidden');
  document.getElementById('modal-step2').classList.remove('hidden');
  document.getElementById('modal-rule-text').value = proposal.rule_text;
  document.getElementById('modal-rule-scope').textContent =
    `Scope: ${proposal.scope}${proposal.scope_value ? ' — ' + proposal.scope_value : ''}`;

  const conflictBox = document.getElementById('modal-conflict-box');
  if (proposal.has_conflict) {
    conflictBox.classList.remove('hidden');
    document.getElementById('modal-conflict-detail').textContent =
      proposal.conflicting_rules.join('; ') + (proposal.conflict_explanation ? ' — ' + proposal.conflict_explanation : '');
  } else {
    conflictBox.classList.add('hidden');
  }

  const warnBox = document.getElementById('modal-gen-warning');
  if (proposal.generalization_warning) {
    warnBox.classList.remove('hidden');
    warnBox.textContent = '⚠ ' + proposal.generalization_warning;
  } else {
    warnBox.classList.add('hidden');
  }
}

async function confirmRule() {
  if (!pendingRule) return;
  const ruleText = document.getElementById('modal-rule-text').value.trim();
  if (!ruleText) { alert('Regeltekst mag niet leeg zijn.'); return; }

  const res = await fetch(`/api/runs/${runId}/action`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action: 'confirm_rule', rule_text: ruleText,
      scope: pendingRule.scope, scope_value: pendingRule.scope_value,
    }),
  });
  if (!res.ok) { alert('Fout bij opslaan regel'); return; }
  document.getElementById('correct-modal').close();
}

function skipRule() { document.getElementById('correct-modal').close(); }

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (!runId) { showError('Geen run_id opgegeven.'); return; }
  document.getElementById('btn-approve').addEventListener('click', doApprove);
  document.getElementById('btn-force').addEventListener('click', doForceApprove);
  document.getElementById('btn-escalate').addEventListener('click', doEscalate);
  document.getElementById('btn-cancel').addEventListener('click', doCancel);
  document.getElementById('modal-submit').addEventListener('click', submitCorrection);
  document.getElementById('modal-confirm-rule').addEventListener('click', confirmRule);
  document.getElementById('modal-skip-rule').addEventListener('click', skipRule);
  document.getElementById('modal-close').addEventListener('click', () => document.getElementById('correct-modal').close());
  startPolling();
});
