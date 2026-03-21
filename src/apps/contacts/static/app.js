/* XPlus Contacts — Frontend Application */

const API = '/api';
let contacts = [];
let categories = [];
let selectedId = null;
let currentFilter = null;
let currentSort = 'first_name';

// ── Init ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await Promise.all([loadCategories(), loadContacts(), loadStats()]);
  setupSearch();
  setupKeyboard();
  setupImportDrag();
});

// ── API helpers ───────────────────────────────────────
async function api(path, opts = {}) {
  const url = `${API}${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || 'Request failed');
  }
  if (res.headers.get('content-type')?.includes('json')) return res.json();
  return res.text();
}

// ── Data loading ──────────────────────────────────────
async function loadContacts() {
  const params = new URLSearchParams({ sort: currentSort, dir: currentSort === 'updated_at' ? 'DESC' : 'ASC' });
  if (currentFilter === '_favorites') params.set('favorite', '1');
  else if (currentFilter && currentFilter !== '_all') params.set('category', currentFilter);
  contacts = await api(`/contacts?${params}`);
  renderContactList();
}

async function loadCategories() {
  categories = await api('/categories');
  renderSidebar();
}

async function loadStats() {
  const stats = await api('/contacts/stats');
  document.getElementById('stat-total').textContent = stats.total;
  document.getElementById('stat-favs').textContent = stats.favorites;
  document.getElementById('stat-week').textContent = stats.added_this_week;
  document.getElementById('stat-cats').textContent = Object.keys(stats.by_category).length;
}

// ── Render sidebar ────────────────────────────────────
function renderSidebar() {
  const nav = document.getElementById('cat-nav');
  const catOpts = document.getElementById('cat-options');

  let html = `
    <div class="nav-item ${!currentFilter || currentFilter === '_all' ? 'active' : ''}" onclick="filterBy('_all')">
      <span class="nav-dot" style="background: var(--text-muted)"></span>
      Todos
    </div>
    <div class="nav-item ${currentFilter === '_favorites' ? 'active' : ''}" onclick="filterBy('_favorites')">
      <span class="nav-dot" style="background: var(--star)"></span>
      Favoritos
    </div>
  `;
  let opts = '<option value="personal">Personal</option>';

  for (const cat of categories) {
    const active = currentFilter === cat.id ? 'active' : '';
    html += `
      <div class="nav-item ${active}" onclick="filterBy('${cat.id}')">
        <span class="nav-dot" style="background: ${cat.color}"></span>
        ${cat.name}
        <span class="nav-count" id="count-${cat.id}">0</span>
      </div>
    `;
    opts += `<option value="${cat.id}">${cat.name}</option>`;
  }
  nav.innerHTML = html;
  if (catOpts) catOpts.innerHTML = opts;

  // Update counts
  api('/contacts/stats').then(stats => {
    for (const [cat, count] of Object.entries(stats.by_category)) {
      const el = document.getElementById(`count-${cat}`);
      if (el) el.textContent = count;
    }
  });
}

// ── Render contact list ───────────────────────────────
function renderContactList() {
  const list = document.getElementById('contact-list');
  const countEl = document.getElementById('list-count');
  countEl.textContent = contacts.length;

  if (contacts.length === 0) {
    list.innerHTML = `
      <div class="empty-list">
        <div class="empty-icon">&#128100;</div>
        <p>No hay contactos${currentFilter && currentFilter !== '_all' ? ' en esta categoría' : ''}</p>
        <button class="btn-new" onclick="openNewModal()">+ Nuevo contacto</button>
      </div>
    `;
    return;
  }

  let html = '';
  let lastLetter = '';

  for (const c of contacts) {
    const name = `${c.first_name} ${c.last_name}`.trim() || c.email || c.phone || 'Sin nombre';
    const letter = (c.first_name || c.last_name || name)[0]?.toUpperCase() || '#';

    if (currentSort === 'first_name' && letter !== lastLetter) {
      lastLetter = letter;
      html += `<div class="letter-divider">${letter}</div>`;
    }

    const initials = getInitials(c);
    const sub = c.company || c.email || c.phone || '';
    const catColor = getCatColor(c.category);

    html += `
      <div class="contact-item ${selectedId === c.id ? 'active' : ''}" onclick="selectContact('${c.id}')">
        <div class="contact-avatar" style="background: ${getAvatarGradient(c)}">${initials}</div>
        <div class="contact-info">
          <div class="contact-name">${esc(name)}</div>
          <div class="contact-sub">${esc(sub)}</div>
        </div>
        ${c.is_favorite ? '<span class="contact-fav">&#9733;</span>' : ''}
        <span class="contact-cat-dot" style="background: ${catColor}"></span>
      </div>
    `;
  }
  list.innerHTML = html;
}

// ── Select & render detail ────────────────────────────
async function selectContact(id) {
  selectedId = id;
  renderContactList();

  const c = await api(`/contacts/${id}`);
  const interactions = await api(`/contacts/${id}/interactions`);
  const panel = document.getElementById('detail-panel');
  panel.classList.add('has-contact');

  const name = `${c.first_name} ${c.last_name}`.trim() || 'Sin nombre';
  const initials = getInitials(c);
  const catColor = getCatColor(c.category);
  const catName = categories.find(x => x.id === c.category)?.name || c.category;

  let fieldsHtml = '';

  const fieldMap = [
    { icon: '&#9993;', label: 'Email', value: c.email, link: `mailto:${c.email}` },
    { icon: '&#9993;', label: 'Email 2', value: c.email2, link: `mailto:${c.email2}` },
    { icon: '&#9742;', label: 'Teléfono', value: c.phone, link: `tel:${c.phone}` },
    { icon: '&#9742;', label: 'Teléfono 2', value: c.phone2, link: `tel:${c.phone2}` },
    { icon: '&#128241;', label: 'Móvil', value: c.mobile, link: `tel:${c.mobile}` },
    { icon: '&#127968;', label: 'Dirección', value: [c.address, c.city, c.state, c.zip_code, c.country].filter(Boolean).join(', ') },
    { icon: '&#127760;', label: 'Sitio web', value: c.website, link: c.website?.startsWith('http') ? c.website : `https://${c.website}` },
    { icon: '&#128101;', label: 'LinkedIn', value: c.linkedin, link: c.linkedin?.startsWith('http') ? c.linkedin : `https://linkedin.com/in/${c.linkedin}` },
    { icon: '&#128038;', label: 'Twitter/X', value: c.twitter, link: c.twitter?.startsWith('http') ? c.twitter : `https://x.com/${c.twitter}` },
    { icon: '&#128187;', label: 'GitHub', value: c.github, link: c.github?.startsWith('http') ? c.github : `https://github.com/${c.github}` },
    { icon: '&#128247;', label: 'Instagram', value: c.instagram, link: c.instagram?.startsWith('http') ? c.instagram : `https://instagram.com/${c.instagram}` },
    { icon: '&#128101;', label: 'Facebook', value: c.facebook, link: c.facebook?.startsWith('http') ? c.facebook : `https://facebook.com/${c.facebook}` },
  ];

  for (const f of fieldMap) {
    if (!f.value) continue;
    const val = f.link ? `<a href="${esc(f.link)}" target="_blank">${esc(f.value)}</a>` : esc(f.value);
    fieldsHtml += `
      <div class="detail-field">
        <div class="detail-field-icon">${f.icon}</div>
        <div class="detail-field-content">
          <div class="detail-field-label">${f.label}</div>
          <div class="detail-field-value">${val}</div>
        </div>
      </div>
    `;
  }

  // Custom fields
  let customHtml = '';
  if (c.custom_fields && typeof c.custom_fields === 'object') {
    for (const [k, v] of Object.entries(c.custom_fields)) {
      if (!v) continue;
      customHtml += `
        <div class="detail-field">
          <div class="detail-field-icon">&#9881;</div>
          <div class="detail-field-content">
            <div class="detail-field-label">${esc(k)}</div>
            <div class="detail-field-value">${esc(v)}</div>
          </div>
        </div>
      `;
    }
  }

  // Tags
  let tagsHtml = '';
  const tags = Array.isArray(c.tags) ? c.tags : [];
  if (tags.length > 0) {
    tagsHtml = `<div class="detail-tags">${tags.map(t => `<span class="tag">${esc(t)}</span>`).join('')}</div>`;
  }

  // Interactions
  let intHtml = '';
  for (const int of interactions) {
    const icons = { note: '&#128221;', call: '&#9742;', email: '&#9993;', meeting: '&#128101;', other: '&#128196;' };
    intHtml += `
      <div class="interaction-item">
        <div class="interaction-icon">${icons[int.type] || icons.other}</div>
        <div class="interaction-content">
          ${esc(int.content)}
          <div class="interaction-date">${formatDate(int.date)}</div>
        </div>
      </div>
    `;
  }

  panel.innerHTML = `
    <div class="detail-header">
      <div class="detail-avatar" style="background: ${getAvatarGradient(c)}">${initials}</div>
      <div class="detail-title">
        <h1>${esc(name)}</h1>
        ${c.job_title ? `<div class="detail-company">${esc(c.job_title)}${c.company ? ` @ ${esc(c.company)}` : ''}</div>` :
          c.company ? `<div class="detail-company">${esc(c.company)}</div>` : ''}
        <div class="detail-cat">
          <span class="cat-dot" style="background: ${catColor}"></span>
          ${esc(catName)}
        </div>
      </div>
      <div class="detail-actions">
        <button class="${c.is_favorite ? 'btn-fav' : ''}" onclick="toggleFav('${c.id}')" title="Favorito">&#9733;</button>
        <button onclick="openEditModal('${c.id}')" title="Editar">&#9998;</button>
        <button onclick="exportOne('${c.id}')" title="Exportar vCard">&#8681;</button>
        <button class="btn-delete" onclick="deleteContact('${c.id}')" title="Eliminar">&#128465;</button>
      </div>
    </div>
    <div class="detail-body">
      ${fieldsHtml ? `<div class="detail-section"><div class="detail-section-title">Información de contacto</div>${fieldsHtml}</div>` : ''}
      ${customHtml ? `<div class="detail-section"><div class="detail-section-title">Campos personalizados</div>${customHtml}</div>` : ''}
      ${tagsHtml ? `<div class="detail-section"><div class="detail-section-title">Etiquetas</div>${tagsHtml}</div>` : ''}
      ${c.notes ? `<div class="detail-section"><div class="detail-section-title">Notas</div><div class="detail-notes">${esc(c.notes)}</div></div>` : ''}
      <div class="detail-section">
        <div class="detail-section-title">Historial de interacciones</div>
        <div class="interaction-list">
          ${intHtml || '<p style="color: var(--text-muted); font-size: 13px;">Sin interacciones registradas</p>'}
        </div>
        <div class="add-interaction">
          <select id="int-type" style="width: 100px; padding: 8px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius-xs); color: var(--text-primary); font-size: 12px;">
            <option value="note">Nota</option>
            <option value="call">Llamada</option>
            <option value="email">Email</option>
            <option value="meeting">Reunión</option>
          </select>
          <input type="text" id="int-content" placeholder="Agregar interacción..." onkeydown="if(event.key==='Enter')addInteraction('${c.id}')">
          <button onclick="addInteraction('${c.id}')">+</button>
        </div>
      </div>
      <div style="padding-top: 8px; font-size: 11px; color: var(--text-muted);">
        Creado: ${formatDate(c.created_at)} &middot; Actualizado: ${formatDate(c.updated_at)}
        ${c.last_contacted ? ` &middot; Último contacto: ${formatDate(c.last_contacted)}` : ''}
      </div>
    </div>
  `;
}

