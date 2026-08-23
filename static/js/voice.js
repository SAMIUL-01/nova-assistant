/* ==========================================================================
   Nova voice engine  —  female persona (mandatory)

   The browser decides which text-to-speech voices exist, and on most systems
   the DEFAULT voice is male (Microsoft David on Windows, for example). So we
   never accept the default: we score every installed voice and pick the best
   female one.

   Rules implemented here, from the spec:
     - a female voice is always preferred
     - known male voices are excluded outright, never used as a fallback
     - if no female voice exists we say so clearly instead of going quiet
       or silently speaking in a male voice
     - the user can override voice, rate, pitch and volume
     - the choice survives a restart (localStorage)
     - Bangla text uses a Bangla voice when one is installed
   ========================================================================== */

window.NovaVoice = (() => {
  "use strict";

  // Voices shipped by Windows, macOS, Android and Chrome that are female.
  const FEMALE_NAMES = [
    "zira", "hazel", "susan", "linda", "heera", "catherine", "eva", "aria",
    "jenny", "michelle", "sonia", "natasha", "clara", "libby", "maisie",
    "samantha", "karen", "moira", "tessa", "fiona", "victoria", "ava",
    "allison", "serena", "kate", "amelie", "anna", "google uk english female",
    "google us english", "nabanita", "tanishaa", "sfg", "female",
  ];

  // Never use these, even if nothing else is available.
  const MALE_NAMES = [
    "david", "mark", "george", "ravi", "daniel", "alex", "fred", "guy",
    "ryan", "thomas", "brian", "eric", "christopher", "roger", "steffan",
    "prabhat", "madhur", "james", "william", "oliver", "liam", "male",
    "rishi", "arthur", "gordon", "aaron", "nathan", "jorge", "diego",
  ];

  const state = {
    voices: [],
    chosen: null,
    femaleAvailable: false,
    warning: "",
    settings: {
      voiceURI: localStorage.getItem("novaVoiceURI") || "",
      rate: parseFloat(localStorage.getItem("novaRate") || "1.02"),
      pitch: parseFloat(localStorage.getItem("novaPitch") || "1.15"),
      volume: parseFloat(localStorage.getItem("novaVolume") || "1"),
    },
    speaking: false,
    onStateChange: null,   // wired to the avatar
  };

  const lower = (v) => (v || "").toLowerCase();

  function isFemale(voice) {
    const n = lower(voice.name);
    if (n.includes("female")) return true;          // checked first, see below
    return FEMALE_NAMES.some((f) => n.includes(f));
  }

  function isMale(voice) {
    const n = lower(voice.name);
    // "female" literally contains "male", so a naive substring test marks
    // "Google UK English Female" as male. Always rule female out first.
    if (isFemale(voice)) return false;
    return MALE_NAMES.some((m) => {
      // Match "male" as a whole word, not inside another word.
      if (m === "male") return /\bmale\b/.test(n);
      return n.includes(m);
    });
  }

  /** Higher is better. Male voices are removed before scoring. */
  function score(voice, lang) {
    let points = 0;
    if (isFemale(voice)) points += 100;
    if (lower(voice.name).includes("female")) points += 40;

    // Prefer a voice that matches the language we are about to speak.
    if (lang && voice.lang) {
      if (lower(voice.lang) === lower(lang)) points += 50;
      else if (lower(voice.lang).slice(0, 2) === lower(lang).slice(0, 2)) points += 30;
    }
    // "Natural" / "Online" Microsoft voices sound far better than the old ones.
    const n = lower(voice.name);
    if (n.includes("natural")) points += 35;
    if (n.includes("online")) points += 10;
    if (n.includes("google")) points += 20;
    if (voice.localService) points += 5;
    return points;
  }

  function refreshVoices() {
    if (!window.speechSynthesis) return [];
    state.voices = window.speechSynthesis.getVoices() || [];
    const females = state.voices.filter((v) => !isMale(v) && isFemale(v));
    state.femaleAvailable = females.length > 0;

    if (!state.voices.length) {
      state.warning = "";                     // not loaded yet, ask again later
    } else if (!state.femaleAvailable) {
      state.warning =
        "No female voice is installed on this device, so Nova cannot use her " +
        "normal voice. On Windows: Settings → Time & language → Speech → " +
        "Add voices, and install a female voice such as Microsoft Zira or " +
        "Aria. Until then, please choose a voice manually below.";
    } else {
      state.warning = "";
    }
    return state.voices;
  }

  /** Bengali script → Bangla voice if we have one. */
  function detectLang(text) {
    return /[\u0980-\u09FF]/.test(text || "") ? "bn-BD" : (navigator.language || "en-US");
  }

  function pick(lang) {
    refreshVoices();
    if (!state.voices.length) return null;

    // 1. An explicit choice by the user always wins.
    if (state.settings.voiceURI) {
      const chosen = state.voices.find((v) => v.voiceURI === state.settings.voiceURI);
      if (chosen) return chosen;
    }

    // 2. Otherwise the best female voice for this language.
    const candidates = state.voices
      .filter((v) => !isMale(v))
      .map((v) => ({ voice: v, points: score(v, lang) }))
      .sort((a, b) => b.points - a.points);

    const best = candidates.find((c) => isFemale(c.voice)) || candidates[0];
    return best ? best.voice : null;
  }

  /** Voices for the Settings dropdown, females first and clearly marked. */
  function listForSettings() {
    refreshVoices();
    return state.voices
      .map((v) => ({
        uri: v.voiceURI,
        name: v.name,
        lang: v.lang,
        female: isFemale(v) && !isMale(v),
        male: isMale(v),
      }))
      .sort((a, b) => (b.female - a.female) || a.name.localeCompare(b.name));
  }

  function save(partial) {
    Object.assign(state.settings, partial);
    localStorage.setItem("novaVoiceURI", state.settings.voiceURI || "");
    localStorage.setItem("novaRate", String(state.settings.rate));
    localStorage.setItem("novaPitch", String(state.settings.pitch));
    localStorage.setItem("novaVolume", String(state.settings.volume));
  }

  function setSpeaking(on) {
    state.speaking = on;
    if (typeof state.onStateChange === "function") {
      state.onStateChange(on ? "speaking" : "idle");
    }
  }

  function stop() {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    setSpeaking(false);
  }

  /**
   * Speak some text in Nova's voice.
   * Returns false when nothing could be spoken, so the caller can warn.
   */
  function speak(text, { onWord } = {}) {
    if (!window.speechSynthesis || !text) return false;

    window.speechSynthesis.cancel();
    const lang = detectLang(text);
    const voice = pick(lang);

    const utterance = new SpeechSynthesisUtterance(text);
    if (voice) {
      utterance.voice = voice;
      utterance.lang = voice.lang || lang;
      state.chosen = voice;
    } else {
      utterance.lang = lang;
    }
    utterance.rate = state.settings.rate;
    utterance.pitch = state.settings.pitch;     // slightly high = softer, cuter
    utterance.volume = state.settings.volume;

    utterance.onstart = () => setSpeaking(true);
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    if (typeof onWord === "function") {
      utterance.onboundary = onWord;            // drives the mouth animation
    }

    window.speechSynthesis.speak(utterance);
    return true;
  }

  // Voices load asynchronously in Chrome.
  if (window.speechSynthesis) {
    refreshVoices();
    window.speechSynthesis.onvoiceschanged = () => {
      refreshVoices();
      if (typeof state.onVoicesReady === "function") state.onVoicesReady();
    };
  }

  return {
    speak,
    stop,
    pick,
    listForSettings,
    refreshVoices,
    save,
    isSpeaking: () => state.speaking,
    settings: () => ({ ...state.settings }),
    warning: () => state.warning,
    femaleAvailable: () => state.femaleAvailable,
    currentVoiceName: () => (state.chosen ? state.chosen.name : ""),
    set onStateChange(fn) { state.onStateChange = fn; },
    set onVoicesReady(fn) { state.onVoicesReady = fn; },
  };
})();
