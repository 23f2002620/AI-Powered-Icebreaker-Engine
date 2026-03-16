/* Icebreaker Engine — app.js (with Magic Wand) */

const state = {
  profileA: null,
  profileB: null,
  allProfiles: [],
  lastIcebreakers: null,
};

/* ── DOM refs ── */
const selectA       = document.getElementById('select-a');
const selectB       = document.getElementById('select-b');
const badgeA        = document.getElementById('badge-a');
const badgeB        = document.getElementById('badge-b');
const btnGenerate   = document.getElementById('btn-generate');
const btnRegen      = document.getElementById('btn-regen');
const btnCopyAll    = document.getElementById('btn-copy-all');
const swapBtn       = document.getElementById('swap-btn');
const outputSection = document.getElementById('output-section');
const chatSection   = document.getElementById('chat-section');
const matchBanner   = document.getElementById('match-banner');
const ibGrid        = document.getElementById('ib-grid');
const loadingEl     = document.getElementById('loading');
const toastEl       = document.getElementById('toast');
const healthDot     = document.getElementById('health-dot');
const healthLabel   = document.getElementById('health-label');

/* Magic Wand refs */
const wandBtn       = document.getElementById('wand-btn');
const wandPopup     = document.getElementById('wand-popup');
const wandBackdrop  = document.getElementById('wand-backdrop');
const wandClose     = document.getElementById('wand-close');
const wandItems     = document.getElementById('wand-items');
const chatTextarea  = document.getElementById('chat-textarea');
const sendBtn       = document.getElementById('send-btn');
const chatMessages  = document.getElementById('chat-messages');
const chatEmpty     = document.getElementById('chat-empty');

/* ── Utils ── */
function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function escAttr(s) { return String(s).replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function toast(msg) {
  toastEl.textContent = msg;
  toastEl.classList.add('show');
  setTimeout(() => toastEl.classList.remove('show'), 2400);
}
function loading(on) { loadingEl.style.display = on ? 'flex' : 'none'; }
function calcAge(bd) {
  if (!bd) return null;
  return Math.floor((Date.now() - new Date(bd)) / (365.25 * 24 * 3600 * 1000));
}
function profileMeta(p) {
  const parts = [];
  if (p.birth_date) { const a = calcAge(p.birth_date); if (a) parts.push(a + 'y'); }
  if (p.city)   parts.push(p.city);
  if (p.gender) parts.push(p.gender);
  return parts.join(' · ');
}
function initials(n) {
  if (!n) return '?';
  return n.trim().split(/\s+/).map(w => w[0]).join('').toUpperCase().slice(0, 2);
}

/* ── Health ── */
async function checkHealth() {
  try {
    const d = await fetch('/api/health').then(r => r.json());
    if (d.status === 'ok') {
      healthDot.className = 'hdot ok';
      healthLabel.textContent = 'Backend online';
    }
  } catch {
    healthDot.className = 'hdot err';
    healthLabel.textContent = 'Backend offline';
  }
}

/* ── Load profiles ── */
async function loadProfiles() {
  try {
    const d = await fetch('/api/profiles?per_page=200').then(r => r.json());
    if (!d.success) throw new Error(d.error);
    state.allProfiles = d.profiles;
    [selectA, selectB].forEach(sel => {
      sel.innerHTML = '<option value="">— Select a profile —</option>';
      d.profiles.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        const m = profileMeta(p);
        opt.textContent = (p.display_name || 'Unnamed') + (m ? '  (' + m + ')' : '');
        sel.appendChild(opt);
      });
    });
  } catch (e) {
    [selectA, selectB].forEach(s => {
      s.innerHTML = '<option value="">— Failed to load profiles —</option>';
    });
    console.error('loadProfiles error:', e);
  }
}