// ── Filter & Sort ─────────────────────────────────────
function filterBy(cat) {
  currentFilter = cat === '_all' ? null : cat;
  loadContacts();
  renderSidebar();
}

function sortBy(field) {
  currentSort = field;
  document.querySelectorAll('.sort-chip').forEach(el => {
    el.classList.toggle('active', el.dataset.sort === field);
  });
  loadContacts();
}

// ── Search ────────────────────────────────────────────
function setupSearch() {
  const input = document.getElementById('search-input');
  let timeout;
  input.addEventListener('input', () => {
    clearTimeout(timeout);
    timeout = setTimeout(async () => {
      const q = input.value.trim();
      if (q.length < 2) {
        await loadContacts();
        return;
      }
      contacts = await api(`/contacts/search?q=${encodeURIComponent(q)}`);
      renderContactList();
    }, 250);
  });
}

// ── Keyboard shortcuts ────────────────────────────────
function setupKeyboard() {
  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
    if (e.key === 'n' && !e.ctrlKey && !e.metaKey) { e.preventDefault(); openNewModal(); }
    if (e.key === 'Escape') closeModal();
    if (e.key === '/' || (e.key === 'f' && (e.ctrlKey || e.metaKey))) {
      e.preventDefault();
      document.getElementById('search-input').focus();
    }
    if (e.key === 'Delete' && selectedId) deleteContact(selectedId);
  });
}

