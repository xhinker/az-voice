// AudioWorklet processor for gapless PCM streaming
class StreamingAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];
    this.sampleRate = 48000;
    this.port.onmessage = (e) => {
      if (e.data.type === 'pcm') {
        // Append int16 PCM samples to buffer
        for (let i = 0; i < e.data.samples.length; i++) {
          this.buffer.push(e.data.samples[i] / 32768);
        }
      } else if (e.data.type === 'stop') {
        this.buffer = [];
      }
    };
  }

  process(inputs, outputs, parameters) {
    const output = outputs[0];
    const channel = output[0];
    
    // Fill output buffer from our queue
    for (let i = 0; i < channel.length; i++) {
      if (this.buffer.length > 0) {
        channel[i] = this.buffer.shift();
      } else {
        channel[i] = 0;
      }
    }
    
    return true; // Keep processor alive
  }
}

registerProcessor('streaming-audio-processor', StreamingAudioProcessor);
