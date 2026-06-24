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

// ── Tab switching ──────────────────────────────────────────────────────────────
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
  });
});

// ── True streaming with AudioWorklet ──────────────────────────────────────────
let streamAudioCtx = null;
let streamWorkletNode = null;
let streamController = null;

const streamBtn = document.getElementById('streamBtn');
const stopStreamBtn = document.getElementById('stopStreamBtn');
const streamStatus = document.getElementById('streamStatus');
const streamStatusText = document.getElementById('streamStatusText');
const streamWave = document.getElementById('streamWave');
const streamErrorSection = document.getElementById('streamErrorSection');
const streamErrorText = document.getElementById('streamErrorText');
const streamTextInput = document.getElementById('streamTextInput');
const streamStyleInput = document.getElementById('streamStyleInput');

// Build wave animation bars
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

  // Initialize audio - try AudioWorklet first, fallback to ScriptProcessor
  if (!streamAudioCtx) {
    streamAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (streamAudioCtx.state === 'suspended') await streamAudioCtx.resume();

  // Try AudioWorklet for gapless playback
  let useWorklet = false;
  if (!streamWorkletNode) {
    try {
      await streamAudioCtx.audioWorklet.addModule('stream-processor.js');
      streamWorkletNode = new AudioWorkletNode(streamAudioCtx, 'streaming-audio-processor');
      streamWorkletNode.connect(streamAudioCtx.destination);
      useWorklet = true;
      console.log('[stream] AudioWorklet initialized');
    } catch(e) {
      console.warn('[stream] AudioWorklet failed, using fallback:', e);
      useWorklet = false;
    }
  }

  if (useWorklet) {
    if (useWorklet && streamWorkletNode) streamWorkletNode.port.postMessage({ type: 'stop' });
  }

  streamController = new AbortController();
  const payload = { model: 'voxcpm2', input: text };
  const style = streamStyleInput.value.trim();
  if (style) payload.control_instruction = style;

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
    streamStatusText.textContent = 'Streaming...';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = JSON.parse(line.slice(6));

        if (data.type === 'audio') {
          const pcmBytes = Uint8Array.from(atob(data.data), c => c.charCodeAt(0));
          const int16 = new Int16Array(pcmBytes.buffer);
          const float32 = new Float32Array(int16.length);
          for (let j = 0; j < int16.length; j++) float32[j] = int16[j] / 32768;
          if (useWorklet && streamWorkletNode) {
            streamWorkletNode.port.postMessage({ type: 'pcm', samples: float32 });
          } else {
            playPcmFallback(float32);
          }
          chunkCount++;
          streamStatusText.textContent = 'Streaming... (' + chunkCount + ' chunks)';
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
    if (useWorklet && streamWorkletNode) streamWorkletNode.port.postMessage({ type: 'stop' });
    setTimeout(() => {
      streamStatus.hidden = true;
      streamBtn.hidden = false;
      stopStreamBtn.hidden = true;
    }, 2000);
  }
}

// Fallback playback - ring buffer with proper tail tracking for crossfade
let fallbackProcessor = null;
let fallbackQueue = [];
let fallbackReadPos = 0;
let fallbackTail = [];  // Last 64 samples actually played (for crossfade)
const CF = 64;  // crossfade length

function playPcmFallback(samples) {
  // Crossfade: blend first CF samples with tail of previously PLAYED audio
  if (fallbackTail.length >= CF && samples.length > CF) {
    for (let i = 0; i < CF; i++) {
      const t = (i + 1) / (CF + 1);
      samples[i] = fallbackTail[Math.max(0, fallbackTail.length - CF + i)] * (1 - t) + samples[i] * t;
    }
  }
  // Update tail with new samples
  fallbackTail = Array.from(samples);
  Array.prototype.push.apply(fallbackQueue, samples);
  
  if (!fallbackProcessor) {
    fallbackProcessor = streamAudioCtx.createScriptProcessor(2048, 0, 1);
    fallbackProcessor.onaudioprocess = (e) => {
      const out = e.outputBuffer.getChannelData(0);
      const avail = fallbackQueue.length - fallbackReadPos;
      const copy = Math.min(out.length, avail);
      for (let i = 0; i < copy; i++) out[i] = fallbackQueue[fallbackReadPos + i];
      // If queue runs dry, fade to silence smoothly
      if (copy < out.length) {
        const fadeLen = Math.min(64, out.length - copy);
        for (let i = 0; i < fadeLen; i++) {
          out[copy + i] = (copy > 0 ? out[copy - 1] : 0) * (1 - i / fadeLen);
        }
        out.fill(0, copy + fadeLen);
      }
      fallbackReadPos += copy;
      if (fallbackReadPos > 65536) { fallbackQueue = fallbackQueue.slice(fallbackReadPos); fallbackReadPos = 0; }
    };
    fallbackProcessor.connect(streamAudioCtx.destination);
  }
}

function stopStream() {
  if (streamController) { streamController.abort(); streamController = null; }
  if (streamWorkletNode) streamWorkletNode.port.postMessage({ type: 'stop' });
  if (fallbackProcessor) {
    fallbackProcessor.disconnect();
    fallbackProcessor = null;
  }
  fallbackQueue = [];
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