// ── Modal: New / Edit ─────────────────────────────────
function openNewModal() {
  renderFormModal(null);
}

async function openEditModal(id) {
  const c = await api(`/contacts/${id}`);
  renderFormModal(c);
}

function renderFormModal(contact) {
  const isEdit = !!contact;
  const c = contact || {};
  const tags = Array.isArray(c.tags) ? c.tags.join(', ') : '';
  const custom = c.custom_fields && typeof c.custom_fields === 'object' ? c.custom_fields : {};

  let catOptions = categories.map(cat =>
    `<option value="${cat.id}" ${c.category === cat.id ? 'selected' : ''}>${cat.name}</option>`
  ).join('');

  let customFieldsHtml = '';
  for (const [k, v] of Object.entries(custom)) {
    customFieldsHtml += `
      <div class="custom-field-row">
        <input type="text" placeholder="Campo" value="${esc(k)}" class="cf-key">
        <input type="text" placeholder="Valor" value="${esc(v)}" class="cf-val">
        <button onclick="this.parentElement.remove()">&#10005;</button>
      </div>
    `;
  }

  const modal = document.getElementById('modal');
  modal.innerHTML = `
    <div class="modal">
      <div class="modal-header">
        <h2>${isEdit ? 'Editar contacto' : 'Nuevo contacto'}</h2>
        <button class="modal-close" onclick="closeModal()">&#10005;</button>
      </div>
      <div class="modal-body">
        <div class="form-section-title">Información personal</div>
        <div class="form-row">
          <div class="form-group">
            <label>Nombre</label>
            <input type="text" id="f-fname" value="${esc(c.first_name || '')}" placeholder="Juan" autofocus>
          </div>
          <div class="form-group">
            <label>Apellido</label>
            <input type="text" id="f-lname" value="${esc(c.last_name || '')}">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>Apodo</label>
            <input type="text" id="f-nick" value="${esc(c.nickname || '')}">
          </div>
          <div class="form-group">
            <label>Categoría</label>
            <select id="f-category">${catOptions}</select>
          </div>
        </div>

        <div class="form-divider"></div>
        <div class="form-section-title">Empresa</div>
        <div class="form-row">
          <div class="form-group">
            <label>Empresa</label>
            <input type="text" id="f-company" value="${esc(c.company || '')}">
          </div>
          <div class="form-group">
            <label>Cargo</label>
            <input type="text" id="f-title" value="${esc(c.job_title || '')}">
          </div>
        </div>

        <div class="form-divider"></div>
        <div class="form-section-title">Contacto</div>
        <div class="form-row">
          <div class="form-group">
            <label>Email principal</label>
            <input type="email" id="f-email" value="${esc(c.email || '')}">
          </div>
          <div class="form-group">
            <label>Email secundario</label>
            <input type="email" id="f-email2" value="${esc(c.email2 || '')}">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>Teléfono</label>
            <input type="tel" id="f-phone" value="${esc(c.phone || '')}">
          </div>
          <div class="form-group">
            <label>Teléfono 2</label>
            <input type="tel" id="f-phone2" value="${esc(c.phone2 || '')}">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>Móvil</label>
            <input type="tel" id="f-mobile" value="${esc(c.mobile || '')}">
          </div>
          <div class="form-group">
            <label>Sitio web</label>
            <input type="url" id="f-website" value="${esc(c.website || '')}">
          </div>
        </div>

        <div class="form-divider"></div>
        <div class="form-section-title">Dirección</div>
        <div class="form-row full">
          <div class="form-group">
            <label>Dirección</label>
            <input type="text" id="f-address" value="${esc(c.address || '')}">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>Ciudad</label>
            <input type="text" id="f-city" value="${esc(c.city || '')}">
          </div>
          <div class="form-group">
            <label>Estado</label>
            <input type="text" id="f-state" value="${esc(c.state || '')}">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>Código postal</label>
            <input type="text" id="f-zip" value="${esc(c.zip_code || '')}">
          </div>
          <div class="form-group">
            <label>País</label>
            <input type="text" id="f-country" value="${esc(c.country || '')}">
          </div>
        </div>

        <div class="form-divider"></div>
        <div class="form-section-title">Redes sociales</div>
        <div class="form-row">
          <div class="form-group">
            <label>LinkedIn</label>
            <input type="text" id="f-linkedin" value="${esc(c.linkedin || '')}" placeholder="usuario o URL">
          </div>
          <div class="form-group">
            <label>Twitter/X</label>
            <input type="text" id="f-twitter" value="${esc(c.twitter || '')}" placeholder="@usuario">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>GitHub</label>
            <input type="text" id="f-github" value="${esc(c.github || '')}">
          </div>
          <div class="form-group">
            <label>Instagram</label>
            <input type="text" id="f-instagram" value="${esc(c.instagram || '')}">
          </div>
        </div>
        <div class="form-row full">
          <div class="form-group">
            <label>Facebook</label>
            <input type="text" id="f-facebook" value="${esc(c.facebook || '')}">
          </div>
        </div>

        <div class="form-divider"></div>
        <div class="form-section-title">Etiquetas y notas</div>
        <div class="form-row full">
          <div class="form-group">
            <label>Etiquetas (separadas por comas)</label>
            <input type="text" id="f-tags" value="${esc(tags)}" placeholder="vip, miami, tech">
          </div>
        </div>
        <div class="form-row full">
          <div class="form-group">
            <label>Notas</label>
            <textarea id="f-notes" rows="3">${esc(c.notes || '')}</textarea>
          </div>
        </div>

        <div class="form-divider"></div>
        <div class="form-section-title">Campos personalizados</div>
        <div class="custom-fields-editor" id="custom-fields-editor">
          ${customFieldsHtml}
        </div>
        <div class="btn-add-field" onclick="addCustomField()">+ Agregar campo</div>

        <div class="form-row" style="margin-top: 12px;">
          <div class="form-group">
            <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
              <input type="checkbox" id="f-fav" ${c.is_favorite ? 'checked' : ''} style="accent-color: var(--star);">
              Marcar como favorito
            </label>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="closeModal()">Cancelar</button>
        <button class="btn btn-primary" onclick="saveContact(${isEdit ? `'${c.id}'` : 'null'})">${isEdit ? 'Guardar cambios' : 'Crear contacto'}</button>
      </div>
    </div>
  `;

  document.getElementById('modal').classList.add('visible');
  setTimeout(() => document.getElementById('f-fname')?.focus(), 100);
}

