import wave, numpy as np, json, sys
def segs(p, rel=-28, min_sil=0.09):
    w=wave.open(p); sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
    h=int(sr*0.005); n=len(x)//h
    e=np.sqrt(np.mean(x[:n*h].reshape(n,h)**2,axis=1)); e=np.convolve(e,np.ones(4)/4,'same')
    db=20*np.log10(e+1e-9); thr=np.percentile(db,95)+rel; v=db>thr
    out=[];i=0
    while i<n:
        if v[i]:
            j=i
            while j<n:
                if not v[j]:
                    k=j
                    while k<n and not v[k]: k+=1
                    if (k-j)*0.005>=min_sil or k>=n: break
                    j=k
                else: j+=1
            out.append((round(i*0.005,2),round(j*0.005,2))); i=j
        else: i+=1
    return out
res={}
for s in json.load(open("script.json")):
    sg=segs(f"audio/vo_proc/{s['id']}.wav"); res[s["id"]]=sg
    print(s["id"], s["text"]); print("   ", " ".join(f"{a:.2f}-{b:.2f}" for a,b in sg))
json.dump(res,open("audio/vo_proc/phrases.json","w"))
