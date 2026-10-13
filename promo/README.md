# Inventory Sentinel: two-minute promo

A whimsical, hand-drawn explainer (120 s, 1080p) for leadership audiences. It covers the problem (shrinkage), plug-and-play
connection over MCP, unsupervised detection, the Executive screen, the agentic assistant and the learning loop.

| File | What it is |
|---|---|
| `inventory-sentinel-promo.html` | The animation: pure JavaScript on a canvas, fully self-contained (fonts, soundtrack and data inlined). Open it in Chrome or Edge and press play. Keys: space play/pause, ← → seek, `c` captions, `f` full screen. |
| `inventory-sentinel-promo.mp4` | The same animation rendered frame-exact to H.264 1080p30 + AAC, for slides, email and social. |
| `inventory-sentinel-promo.srt` | Captions. |

Every figure on screen comes from the demo vendor run in `data/` (run `run_470a7cf1`, Isolation Forest): £144k stock value
at risk across 40 stores, 99 alerts worth a visit for 120 investigator hours (about £19k expected back, 5x the cost),
1.7x the rule of thumb's average precision (README, *Measured results*), the planner's real top five alerts and the
store x category heatmap.

## How it is made

- `src/engine.js`: the hand-drawn renderer. Seeded wobbly strokes with a second pencil pass, 12 fps "line boil",
  watercolour fills with granulation, hand-lettered text with per-letter jitter, paper texture, film grain, vignette.
  Everything is a pure function of time, so playback and video export are identical.
- `src/characters.js`: Sentinel the owl, the raccoon, bean people, the AI agent bots and props.
- `src/scenes1.js`, `src/scenes2.js`: the nine scenes and the cue table (`CUE`) that syncs picture to narration.
- `src/main.js`: camera rig (whip pans, the dive into the laptop screen), player UI, captions, export hook.
- `build/`: the asset pipeline.
  - `gen_tts.py`: narration with `gemini-2.5-pro-preview-tts` (voice Sulafat, British storyteller direction), one call per scene.
  - `process_vo.py`: trims, tightens long pauses, 1.06x tempo, EQ and compression.
  - `gen_music.py` + `music_prompt.txt`: score from Lyria 3.5 with timestamped sections matched to the scenes.
  - `mix.py`: synthesises ~400 sound effects from the same cue table, voice-keyed level-adaptive ducking, loudness to -15 LUFS.
  - `build.py`: inlines everything into the single HTML file. `tools/export.js`: renders the MP4.

Rebuild after editing `src/`:

```bash
python promo/build/build.py
```

Re-render the video (needs `npm install` in `promo/build/tools` and Chrome):

```bash
node promo/build/tools/export.js promo/inventory-sentinel-promo.html promo/inventory-sentinel-promo.mp4 <ffmpeg> promo/build/audio/final_mix.wav 30
```