function addCustomField() {
  const editor = document.getElementById('custom-fields-editor');
  const row = document.createElement('div');
  row.className = 'custom-field-row';
  row.innerHTML = `
    <input type="text" placeholder="Campo" class="cf-key">
    <input type="text" placeholder="Valor" class="cf-val">
    <button onclick="this.parentElement.remove()">&#10005;</button>
  `;
  editor.appendChild(row);
}

function closeModal() {
  document.getElementById('modal').classList.remove('visible');
}

// ── Save contact ──────────────────────────────────────
async function saveContact(id) {
  const tagsStr = document.getElementById('f-tags').value;
  const tags = tagsStr.split(',').map(t => t.trim()).filter(Boolean);

  // Collect custom fields
  const customFields = {};
  document.querySelectorAll('.custom-field-row').forEach(row => {
    const key = row.querySelector('.cf-key')?.value?.trim();
    const val = row.querySelector('.cf-val')?.value?.trim();
    if (key && val) customFields[key] = val;
  });

  const data = {
    first_name: document.getElementById('f-fname').value.trim(),
    last_name: document.getElementById('f-lname').value.trim(),
    nickname: document.getElementById('f-nick').value.trim(),
    category: document.getElementById('f-category').value,
    company: document.getElementById('f-company').value.trim(),
    job_title: document.getElementById('f-title').value.trim(),
    email: document.getElementById('f-email').value.trim(),
    email2: document.getElementById('f-email2').value.trim(),
    phone: document.getElementById('f-phone').value.trim(),
    phone2: document.getElementById('f-phone2').value.trim(),
    mobile: document.getElementById('f-mobile').value.trim(),
    website: document.getElementById('f-website').value.trim(),
    address: document.getElementById('f-address').value.trim(),
    city: document.getElementById('f-city').value.trim(),
    state: document.getElementById('f-state').value.trim(),
    zip_code: document.getElementById('f-zip').value.trim(),
    country: document.getElementById('f-country').value.trim(),
    linkedin: document.getElementById('f-linkedin').value.trim(),
    twitter: document.getElementById('f-twitter').value.trim(),
    github: document.getElementById('f-github').value.trim(),
    instagram: document.getElementById('f-instagram').value.trim(),
    facebook: document.getElementById('f-facebook').value.trim(),
    tags,
    notes: document.getElementById('f-notes').value,
    is_favorite: document.getElementById('f-fav').checked ? 1 : 0,
    custom_fields: customFields,
  };

  try {
    if (id) {
      await api(`/contacts/${id}`, { method: 'PUT', body: JSON.stringify(data) });
      toast('Contacto actualizado', 'success');
    } else {
      const created = await api('/contacts', { method: 'POST', body: JSON.stringify(data) });
      id = created.id;
      toast('Contacto creado', 'success');
    }
    closeModal();
    await loadContacts();
    await loadStats();
    if (id) selectContact(id);
  } catch (err) {
    toast(err.message, 'error');
  }
}

