class StreamingAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.readOffset = 0;
    this.queuedSamples = 0;
    this.started = false;
    this.prebufferSamples = 8192;
    this.fadeSamples = 128;
    this.fadeRemaining = 0;
    this.reportCountdown = 0;

    this.port.onmessage = (e) => {
      const msg = e.data || {};

      if (msg.type === 'config') {
        if (Number.isFinite(msg.prebufferSamples)) {
          this.prebufferSamples = Math.max(0, Math.floor(msg.prebufferSamples));
        }
        if (Number.isFinite(msg.fadeSamples)) {
          this.fadeSamples = Math.max(0, Math.floor(msg.fadeSamples));
        }
      } else if (msg.type === 'pcm') {
        const samples = new Float32Array(msg.samples);
        if (samples.length > 0) {
          this.queue.push(samples);
          this.queuedSamples += samples.length;
        }
      } else if (msg.type === 'reset') {
        this._reset();
      }
    };
  }

  process(inputs, outputs, parameters) {
    const output = outputs[0];
    if (!output || output.length === 0) return true;

    const frameCount = output[0].length;

    if (!this.started) {
      if (this.queuedSamples < this.prebufferSamples) {
        this._writeSilence(output);
        this._report(frameCount);
        return true;
      }
      this.started = true;
      this.fadeRemaining = this.fadeSamples;
    }

    for (let i = 0; i < frameCount; i++) {
      let sample = this._readSample();
      if (sample === null) {
        sample = 0;
        this.started = false;
      } else if (this.fadeRemaining > 0) {
        const fadeIndex = this.fadeSamples - this.fadeRemaining;
        sample *= fadeIndex / Math.max(1, this.fadeSamples);
        this.fadeRemaining--;
      }

      for (let ch = 0; ch < output.length; ch++) {
        output[ch][i] = sample;
      }
    }

    this._report(frameCount);
    return true;
  }

  _readSample() {
    while (this.queue.length > 0) {
      const chunk = this.queue[0];
      if (this.readOffset < chunk.length) {
        const sample = chunk[this.readOffset];
        this.readOffset++;
        this.queuedSamples--;
        if (this.readOffset >= chunk.length) {
          this.queue.shift();
          this.readOffset = 0;
        }
        return sample;
      }
      this.queue.shift();
      this.readOffset = 0;
    }
    return null;
  }

  _writeSilence(output) {
    for (let ch = 0; ch < output.length; ch++) {
      output[ch].fill(0);
    }
  }

  _reset() {
    this.queue = [];
    this.readOffset = 0;
    this.queuedSamples = 0;
    this.started = false;
    this.fadeRemaining = 0;
  }

  _report(frameCount) {
    this.reportCountdown -= frameCount;
    if (this.reportCountdown <= 0) {
      this.port.postMessage({
        type: 'buffer',
        samples: this.queuedSamples,
        started: this.started,
      });
      this.reportCountdown = Math.max(1, Math.floor(sampleRate / 4));
    }
  }
}

registerProcessor('streaming-audio-processor', StreamingAudioProcessor);
