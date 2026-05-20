let currentTenant = null;

async function loadTenants() {
  const res = await fetch('/api/inbox');
  const data = await res.json();
  const select = document.getElementById('tenant-select');
  select.innerHTML = '';
  data.tenants.forEach(t => {
    const opt = document.createElement('option');
    opt.value = t;
    opt.textContent = t.charAt(0).toUpperCase() + t.slice(1);
    select.appendChild(opt);
  });
  if (data.tenants.length) {
    currentTenant = data.tenants[0];
    loadRules(currentTenant);
  }
  select.addEventListener('change', () => { currentTenant = select.value; loadRules(currentTenant); });
}

async function loadRules(slug) {
  const res = await fetch(`/api/tenants/${slug}/rules`);
  const data = await res.json();
  document.getElementById('tenant-title').textContent = `Geleerde regels — ${data.tenant_name}`;
  renderRules(data.rules);
}

function renderRules(rules) {
  const container = document.getElementById('rules-list');
  if (!rules.length) {
    container.innerHTML = '<div class="empty-rules">Geen geleerde regels voor deze tenant.</div>';
    return;
  }
  container.innerHTML = rules.map(r => `
    <div class="rule-card" id="rule-card-${r.number}">
      <div class="rule-meta">
        <span class="rule-num">#${r.number}</span>
        <span class="badge ${r.scope === 'vendor' ? 'badge-acme' : 'badge-betaworks'}">${r.scope}${r.scope_value ? ': '+r.scope_value : ''}</span>
        <span class="text-muted" style="font-size:11px">${r.date}</span>
      </div>
      <div class="rule-text" id="rule-text-${r.number}">${r.rule_text}</div>
      <div class="rule-actions">
        <button class="btn btn-outline" onclick="startEdit(${r.number})">Bewerk</button>
        <button class="btn btn-danger" onclick="deleteRule(${r.number})">Verwijder</button>
      </div>
      <div class="hidden" id="rule-edit-${r.number}">
        <textarea class="rule-edit-area" id="rule-textarea-${r.number}">${r.rule_text}</textarea>
        <div style="display:flex;gap:8px;margin-top:6px">
          <button class="btn btn-success" onclick="saveEdit(${r.number})">Opslaan</button>
          <button class="btn btn-outline" onclick="cancelEdit(${r.number})">Annuleren</button>
        </div>
      </div>
    </div>
  `).join('');
}

function startEdit(num) {
  document.getElementById(`rule-edit-${num}`).classList.remove('hidden');
  document.getElementById(`rule-text-${num}`).classList.add('hidden');
}

function cancelEdit(num) {
  document.getElementById(`rule-edit-${num}`).classList.add('hidden');
  document.getElementById(`rule-text-${num}`).classList.remove('hidden');
}

async function saveEdit(num) {
  const text = document.getElementById(`rule-textarea-${num}`).value.trim();
  if (!text) { alert('Regeltekst mag niet leeg zijn.'); return; }
  const res = await fetch(`/api/tenants/${currentTenant}/rules/${num}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rule_text: text }),
  });
  if (!res.ok) { alert('Opslaan mislukt'); return; }
  loadRules(currentTenant);
}

async function deleteRule(num) {
  if (!confirm(`Regel #${num} verwijderen?`)) return;
  const res = await fetch(`/api/tenants/${currentTenant}/rules/${num}`, { method: 'DELETE' });
  if (!res.ok) { alert('Verwijderen mislukt'); return; }
  loadRules(currentTenant);
}

document.addEventListener('DOMContentLoaded', loadTenants);
