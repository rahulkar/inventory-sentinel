import os, sys, base64, requests, wave, time
KEY=os.environ["GEMINI_API_KEY"]
def call(model, voice, body, out):
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={KEY}"
    body.setdefault("generationConfig",{}).update({"responseModalities":["AUDIO"],
         "speechConfig":{"voiceConfig":{"prebuiltVoiceConfig":{"voiceName":voice}}}})
    r=requests.post(url,json=body,timeout=300)
    if r.status_code!=200: print(out, r.status_code, r.text[:300]); return
    data=base64.b64decode(r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    if data[:4]==b"RIFF": open(out,"wb").write(data)
    else:
        with wave.open(out,"wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(data)
    with wave.open(out) as w: print(out, "dur", round(w.getnframes()/w.getframerate(),2))
text="Somewhere in your stores, right now, stock is quietly vanishing. Theft. Till fraud. Miscounts. Short deliveries. The odd typo."
structured=f"""# AUDIO PROFILE: The Storyteller
A warm, gently playful British narrator of a whimsical hand-drawn animated short.

## THE SCENE
A cosy recording booth. The narrator is telling a delightful little story to business leaders, smiling throughout.

### DIRECTOR'S NOTES
Style: warm, witty, wonder-filled; a twinkle in the voice. Crisp, clear diction.
Pace: lively but unhurried, natural short pauses at full stops.
Accent: Southern British English.

#### TRANSCRIPT
{text}"""
m="gemini-3.8-flash-tts"
call(m,"Sulafat",{"contents":[{"parts":[{"text":structured}]}]},"audio/tts_test/s_struct.wav")
call(m,"Sulafat",{"systemInstruction":{"parts":[{"text":"You are a warm, gently playful British narrator of a whimsical hand-drawn animated short. Read the user's text aloud exactly, smiling, lively but unhurried."}]},"contents":[{"parts":[{"text":text}]}]},"audio/tts_test/s_sys.wav")
call(m,"Sulafat",{"contents":[{"parts":[{"text":text}]}]},"audio/tts_test/s_plain.wav")
