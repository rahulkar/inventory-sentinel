import sys, wave, numpy as np
def segs(path, thr_db=-40, min_sil=0.18):
    w=wave.open(path); sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
    hop=int(sr*0.01); n=len(x)//hop
    e=np.array([np.sqrt(np.mean(x[i*hop:(i+1)*hop]**2)+1e-12) for i in range(n)])
    db=20*np.log10(e); voiced=db>thr_db
    out=[]; i=0
    while i<n:
        if voiced[i]:
            j=i
            while j<n:
                if not voiced[j]:
                    k=j
                    while k<n and not voiced[k]: k+=1
                    if (k-j)*0.01>=min_sil or k>=n: break
                    j=k
                else: j+=1
            out.append((i*0.01,j*0.01)); i=j
        else: i+=1
    return out, len(x)/sr, 20*np.log10(np.max(np.abs(x))+1e-9)
for p in sys.argv[1:]:
    s,d,pk=segs(p); print(p, f"dur={d:.2f} peak={pk:.1f}dB", " ".join(f"[{a:.2f}-{b:.2f}]" for a,b in s))