// ── Delete ────────────────────────────────────────────
async function deleteContact(id) {
  if (!confirm('¿Eliminar este contacto?')) return;
  try {
    await api(`/contacts/${id}`, { method: 'DELETE' });
    toast('Contacto eliminado', 'success');
    selectedId = null;
    document.getElementById('detail-panel').innerHTML = `
      <div class="detail-empty">
        <div class="detail-empty-icon">&#128100;</div>
        <p>Selecciona un contacto</p>
      </div>
    `;
    document.getElementById('detail-panel').classList.remove('has-contact');
    await loadContacts();
    await loadStats();
  } catch (err) {
    toast(err.message, 'error');
  }
}

// ── Toggle favorite ───────────────────────────────────
async function toggleFav(id) {
  await api(`/contacts/${id}/favorite`, { method: 'POST' });
  await loadContacts();
  await loadStats();
  selectContact(id);
}

// ── Add interaction ───────────────────────────────────
async function addInteraction(contactId) {
  const content = document.getElementById('int-content').value.trim();
  if (!content) return;
  const type = document.getElementById('int-type').value;
  await api(`/contacts/${contactId}/interactions`, {
    method: 'POST',
    body: JSON.stringify({ type, content }),
  });
  selectContact(contactId);
}

// ── Export ─────────────────────────────────────────────
function exportOne(id) {
  window.open(`${API}/contacts/export?id=${id}`, '_blank');
}

