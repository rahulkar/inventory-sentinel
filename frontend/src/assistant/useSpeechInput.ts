import { useCallback, useEffect, useRef, useState } from "react";

/* Minimal typings for the Web Speech API (Chrome, Edge, Safari); TypeScript's DOM lib does not ship them. */
interface SpeechRecognitionResultLike {
  isFinal: boolean;
  0: { transcript: string };
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
}
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function getCtor(): SpeechRecognitionCtor | null {
  const w = window as unknown as { SpeechRecognition?: SpeechRecognitionCtor; webkitSpeechRecognition?: SpeechRecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export interface SpeechInput {
  supported: boolean;
  listening: boolean;
  interim: string;
  error: string | null;
  start: () => void;
  stop: () => void;
  toggle: () => void;
}

/**
 * Browser speech-to-text for the composer. `onFinal` receives each finished phrase; `interim` holds the
 * phrase still being recognised so the UI can show it live. Recognition stops by itself after a pause.
 */
export function useSpeechInput(onFinal: (text: string) => void, lang = "en-GB"): SpeechInput {
  const ctor = useRef<SpeechRecognitionCtor | null>(null);
  const rec = useRef<SpeechRecognitionLike | null>(null);
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const onFinalRef = useRef(onFinal);
  onFinalRef.current = onFinal;

  useEffect(() => {
    ctor.current = getCtor();
    setSupported(!!ctor.current && window.isSecureContext);
    return () => rec.current?.abort();
  }, []);

  const stop = useCallback(() => {
    rec.current?.stop();
  }, []);

  const start = useCallback(() => {
    const C = ctor.current;
    if (!C || listening) return;
    setError(null);
    setInterim("");
    const r = new C();
    r.lang = lang;
    r.continuous = true;
    r.interimResults = true;
    r.maxAlternatives = 1;
    r.onresult = (e) => {
      let live = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        const text = res[0].transcript;
        if (res.isFinal) onFinalRef.current(text.trim());
        else live += text;
      }
      setInterim(live.trim());
    };
    r.onerror = (e) => {
      const msg =
        e.error === "not-allowed" || e.error === "service-not-allowed"
          ? "Microphone access was blocked. Allow it in the browser's site settings."
          : e.error === "no-speech"
            ? null
            : e.error === "network"
              ? "Speech recognition needs an internet connection in this browser."
              : `Speech recognition error: ${e.error}`;
      setError(msg);
    };
    r.onend = () => {
      setListening(false);
      setInterim("");
      rec.current = null;
    };
    rec.current = r;
    try {
      r.start();
      setListening(true);
    } catch {
      setError("Could not start the microphone.");
      rec.current = null;
    }
  }, [lang, listening]);

  const toggle = useCallback(() => (listening ? stop() : start()), [listening, start, stop]);

  return { supported, listening, interim, error, start, stop, toggle };
}
