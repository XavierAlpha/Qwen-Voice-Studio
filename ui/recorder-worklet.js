class MonoRecorder extends AudioWorkletProcessor {
  constructor(){super();this.buffer=new Float32Array(4096);this.offset=0;this.stopped=false;this.port.onmessage=e=>{if(e.data==='stop'){this.flush();this.stopped=true;this.port.postMessage({done:true});}};}
  flush(){if(this.offset){const data=this.buffer.slice(0,this.offset);this.port.postMessage({data},[data.buffer]);this.offset=0;}}
  process(inputs){if(this.stopped)return false;const channels=inputs[0];if(channels?.length){const first=channels[0];for(let i=0;i<first.length;i++){let value=0;for(const channel of channels)value+=channel[i];this.buffer[this.offset++]=value/channels.length;if(this.offset===this.buffer.length)this.flush();}}return true;}
}
registerProcessor('qvs-recorder',MonoRecorder);