function exportAll() {
  window.open(`${API}/contacts/export`, '_blank');
}

// ── Import ────────────────────────────────────────────
function openImportModal() {
  const modal = document.getElementById('modal');
  modal.innerHTML = `
    <div class="modal">
      <div class="modal-header">
        <h2>Importar contactos</h2>
        <button class="modal-close" onclick="closeModal()">&#10005;</button>
      </div>
      <div class="modal-body">
        <div class="import-area" id="import-area" onclick="document.getElementById('import-file').click()">
          <div style="font-size: 36px; margin-bottom: 12px;">&#128229;</div>
          <p>Arrastra un archivo .vcf aquí o haz clic para seleccionar</p>
          <p style="font-size: 11px; margin-top: 8px;">Formato soportado: vCard (.vcf)</p>
        </div>
        <input type="file" id="import-file" accept=".vcf,.vcard" style="display:none" onchange="handleImportFile(event)">
        <div id="import-result" style="margin-top: 12px;"></div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="closeModal()">Cerrar</button>
      </div>
    </div>
  `;
  modal.classList.add('visible');
}

async function handleImportFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const text = await file.text();
  try {
    const result = await api('/contacts/import', { method: 'POST', body: text, headers: { 'Content-Type': 'text/plain' } });
    document.getElementById('import-result').innerHTML = `
      <div style="color: var(--success); font-size: 14px;">&#10003; ${result.imported} contactos importados</div>
    `;
    await loadContacts();
    await loadStats();
    await loadCategories();
  } catch (err) {
    document.getElementById('import-result').innerHTML = `
      <div style="color: var(--danger); font-size: 14px;">Error: ${err.message}</div>
    `;
  }
}

