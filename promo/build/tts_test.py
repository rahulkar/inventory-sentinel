import os, sys, json, base64, requests, wave, time
KEY=os.environ["GEMINI_API_KEY"]
def tts(model, voice, text, style, out):
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={KEY}"
    body={"contents":[{"parts":[{"text": f"{style}\n\n{text}"}]}],
          "generationConfig":{"responseModalities":["AUDIO"],
             "speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":voice}}}}}
    t=time.time(); r=requests.post(url,json=body,timeout=300)
    if r.status_code!=200: print(model,voice,r.status_code,r.text[:400]); return
    p=r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
    data=base64.b64decode(p["data"]); print(model, voice, p["mimeType"], len(data), f"{time.time()-t:.1f}s")
    if data[:4]==b"RIFF":
        open(out,"wb").write(data)
    else:
        with wave.open(out,"wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(data)
    with wave.open(out) as w: print("  sr",w.getframerate(),"ch",w.getnchannels(),"dur",w.getnframes()/w.getframerate())
style="Read this aloud as the warm, gently playful British narrator of a hand-drawn animated short film. Smile in your voice, unhurried but lively, with clear crisp diction:"
text="Somewhere in your stores, right now, stock is quietly vanishing. Theft. Till fraud. Miscounts. Short deliveries. The odd typo."
for model in sys.argv[1].split(","):
  for v in sys.argv[2].split(","):
    tts(model,v,text,style,f"audio/tts_test/{model}_{v}.wav")
