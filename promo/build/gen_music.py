import os, sys, json, base64, requests, time
KEY=os.environ["GEMINI_API_KEY"]; MODEL=sys.argv[1]; TAG=sys.argv[2]
PROMPT=open("music_prompt.txt").read()
url=f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}"
body={"contents":[{"parts":[{"text":PROMPT}]}]}
if len(sys.argv)>3: body["generationConfig"]=json.loads(sys.argv[3])
t=time.time(); r=requests.post(url,json=body,timeout=900)
print(r.status_code, f"{time.time()-t:.0f}s")
if r.status_code!=200: print(r.text[:1500]); sys.exit(1)
d=r.json()
for c in d.get("candidates",[]):
    for i,p in enumerate(c["content"]["parts"]):
        if "inlineData" in p:
            mt=p["inlineData"]["mimeType"]; ext={"audio/mpeg":"mp3","audio/mp3":"mp3","audio/wav":"wav","audio/x-wav":"wav"}.get(mt,"bin")
            fn=f"audio/music/{TAG}_{i}.{ext}"; open(fn,"wb").write(base64.b64decode(p["inlineData"]["data"])); print("saved",fn,mt)
        elif "text" in p: print("TEXT:",p["text"][:800])
print(json.dumps(d.get("usageMetadata",{}))[:300])
