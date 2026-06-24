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

async function fileToDataUri(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

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

  // Reference audio
  const refAudioFile = refAudioInput.files[0];
  if (refAudioFile) {
    payload.reference_wav = await fileToDataUri(refAudioFile);
    const refText = refTextInput.value.trim();
    if (refText) payload.reference_text = refText;
  }

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

// ── Tab switching ──────────────────────────────────────────────────────────────
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
  });
});

// ── Streaming: schedule PCM chunks on the Web Audio clock ─────────────────────
let streamAudioCtx = null;
let streamController = null;
let streamSampleRate = 24000;
let streamNextStartTime = 0;
let streamSources = new Set();
let streamLastSample = null;

const STREAM_INITIAL_DELAY_SEC = 0.18;
const STREAM_RECOVERY_DELAY_SEC = 0.02;
const STREAM_DECLICK_SAMPLES = 128;

const streamBtn = document.getElementById('streamBtn');
const stopStreamBtn = document.getElementById('stopStreamBtn');
const streamStatus = document.getElementById('streamStatus');
const streamStatusText = document.getElementById('streamStatusText');
const streamWave = document.getElementById('streamWave');
const streamErrorSection = document.getElementById('streamErrorSection');
const streamErrorText = document.getElementById('streamErrorText');
const streamTextInput = document.getElementById('streamTextInput');
const streamStyleInput = document.getElementById('streamStyleInput');

for (let i = 0; i < 8; i++) {
  const bar = document.createElement('div');
  bar.className = 'bar';
  streamWave.appendChild(bar);
}

streamBtn.addEventListener('click', startStream);
stopStreamBtn.addEventListener('click', stopStream);

async function startStream() {
  const text = streamTextInput.value.trim();
  if (!text) return;

  streamErrorSection.hidden = true;
  streamStatus.hidden = false;
  streamStatusText.textContent = 'Connecting...';
  streamBtn.hidden = true;
  stopStreamBtn.hidden = false;

  if (!streamAudioCtx) {
    streamAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (streamAudioCtx.state === 'suspended') await streamAudioCtx.resume();

  resetStreamPlayback();

  streamController = new AbortController();
  const payload = { model: 'voxcpm2', input: text };
  const style = streamStyleInput.value.trim();
  if (style) payload.control_instruction = style;

  // Reference audio
  const streamRefAudioFile = streamRefAudioInput.files[0];
  if (streamRefAudioFile) {
    payload.reference_wav = await fileToDataUri(streamRefAudioFile);
    const streamRefText = streamRefTextInput.value.trim();
    if (streamRefText) payload.reference_text = streamRefText;
  }

  try {
    const resp = await fetch('/v1/audio/speech/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: streamController.signal,
    });

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let chunkCount = 0;
    streamStatusText.textContent = 'Generating...';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = JSON.parse(line.slice(6));

        if (data.type === 'metadata') {
          if (data.sample_rate) streamSampleRate = data.sample_rate;
        } else if (data.type === 'audio') {
          const float32 = smoothChunkBoundary(decodePcm16(data.data));
          queueStreamChunk(float32);
          chunkCount++;
          streamStatusText.textContent = 'Generating... (' + chunkCount + ' chunks)';
        } else if (data.type === 'done') {
          streamStatusText.textContent = 'Complete! (' + chunkCount + ' chunks)';
        } else if (data.type === 'error') {
          throw new Error(data.message);
        }
      }
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      streamStatusText.textContent = 'Stopped';
    } else {
      streamErrorText.textContent = err.message;
      streamErrorSection.hidden = false;
    }
  } finally {
    setTimeout(() => {
      streamStatus.hidden = true;
      streamBtn.hidden = false;
      stopStreamBtn.hidden = true;
    }, 3000);
  }
}

function decodePcm16(base64) {
  const bytes = Uint8Array.from(atob(base64), c => c.charCodeAt(0));
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const samples = new Float32Array(bytes.byteLength / 2);

  for (let i = 0; i < samples.length; i++) {
    samples[i] = view.getInt16(i * 2, true) / 32768;
  }

  return samples;
}

function smoothChunkBoundary(samples) {
  if (!samples.length) return samples;

  if (streamLastSample !== null) {
    const fade = Math.min(STREAM_DECLICK_SAMPLES, samples.length);
    const offset = streamLastSample - samples[0];
    for (let i = 0; i < fade; i++) {
      const t = i / fade;
      samples[i] += offset * (1 - t);
    }
  }

  streamLastSample = samples[samples.length - 1];
  return samples;
}

function queueStreamChunk(samples) {
  if (!samples.length) return;

  const audioBuf = streamAudioCtx.createBuffer(1, samples.length, streamSampleRate);
  audioBuf.getChannelData(0).set(samples);

  const source = streamAudioCtx.createBufferSource();
  const gain = streamAudioCtx.createGain();
  source.buffer = audioBuf;
  source.connect(gain);
  gain.connect(streamAudioCtx.destination);
  source.onended = () => streamSources.delete(source);

  const now = streamAudioCtx.currentTime;
  const isFirstChunk = streamNextStartTime === 0;
  const underrun = !isFirstChunk && streamNextStartTime <= now;
  const startAt = isFirstChunk
    ? now + STREAM_INITIAL_DELAY_SEC
    : underrun
      ? now + STREAM_RECOVERY_DELAY_SEC
      : streamNextStartTime;

  if (isFirstChunk || underrun) {
    const fadeSec = STREAM_DECLICK_SAMPLES / streamSampleRate;
    gain.gain.setValueAtTime(0, startAt);
    gain.gain.linearRampToValueAtTime(1, startAt + fadeSec);
  } else {
    gain.gain.setValueAtTime(1, startAt);
  }

  streamSources.add(source);
  source.start(startAt);
  streamNextStartTime = startAt + audioBuf.duration;
}

function resetStreamPlayback() {
  for (const source of streamSources) {
    try { source.stop(); } catch(e) {}
  }
  streamSources.clear();
  streamNextStartTime = 0;
  streamLastSample = null;
}

function stopStream() {
  if (streamController) { streamController.abort(); streamController = null; }
  resetStreamPlayback();
}

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
