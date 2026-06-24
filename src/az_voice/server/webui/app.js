// ── State ──────────────────────────────────────────────────────────────────────
let currentBlob = null;
let currentFormat = 'mp3';

// ── DOM refs ───────────────────────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const textInput = $('#textInput');
const formatSelect = $('#formatSelect');
const speedRange = $('#speedRange');
const speedValue = $('#speedValue');
const styleInput = $('#styleInput');
const generateBtn = $('#generateBtn');
const clearBtn = $('#clearBtn');
const outputSection = $('#outputSection');
const outputInfo = $('#outputInfo');
const audioPlayer = $('#audioPlayer');
const downloadBtn = $('#downloadBtn');
const errorSection = $('#errorSection');
const errorText = $('#errorText');
const statusDot = $('#statusDot');
const statusText = $('#statusText');

// ── Health check with download progress polling ──────────────────────────────
let healthPollTimer = null;

async function checkHealth() {
  try {
    const resp = await fetch('/health');
    const data = await resp.json();
    console.log('[health]', data);
    const progress = data.model_progress || {};
    console.log('[progress]', progress);
    
    if (data.model_loaded) {
      statusDot.className = 'status-dot online';
      const msg = `Ready · ${data.device}`;
      console.log('[status] setting:', msg);
      statusText.textContent = msg;
      generateBtn.disabled = false;
      // Stop aggressive polling when ready
      if (healthPollTimer) { clearInterval(healthPollTimer); healthPollTimer = null; }
    } else if (progress.status === 'loading') {
      statusDot.className = 'status-dot loading';
      const pct = progress.percent ? ` (${progress.percent}%)` : '';
      const msg = `${progress.message}${pct}`;
      console.log('[status] setting:', msg);
      statusText.textContent = msg;
      generateBtn.disabled = true;
      // Poll every 1s during loading
      if (!healthPollTimer) healthPollTimer = setInterval(checkHealth, 1000);
    } else if (progress.status === 'downloading') {
      statusDot.className = 'status-dot loading';
      const msg = `${progress.message} (${progress.percent}%)`;
      console.log('[status] setting:', msg);
      statusText.textContent = msg;
      generateBtn.disabled = true;
      // Poll every 1s during download
      if (!healthPollTimer) healthPollTimer = setInterval(checkHealth, 1000);
    } else if (progress.status === 'cached') {
      statusDot.className = 'status-dot online';
      const msg = `${progress.message} (${data.device})`;
      console.log('[status] setting:', msg);
      statusText.textContent = msg;
      generateBtn.disabled = false;
    } else if (progress.status === 'pending') {
      statusDot.className = 'status-dot online';
      const msg = `Online · Model will download on first request (${data.device})`;
      console.log('[status] setting:', msg);
      statusText.textContent = msg;
      generateBtn.disabled = false;
    } else if (progress.status === 'error') {
      statusDot.className = 'status-dot offline';
      const msg = `Download error: ${progress.message}`;
      console.log('[status] setting:', msg);
      statusText.textContent = msg;
      generateBtn.disabled = false;  // Still allow TTS (will lazy load)
    } else {
      statusDot.className = 'status-dot online';
      statusText.textContent = `Online · ${data.device}`;
      generateBtn.disabled = false;
    }
  } catch {
    statusDot.className = 'status-dot offline';
    statusText.textContent = 'Server unreachable';
    generateBtn.disabled = true;
  }
}

// ── Speed slider ───────────────────────────────────────────────────────────────
speedRange.addEventListener('input', () => {
  speedValue.textContent = speedRange.value;
});

// ── Generate ───────────────────────────────────────────────────────────────────
generateBtn.addEventListener('click', generate);

async function generate() {
  const text = textInput.value.trim();
  if (!text) {
    showError('Please enter some text.');
    return;
  }

  // Check if model is still loading
  const health = await fetch('/health').then(r => r.json()).catch(() => null);
  if (health && health.model_progress && health.model_progress.status === 'loading') {
    showError('Model is still loading. Please wait...');
    return;
  }

  // Reset state
  hideError();
  outputSection.hidden = true;
  generateBtn.classList.add('loading');
  generateBtn.disabled = true;

  const payload = {
    model: 'voxcpm2',
    input: text,
    response_format: formatSelect.value,
    speed: parseFloat(speedRange.value),
  };

  const style = styleInput.value.trim();
  if (style) payload.control_instruction = style;

  try {
    const startTime = Date.now();
    const resp = await fetch('/v1/audio/speech', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: { message: `HTTP ${resp.status}` } }));
      throw new Error(err.error?.message || `Request failed: ${resp.status}`);
    }

    const blob = await resp.blob();
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    const duration = resp.headers.get('X-Audio-Duration') || '?';
    const size = (blob.size / 1024).toFixed(1);

    // Clean up previous blob URL
    if (currentBlob) URL.revokeObjectURL(currentBlob);

    currentBlob = URL.createObjectURL(blob);
    currentFormat = formatSelect.value;

    audioPlayer.src = currentBlob;
    outputInfo.textContent = `${size} KB · ${duration}s audio · ${elapsed}s gen`;
    outputSection.hidden = false;

    // Auto-play
    audioPlayer.play().catch(() => {});

  } catch (err) {
    showError(err.message);
  } finally {
    generateBtn.classList.remove('loading');
    generateBtn.disabled = false;
  }
}

// ── Download ───────────────────────────────────────────────────────────────────
downloadBtn.addEventListener('click', () => {
  if (!currentBlob) return;
  const a = document.createElement('a');
  a.href = currentBlob;
  a.download = `speech.${currentFormat}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
});

// ── Clear ──────────────────────────────────────────────────────────────────────
clearBtn.addEventListener('click', () => {
  textInput.value = '';
  styleInput.value = '';
  speedRange.value = 1.0;
  speedValue.textContent = '1.0';
  formatSelect.value = 'mp3';
  outputSection.hidden = true;
  hideError();
  if (currentBlob) { URL.revokeObjectURL(currentBlob); currentBlob = null; }
  audioPlayer.src = '';
  textInput.focus();
});

// ── Error handling ─────────────────────────────────────────────────────────────
function showError(msg) {
  errorText.textContent = msg;
  errorSection.hidden = false;
}

function hideError() {
  errorSection.hidden = true;
}

// ── Keyboard shortcut (Ctrl/Cmd + Enter to generate) ──────────────────────────
textInput.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault();
    generate();
  }
});

// ── Init ───────────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  // Verify DOM elements exist
  if (!statusText) console.error('[init] statusText element not found');
  if (!statusDot) console.error('[init] statusDot element not found');
  console.log('[init] DOM ready, elements:', {statusText: !!statusText, statusDot: !!statusDot});
  checkHealth();
  // Re-check every 30s when idle (overridden to 1s during loading)
  setInterval(() => { if (!healthPollTimer) checkHealth(); }, 30000);
});