/* ── Select handlers ── */
function onSelect(role) {
  const sel   = role === 'a' ? selectA : selectB;
  const badge = role === 'a' ? badgeA  : badgeB;
  const avCls = role === 'a' ? 's'     : 'r';
  const id    = sel.value;

  if (!id) {
    if (role === 'a') state.profileA = null; else state.profileB = null;
    badge.innerHTML = '<p class="badge-empty">No profile selected</p>';
    updateBtn(); return;
  }
  const p = state.allProfiles.find(x => x.id === id);
  if (!p) return;
  if (role === 'a') state.profileA = p; else state.profileB = p;
  const m = profileMeta(p);
  badge.innerHTML =
    '<div class="badge">' +
      '<div class="badge-av ' + avCls + '">' + esc(initials(p.display_name)) + '</div>' +
      '<div>' +
        '<div class="badge-name">' + esc(p.display_name || 'Unnamed') + '</div>' +
        (m ? '<div class="badge-meta">' + esc(m) + '</div>' : '') +
      '</div>' +
    '</div>';
  updateBtn();
}
selectA.addEventListener('change', () => onSelect('a'));
selectB.addEventListener('change', () => onSelect('b'));

function updateBtn() {
  btnGenerate.disabled = !(
    state.profileA && state.profileB && state.profileA.id !== state.profileB.id
  );
}

/* ── Swap ── */
swapBtn.addEventListener('click', () => {
  [state.profileA, state.profileB] = [state.profileB, state.profileA];
  selectA.value = state.profileA ? state.profileA.id : '';
  selectB.value = state.profileB ? state.profileB.id : '';
  onSelect('a'); onSelect('b');
});

/* ── Generate ── */
async function generate() {
  if (!state.profileA || !state.profileB) return;
  loading(true);
  try {
    const res = await fetch('/api/icebreakers/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profile_a_id: state.profileA.id,
        profile_b_id: state.profileB.id,
      }),
    });
    const d = await res.json();
    if (!d.success) { toast('Error: ' + (d.error || 'Unknown')); return; }

    state.lastIcebreakers = d.icebreakers;
    renderOutput(d);

    outputSection.style.display = 'block';
    outputSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

    /* Show chat widget + enable magic wand */
    chatSection.style.display = 'block';
    enableMagicWand();

  } catch (e) {
    toast('Network error. Check backend.');
    console.error(e);
  } finally {
    loading(false);
  }
}
btnGenerate.addEventListener('click', generate);
btnRegen.addEventListener('click', generate);

/* ── Render output cards ── */
const IB_META = {
  question:    { label: 'Question',    icon: '🤔' },
  observation: { label: 'Observation', icon: '👁'  },
  fun_fact:    { label: 'Fun Fact',    icon: '✨' },
};

function renderOutput(d) {
  const na = d.profile_a ? d.profile_a.name : 'Sender';
  const nb = d.profile_b ? d.profile_b.name : 'Recipient';
  const ts = d.icebreakers && d.icebreakers.generated_at
    ? new Date(d.icebreakers.generated_at).toLocaleTimeString() : '';
  matchBanner.textContent = na + '  →  ' + nb + (ts ? '  ·  ' + ts : '');

  ibGrid.innerHTML = '';
  ['question', 'observation', 'fun_fact'].forEach(key => {
    const text = d.icebreakers[key] || '';
    const meta = IB_META[key];
    const card = document.createElement('div');
    card.className = 'ib-card';
    card.innerHTML =
      '<div class="ib-badge ' + key + '">' + meta.icon + ' ' + meta.label + '</div>' +
      '<p class="ib-text">' + esc(text) + '</p>' +
      '<button class="ib-copy" data-t="' + escAttr(text) + '">Copy</button>';
    card.querySelector('.ib-copy').addEventListener('click', function () {
      navigator.clipboard.writeText(this.dataset.t).then(() => {
        this.textContent = 'Copied ✓'; this.classList.add('copied');
        setTimeout(() => { this.textContent = 'Copy'; this.classList.remove('copied'); }, 1800);
      });
    });
    ibGrid.appendChild(card);
  });
}

