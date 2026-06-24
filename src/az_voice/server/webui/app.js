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

// ── Streaming: feed PCM chunks into one persistent Web Audio worklet ──────────
let streamAudioCtx = null;
let streamPlayerNode = null;
let streamPlayerReady = null;
let streamUseWorklet = false;
let streamController = null;
let streamSampleRate = 24000;
let streamBufferedSamples = 0;
let streamBufferWaiters = [];
let streamFallbackNextStartTime = 0;
let streamFallbackSources = new Set();

const STREAM_PREBUFFER_SEC = 0.22;
const STREAM_FADE_SEC = 0.006;
const STREAM_HIGH_BUFFER_SEC = 20;
const STREAM_LOW_BUFFER_SEC = 10;

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

  try {
    streamUseWorklet = await ensureStreamPlayer();
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

    const resp = await fetch('/v1/audio/speech/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: streamController.signal,
    });
    if (!resp.ok || !resp.body) {
      let message = `Stream request failed (${resp.status})`;
      try {
        const errBody = await resp.json();
        message = errBody.error?.message || message;
      } catch (e) {}
      throw new Error(message);
    }

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
          const float32 = decodePcm16(data.data);
          queueStreamChunk(float32);
          chunkCount++;
          streamStatusText.textContent = 'Generating... (' + chunkCount + ' chunks)';
          if (streamUseWorklet) {
            await waitForStreamBufferBelow(STREAM_LOW_BUFFER_SEC);
          }
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

async function ensureStreamPlayer() {
  if (!streamAudioCtx) {
    streamAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (streamAudioCtx.state === 'suspended') await streamAudioCtx.resume();

  if (streamPlayerNode) return true;
  if (!streamAudioCtx.audioWorklet) {
    console.warn('[stream] AudioWorklet unavailable; using fallback scheduler.');
    return false;
  }

  try {
    if (!streamPlayerReady) {
      streamPlayerReady = withTimeout(
        streamAudioCtx.audioWorklet.addModule('/stream-processor.js?v=3'),
        3000,
        'AudioWorklet module load timed out',
      );
    }
    await streamPlayerReady;

    streamPlayerNode = new AudioWorkletNode(streamAudioCtx, 'streaming-audio-processor', {
      numberOfInputs: 0,
      numberOfOutputs: 1,
      outputChannelCount: [1],
    });
    streamPlayerNode.port.onmessage = (event) => {
      if (event.data && event.data.type === 'buffer') {
        streamBufferedSamples = event.data.samples || 0;
        notifyStreamBufferWaiters();
      }
    };
    streamPlayerNode.connect(streamAudioCtx.destination);
    configureStreamPlayer();
    return true;
  } catch (err) {
    console.warn('[stream] AudioWorklet init failed; using fallback scheduler.', err);
    streamPlayerReady = null;
    streamPlayerNode = null;
    return false;
  }
}

function withTimeout(promise, ms, message) {
  let timeoutId = null;
  const timeout = new Promise((_, reject) => {
    timeoutId = setTimeout(() => reject(new Error(message)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timeoutId));
}

function configureStreamPlayer() {
  if (!streamPlayerNode || !streamAudioCtx) return;
  streamPlayerNode.port.postMessage({
    type: 'config',
    prebufferSamples: Math.floor(streamAudioCtx.sampleRate * STREAM_PREBUFFER_SEC),
    fadeSamples: Math.floor(streamAudioCtx.sampleRate * STREAM_FADE_SEC),
  });
}

function queueStreamChunk(samples) {
  if (!samples.length) return;

  const outputSamples = resampleIfNeeded(samples, streamSampleRate, streamAudioCtx.sampleRate);
  if (!streamUseWorklet || !streamPlayerNode) {
    queueFallbackStreamChunk(outputSamples);
    return;
  }

  streamBufferedSamples += outputSamples.length;
  streamPlayerNode.port.postMessage(
    { type: 'pcm', samples: outputSamples.buffer },
    [outputSamples.buffer],
  );
  notifyStreamBufferWaiters();
}

function resampleIfNeeded(samples, fromRate, toRate) {
  if (!fromRate || !toRate || fromRate === toRate || samples.length < 2) {
    return samples;
  }

  const ratio = toRate / fromRate;
  const outputLength = Math.max(1, Math.round(samples.length * ratio));
  const output = new Float32Array(outputLength);
  for (let i = 0; i < outputLength; i++) {
    const srcPos = i / ratio;
    const left = Math.floor(srcPos);
    const right = Math.min(samples.length - 1, left + 1);
    const frac = srcPos - left;
    output[i] = samples[left] * (1 - frac) + samples[right] * frac;
  }
  return output;
}

function queueFallbackStreamChunk(samples) {
  const audioBuf = streamAudioCtx.createBuffer(1, samples.length, streamAudioCtx.sampleRate);
  audioBuf.getChannelData(0).set(samples);

  const source = streamAudioCtx.createBufferSource();
  const gain = streamAudioCtx.createGain();
  source.buffer = audioBuf;
  source.connect(gain);
  gain.connect(streamAudioCtx.destination);
  source.onended = () => streamFallbackSources.delete(source);

  const now = streamAudioCtx.currentTime;
  const isFirstChunk = streamFallbackNextStartTime === 0;
  const underrun = !isFirstChunk && streamFallbackNextStartTime <= now;
  const startAt = isFirstChunk
    ? now + STREAM_PREBUFFER_SEC
    : underrun
      ? now + 0.02
      : streamFallbackNextStartTime;

  if (isFirstChunk || underrun) {
    const fadeSec = STREAM_FADE_SEC;
    gain.gain.setValueAtTime(0, startAt);
    gain.gain.linearRampToValueAtTime(1, startAt + fadeSec);
  } else {
    gain.gain.setValueAtTime(1, startAt);
  }

  streamFallbackSources.add(source);
  source.start(startAt);
  streamFallbackNextStartTime = startAt + audioBuf.duration;
}

function streamBufferedSeconds() {
  if (!streamAudioCtx || streamAudioCtx.sampleRate <= 0) return 0;
  return streamBufferedSamples / streamAudioCtx.sampleRate;
}

async function waitForStreamBufferBelow(seconds) {
  while (streamController && streamBufferedSeconds() > STREAM_HIGH_BUFFER_SEC) {
    await new Promise((resolve) => {
      let waiter = null;
      const timeout = setTimeout(() => {
        streamBufferWaiters = streamBufferWaiters.filter((item) => item !== waiter);
        resolve();
      }, 100);
      waiter = () => {
        clearTimeout(timeout);
        resolve();
      };
      streamBufferWaiters.push(waiter);
    });
    if (streamBufferedSeconds() <= seconds) break;
  }
}

function notifyStreamBufferWaiters() {
  if (streamBufferedSeconds() > STREAM_LOW_BUFFER_SEC || streamBufferWaiters.length === 0) return;
  const waiters = streamBufferWaiters;
  streamBufferWaiters = [];
  for (const resolve of waiters) resolve();
}

function resetStreamPlayback() {
  streamBufferedSamples = 0;
  notifyStreamBufferWaiters();
  if (streamPlayerNode) {
    streamPlayerNode.port.postMessage({ type: 'reset' });
  }
  for (const source of streamFallbackSources) {
    try { source.stop(); } catch (e) {}
  }
  streamFallbackSources.clear();
  streamFallbackNextStartTime = 0;
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
