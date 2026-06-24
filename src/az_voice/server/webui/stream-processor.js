// AudioWorklet with proper tail tracking for crossfade
class StreamingAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];
    this.tail = [];
    this.CF = 64;
    this.port.onmessage = (e) => {
      if (e.data.type === 'pcm') {
        let samples = new Float32Array(e.data.samples);
        // Crossfade with tail
        if (this.tail.length >= this.CF && samples.length > this.CF) {
          for (let i = 0; i < this.CF; i++) {
            const t = (i + 1) / (this.CF + 1);
            const tailIdx = Math.max(0, this.tail.length - this.CF + i);
            samples[i] = this.tail[tailIdx] * (1 - t) + samples[i] * t;
          }
        }
        this.tail = Array.from(samples);
        for (let i = 0; i < samples.length; i++) this.buffer.push(samples[i]);
      } else if (e.data.type === 'stop') {
        this.buffer.length = 0;
        this.tail = [];
      }
    };
  }

  process(inputs, outputs, parameters) {
    const output = outputs[0];
    for (let ch = 0; ch < output.length; ch++) {
      const out = output[ch];
      for (let i = 0; i < out.length; i++) {
        out[i] = this.buffer.length > 0 ? this.buffer.shift() : 0;
      }
    }
    return true;
  }
}

registerProcessor('streaming-audio-processor', StreamingAudioProcessor);
