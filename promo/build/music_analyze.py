import sys, subprocess, numpy as np, imageio_ffmpeg
FF=imageio_ffmpeg.get_ffmpeg_exe()
def load(p, sr=22050):
    raw=subprocess.run([FF,"-loglevel","error","-i",p,"-ac","1","-ar",str(sr),"-f","f32le","-"],capture_output=True).stdout
    return np.frombuffer(raw,dtype=np.float32), sr
want=[12,19,30,50,69,86,104,110]
for p in sys.argv[1:]:
    x,sr=load(p); hop=sr//4; n=len(x)//hop
    rms=np.array([np.sqrt(np.mean(x[i*hop:(i+1)*hop]**2)) for i in range(n)])
    # chroma-ish novelty with spectral flux over 2s windows
    W=2048; spec=[]
    for i in range(n):
        s=x[i*hop:i*hop+W]
        if len(s)<W: s=np.pad(s,(0,W-len(s)))
        spec.append(np.log1p(np.abs(np.fft.rfft(s*np.hanning(W)))[:400]))
    S=np.array(spec); k=8
    nov=np.array([np.linalg.norm(S[max(0,i-k):i].mean(0)-S[i:i+k].mean(0)) if k<=i<n-k else 0 for i in range(n)])
    peaks=[i/4 for i in range(2,n-2) if nov[i]==nov[max(0,i-8):i+9].max() and nov[i]>np.percentile(nov,80)]
    print(p, "dur", round(len(x)/sr,2)); print("  boundaries:", [round(b,1) for b in peaks])
    print("  dist to wanted:", [min(abs(b-w) for b in peaks) for w in want])
    db=20*np.log10(rms+1e-9); print("  5s loudness:", " ".join(f"{int(db[i*20:(i+1)*20].mean())}" for i in range(n//20)))