function setupImportDrag() {
  document.addEventListener('dragover', e => {
    e.preventDefault();
    const area = document.getElementById('import-area');
    if (area) area.classList.add('dragover');
  });
  document.addEventListener('drop', async e => {
    e.preventDefault();
    const area = document.getElementById('import-area');
    if (area) area.classList.remove('dragover');
    const file = e.dataTransfer?.files?.[0];
    if (file && (file.name.endsWith('.vcf') || file.name.endsWith('.vcard'))) {
      handleImportFile({ target: { files: [file] } });
    }
  });
}

// ── Toast notifications ───────────────────────────────
function toast(msg, type = 'success') {
  const container = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `${type === 'success' ? '&#10003;' : '&#9888;'} ${esc(msg)}`;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// ── Helpers ───────────────────────────────────────────
function esc(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

function getInitials(c) {
  const f = c.first_name?.[0] || '';
  const l = c.last_name?.[0] || '';
  return (f + l).toUpperCase() || (c.email?.[0] || '?').toUpperCase();
}

function getAvatarGradient(c) {
  const colors = [
    'linear-gradient(135deg, #6366f1, #a855f7)',
    'linear-gradient(135deg, #ec4899, #f43f5e)',
    'linear-gradient(135deg, #10b981, #14b8a6)',
    'linear-gradient(135deg, #f59e0b, #f97316)',
    'linear-gradient(135deg, #3b82f6, #6366f1)',
    'linear-gradient(135deg, #8b5cf6, #ec4899)',
    'linear-gradient(135deg, #ef4444, #f59e0b)',
    'linear-gradient(135deg, #14b8a6, #3b82f6)',
  ];
  const hash = (c.first_name || '').length + (c.last_name || '').length + (c.email || '').length;
  return colors[hash % colors.length];
}

function getCatColor(catId) {
  const cat = categories.find(c => c.id === catId);
  return cat?.color || '#6366f1';
}

function formatDate(ts) {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return d.toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}
