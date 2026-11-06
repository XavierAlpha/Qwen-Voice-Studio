import {t} from './i18n.js';
export class Recorder {
  constructor(){this.active=false;this.timer=null;}
  async start(onLimit){
    if(!navigator.mediaDevices?.getUserMedia)throw new Error(t('error.microphone'));
    this.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
    try{
      this.context=new AudioContext();await this.context.audioWorklet.addModule('/ui/recorder-worklet.js');
      this.chunks=[];this.recorder=new AudioWorkletNode(this.context,'qvs-recorder');
      this.recorder.port.onmessage=e=>{if(e.data.data)this.chunks.push(e.data.data);if(e.data.done)this.done?.();};
      const source=this.context.createMediaStreamSource(this.stream),gain=this.context.createGain();gain.gain.value=0;
      source.connect(this.recorder);this.recorder.connect(gain);gain.connect(this.context.destination);
      this.active=true;this.timer=setTimeout(onLimit,55000);
    }catch(error){await this.abort();throw error;}
  }
  async stop(){
    if(!this.active)return null;
    this.active=false;clearTimeout(this.timer);
    await new Promise(resolve=>{this.done=resolve;this.recorder.port.postMessage('stop');setTimeout(resolve,1200);});
    const rate=this.context.sampleRate,total=this.chunks.reduce((a,b)=>a+b.length,0);
    await this.abort();
    const buffer=new ArrayBuffer(44+total*2),view=new DataView(buffer);
    const text=(offset,value)=>[...value].forEach((c,i)=>view.setUint8(offset+i,c.charCodeAt(0)));
    text(0,'RIFF');view.setUint32(4,36+total*2,true);text(8,'WAVE');text(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,rate,true);view.setUint32(28,rate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);text(36,'data');view.setUint32(40,total*2,true);
    let pos=44;for(const chunk of this.chunks){for(const sample of chunk){const x=Math.min(1,Math.max(-1,sample));view.setInt16(pos,x<0?x*32768:x*32767,true);pos+=2;}}
    this.chunks=[];return new File([buffer],'microphone.wav',{type:'audio/wav'});
  }
  async abort(){clearTimeout(this.timer);this.stream?.getTracks().forEach(t=>t.stop());if(this.context?.state!=='closed')await this.context?.close();this.active=false;}
}
