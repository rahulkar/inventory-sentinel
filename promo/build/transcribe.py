import os, sys, base64, requests
KEY=os.environ["GEMINI_API_KEY"]
for p in sys.argv[1:]:
    b=base64.b64encode(open(p,"rb").read()).decode()
    url=f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-transcribe:generateContent?key={KEY}"
    r=requests.post(url,json={"contents":[{"parts":[{"inlineData":{"mimeType":"audio/wav","data":b}}]}]},timeout=300)
    try: pp=r.json()["candidates"][0]["content"]["parts"][0]; print(p, "=>", (pp.get("text") or pp.get("audioTranscription",{}).get("text","")).strip())
    except Exception: print(p, r.status_code, r.text[:300])