btnCopyAll.addEventListener('click', () => {
  if (!state.lastIcebreakers) return;
  const { question, observation, fun_fact } = state.lastIcebreakers;
  navigator.clipboard.writeText(
    'Question:\n' + question +
    '\n\nObservation:\n' + observation +
    '\n\nFun Fact:\n' + fun_fact
  ).then(() => toast('All icebreakers copied!'));
});

/* ════════════════════════════════════════
   MAGIC WAND
════════════════════════════════════════ */

function enableMagicWand() {
  wandBtn.disabled = false;
  wandBtn.classList.add('has-icebreakers');
  buildWandItems();
  /* Remove ping dot after 3s */
  setTimeout(() => wandBtn.classList.remove('has-icebreakers'), 3000);
}

function buildWandItems() {
  if (!state.lastIcebreakers) return;
  wandItems.innerHTML = '';

  const entries = [
    { key: 'question',    icon: '🤔', label: 'Question' },
    { key: 'observation', icon: '👁',  label: 'Observation' },
    { key: 'fun_fact',    icon: '✨', label: 'Fun Fact' },
  ];

  entries.forEach(({ key, icon, label }) => {
    const text = state.lastIcebreakers[key] || '';
    if (!text) return;

    const btn = document.createElement('button');
    btn.className = 'wand-item';
    btn.setAttribute('data-text', text);
    btn.innerHTML =
      '<span class="wand-item-icon">' + icon + '</span>' +
      '<span class="wand-item-body">' +
        '<div class="wand-item-type ' + key + '">' + label + '</div>' +
        '<div class="wand-item-text">' + esc(text) + '</div>' +
      '</span>' +
      '<span class="wand-item-use">Use →</span>';

    btn.addEventListener('click', () => {
      useIcebreaker(text);
    });
    wandItems.appendChild(btn);
  });
}

function openWandPopup() {
  if (!state.lastIcebreakers) return;
  buildWandItems();               /* refresh in case regenerated */
  wandPopup.style.display = 'block';
  wandBackdrop.style.display = 'block';
  wandBtn.classList.add('active');
  /* Focus trap: first item */
  const first = wandItems.querySelector('.wand-item');
  if (first) first.focus();
}

function closeWandPopup() {
  wandPopup.style.display = 'none';
  wandBackdrop.style.display = 'none';
  wandBtn.classList.remove('active');
  wandBtn.focus();
}

wandBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  if (wandPopup.style.display === 'none') openWandPopup();
  else closeWandPopup();
});

wandClose.addEventListener('click', closeWandPopup);
wandBackdrop.addEventListener('click', closeWandPopup);

/* Close on Escape */
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && wandPopup.style.display !== 'none') closeWandPopup();
});

/* ── Use icebreaker: populate textarea ── */
function useIcebreaker(text) {
  chatTextarea.value = text;
  autoResizeTextarea();
  chatTextarea.focus();
  closeWandPopup();
  toast('Icebreaker loaded — hit Send!');
}

/* ── Send message ── */
function sendMessage() {
  const text = chatTextarea.value.trim();
  if (!text) return;

  /* Hide empty state */
  chatEmpty.style.display = 'none';

  /* Append bubble */
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble sent';
  bubble.textContent = text;
  chatMessages.appendChild(bubble);

  /* Scroll to bottom */
  const win = document.getElementById('chat-window');
  win.scrollTop = win.scrollHeight;

  /* Clear textarea */
  chatTextarea.value = '';
  autoResizeTextarea();
  toast('Message sent!');
}

sendBtn.addEventListener('click', sendMessage);

chatTextarea.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

/* ── Auto-resize textarea ── */
function autoResizeTextarea() {
  chatTextarea.style.height = 'auto';
  chatTextarea.style.height = Math.min(chatTextarea.scrollHeight, 120) + 'px';
}
chatTextarea.addEventListener('input', autoResizeTextarea);

/* ── Init ── */
(async () => {
  await Promise.all([checkHealth(), loadProfiles()]);
})();