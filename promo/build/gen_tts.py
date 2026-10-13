import os, sys, json, base64, requests, wave, concurrent.futures as cf
KEY=os.environ["GEMINI_API_KEY"]; MODEL=os.environ.get("TTS_MODEL","gemini-2.5-pro-preview-tts"); VOICE=sys.argv[1] if len(sys.argv)>1 else "Sulafat"
TAKES=int(sys.argv[2]) if len(sys.argv)>2 else 2
os.makedirs("audio/vo",exist_ok=True)
def prompt(s): return f"""# AUDIO PROFILE: The Storyteller
A warm, gently playful British narrator of a whimsical, hand-drawn animated short film about a clever owl who guards a shop's stock.

## THE SCENE
A cosy recording booth. The narrator tells a delightful little story to busy business leaders, smiling throughout. Premium, polished, intimate microphone.

### DIRECTOR'S NOTES
Style: warm, witty, wonder-filled, with a twinkle in the voice. Crisp, clear diction.
Pace: brisk and lively, like a charming film-trailer storyteller; keep pauses between sentences short.
Accent: Southern British English.
This line: {s['mood']}

#### TRANSCRIPT
{s['text']}"""
def go(s,k):
    out=f"audio/vo/{s['id']}_{VOICE}_{k}.wav"
    if os.path.exists(out): return out
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}"
    body={"contents":[{"parts":[{"text":prompt(s)}]}],"generationConfig":{"responseModalities":["AUDIO"],"speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":VOICE}}}}}
    for attempt in range(3):
        r=requests.post(url,json=body,timeout=300)
        if r.status_code==200: break
        print("ERR",out,r.status_code,r.text[:300].replace(chr(10),' '))
        if r.status_code==429: return None
    else: return None
    try: p=r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
    except Exception: print("BAD",out,r.text[:300]); return None
    data=base64.b64decode(p["data"])
    if data[:4]==b"RIFF": open(out,"wb").write(data)
    else:
        with wave.open(out,"wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(data)
    return out
script=json.load(open("script.json"))
ids=sys.argv[3].split(",") if len(sys.argv)>3 else None
jobs=[(s,k) for s in script for k in range(TAKES) if not ids or s["id"] in ids]
for a in jobs:
    f=go(*a)
    if not f: continue
    with wave.open(f) as w: print(f, round(w.getnframes()/w.getframerate(),2), flush=True)
