let emails = [];
let selectedEmail = null;

async function loadInbox() {
  const res = await fetch('/api/inbox');
  const data = await res.json();
  emails = data.emails;

  const tenantSelect = document.getElementById('tenant-select');
  tenantSelect.innerHTML = '';
  data.tenants.forEach(t => {
    const opt = document.createElement('option');
    opt.value = t;
    opt.textContent = t.charAt(0).toUpperCase() + t.slice(1);
    tenantSelect.appendChild(opt);
  });

  renderEmailList(emails);
}

function tenantBadge(tenant) {
  const cls = tenant === 'acme' ? 'badge-acme' : tenant === 'betaworks' ? 'badge-betaworks' : 'badge-default';
  return `<span class="badge ${cls}">${tenant || '?'}</span>`;
}

function fileTypeBadge(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  const map = {
    txt:  { label: 'TXT',   cls: 'badge-filetype-txt' },
    pdf:  { label: 'PDF',   cls: 'badge-filetype-pdf' },
    html: { label: 'HTML',  cls: 'badge-filetype-html' },
    htm:  { label: 'HTML',  cls: 'badge-filetype-html' },
    xlsx: { label: 'Excel', cls: 'badge-filetype-excel' },
    xls:  { label: 'Excel', cls: 'badge-filetype-excel' },
    csv:  { label: 'CSV',   cls: 'badge-filetype-excel' },
    png:  { label: 'Scan',  cls: 'badge-filetype-scan' },
    jpg:  { label: 'Scan',  cls: 'badge-filetype-scan' },
    jpeg: { label: 'Scan',  cls: 'badge-filetype-scan' },
  };
  const { label, cls } = map[ext] || { label: ext.toUpperCase(), cls: 'badge-default' };
  return `<span class="badge ${cls}">${label}</span>`;
}

function relativeTime(isoStr) {
  const diff = Date.now() - new Date(isoStr).getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) return 'vandaag';
  if (days === 1) return 'gisteren';
  return `${days} dagen geleden`;
}

function renderEmailList(list) {
  const el = document.getElementById('email-list');
  el.innerHTML = '';
  list.forEach(email => {
    const div = document.createElement('div');
    div.className = 'email-item' + (selectedEmail?.id === email.id ? ' selected' : '');
    div.innerHTML = `
      <div class="sender">${email.sender_name}</div>
      <div class="subject">${email.subject}</div>
      <div class="meta">
        <span class="time">${relativeTime(email.received_at)}</span>
        ${tenantBadge(email.default_tenant)}
      </div>
      <div class="snippet">${email.snippet}</div>
    `;
    div.addEventListener('click', () => selectEmail(email));
    el.appendChild(div);
  });
}

async function selectEmail(email) {
  selectedEmail = email;
  renderEmailList(emails);

  const res = await fetch(`/api/inbox/${email.id}`);
  const full = await res.json();

  document.getElementById('preview-empty').classList.add('hidden');
  document.getElementById('preview-content').classList.remove('hidden');

  document.getElementById('preview-subject').textContent = full.subject;
  document.getElementById('preview-meta').textContent =
    `Van: ${full.sender}  ·  Ontvangen: ${new Date(full.received_at).toLocaleString('nl-NL')}  ·  Bijlage: ${full.attachment_filename}`;
  document.getElementById('preview-raw').textContent = full.raw_text;

  const tenantSelect = document.getElementById('tenant-select');
  if (full.default_tenant) tenantSelect.value = full.default_tenant;
}

async function processInvoice() {
  if (!selectedEmail) return;
  const tenant = document.getElementById('tenant-select').value;
  const btn = document.getElementById('process-btn');
  btn.disabled = true;
  btn.textContent = 'Bezig…';

  const res = await fetch('/api/process', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email_id: selectedEmail.id, tenant_slug: tenant }),
  });

  if (!res.ok) {
    const err = await res.json();
    alert('Fout: ' + (err.detail || 'Onbekende fout'));
    btn.disabled = false;
    btn.textContent = 'Verwerk factuur';
    return;
  }

  const data = await res.json();
  window.location.href = `/static/pages/review.html?run_id=${data.run_id}`;
}

document.addEventListener('DOMContentLoaded', () => {
  loadInbox();
  document.getElementById('process-btn').addEventListener('click', processInvoice);
});
