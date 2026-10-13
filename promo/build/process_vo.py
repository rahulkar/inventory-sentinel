import json, wave, subprocess, numpy as np, imageio_ffmpeg, os
FF=imageio_ffmpeg.get_ffmpeg_exe()
TEMPO=1.06
os.makedirs("audio/vo_proc",exist_ok=True)
def load(p):
    w=wave.open(p); sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768; return x,sr
def save(p,x,sr):
    with wave.open(p,"wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes((np.clip(x,-1,1)*32767).astype(np.int16).tobytes())
def env_db(x,sr,hop=0.01):
    h=int(sr*hop); n=len(x)//h
    return 20*np.log10(np.sqrt(np.mean(x[:n*h].reshape(n,h)**2,axis=1))+1e-9)
def tighten(x,sr,thr=-42,maxpause=0.42,keep=0.32):
    db=env_db(x,sr); v=db>thr; h=int(sr*0.01)
    idx=np.where(v)[0]; a=max(idx[0]-4,0); b=min(idx[-1]+8,len(v))
    out=[]; i=a
    while i<b:
        if not v[i]:
            j=i
            while j<b and not v[j]: j+=1
            L=(j-i)*0.01
            if L>maxpause:
                k=int(keep/0.01); half=k//2
                seg1=x[i*h:(i+half)*h]; seg2=x[(j-(k-half))*h:j*h]
                f=int(0.02*sr); r=np.linspace(1,0,f)
                s=np.concatenate([seg1[:-f], seg1[-f:]*r+seg2[:f]*(1-r), seg2[f:]])
                out.append(s)
            else: out.append(x[i*h:j*h])
            i=j
        else:
            j=i
            while j<b and v[j]: j+=1
            out.append(x[i*h:j*h]); i=j
    y=np.concatenate(out); f=int(0.01*sr)
    y[:f]*=np.linspace(0,1,f); y[-f*3:]*=np.linspace(1,0,f*3)
    return y
script=json.load(open("script.json")); info={}
for s in script:
    x,sr=load(f"audio/vo/{s['id']}_Sulafat_0.wav")
    y=tighten(x,sr); tmp=f"audio/vo_proc/{s['id']}_t.wav"; save(tmp,y,sr)
    out=f"audio/vo_proc/{s['id']}.wav"
    af=(f"aresample=48000:filter_size=64:phase_shift=10:cutoff=0.97,atempo={TEMPO},highpass=f=75,"
        "equalizer=f=220:t=q:w=1.2:g=-1.5,equalizer=f=3500:t=q:w=1.0:g=2,equalizer=f=9000:t=h:w=1:g=1.5,"
        "acompressor=threshold=-20dB:ratio=3:attack=8:release=120:makeup=2")
    subprocess.run([FF,"-y","-loglevel","error","-i",tmp,"-af",af,"-ar","48000","-ac","1",out],check=True)
    z,sr2=load(out); info[s["id"]]=len(z)/sr2
    print(s["id"], f"{len(x)/sr:.2f} -> {len(y)/sr:.2f} -> {len(z)/sr2:.2f}")
print("total speech", round(sum(info.values()),2))
json.dump(info,open("audio/vo_proc/durations.json","w"),indent=1)
