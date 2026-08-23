# Build Phases

Nova is being upgraded into a full JARVIS-style assistant one phase at a time.
Each phase must pass its tests, and must not break the phase before it.

| # | Phase | Status |
|---|---|---|
| 1 | Stabilise existing Nova | ✅ done |
| 2 | JARVIS core: router, tool registry, security & permissions | ✅ done |
| 3 | PC control (volume, media keys, screenshots, windows) | ✅ done |
| 4 | Web search | ✅ done |
| 5 | Communication & media (WhatsApp, Telegram, Instagram, music) | ✅ done |
| 6 | Multi-step agent | 🟡 partial — chains up to 4 tools per turn, no visible plan yet |
| 7 | Scheduler & screen understanding | ⬜ not started |
| 8 | Anime avatar + female voice persona | ✅ done (wake word ⬜) |
| 9 | Final integration pass | ⬜ not started |

**Tests: 150 passing** on Windows and Linux, Python 3.11 and 3.12.

---

## Phase 1 — Stabilise ✅

Baseline confirmed green before any new work: chat, streaming, history,
memory, file upload, voice I/O, rate limiting, login. 78 tests.

## Phase 2 — JARVIS core ✅

- **Risk levels** on every tool: `SAFE`, `MODERATE`, `SENSITIVE`, `DESTRUCTIVE`
- **Security layer** (`app/services/security.py`) that every tool call passes
  through. Returns allow / confirm / deny.
- **Permission manager**: capabilities the user switches on and off, stored in
  SQLite, editable from the UI.
- **Command router** (`app/services/router.py`): one pipeline for typed and
  spoken commands, with a fast path that skips the model (~150 ms).

### Invariants (enforced by tests, not by convention)

1. `SENSITIVE` and `DESTRUCTIVE` always confirm — settings can only make Nova
   stricter, never looser.
2. Unknown tools are denied, so the model cannot invent `run_shell`.
3. No arbitrary-command tool exists anywhere in the registry.
4. A disabled capability stays disabled even if the user presses Confirm.
5. Secrets are scrubbed from the audit log.
6. The router cannot bypass the security layer.

## Phase 3 — PC control ✅

Volume up/down/mute, play-pause, next, previous, screenshots, window list.

Volume and media keys use plain `ctypes` on Windows — no extra dependency, and
they work with anything that responds to media keys (Spotify, YouTube, VLC).
On Linux and macOS the Windows-only calls say so clearly instead of pretending.

Screenshots and window titles are `SENSITIVE`, and the **Screen capability is
off by default** because it can reveal a bank page or a private chat.

## Phase 4 — Web search ✅

DuckDuckGo HTML endpoint: no API key, no account, no cost. Lets Nova answer
questions about things that happened after the model's training cut-off.

## Phase 5 — Communication & media ✅

WhatsApp, Telegram, Messenger, Instagram, email drafts, and music on YouTube /
YouTube Music / Spotify.

**Nova never sends a message by herself.** She opens the real app with the
message already typed, and you press Send. Driving WhatsApp Web with a headless
browser was rejected on purpose: it breaks whenever Meta changes their HTML, it
can get an account flagged, and it makes it easy to send something you never
saw. Every messaging tool is `SENSITIVE`, so it also asks first.

## Phase 8 — Avatar & female voice ✅

- **Anime-style female avatar** drawn as inline SVG: sharp at any size,
  themeable, no image files. Four states — idle (float + irregular blink),
  listening (glowing aura), thinking (drifting thought dots), speaking (mouth
  driven by the real speech events, so it stops exactly when the voice does).
- **Female voice, enforced.** The browser default is usually male (Microsoft
  David on Windows), so Nova scores every installed voice and picks the best
  female one. Male voices are excluded outright, never used as a fallback.
- If no female voice exists, Settings shows a **clear message with install
  instructions** instead of quietly using a male voice.
- Voice, speed, pitch and volume are adjustable and survive a restart.
- Bengali text automatically asks for a Bangla voice when one is installed.

> Bug worth remembering: `"female".includes("male")` is `true`, so a naive
> substring check marks *Google UK English Female* as male. Female is now
> always ruled out first, and `male` is matched as a whole word.

## Still to do

- **Phase 6** — a visible task plan ("1. search 2. summarise 3. save") rather
  than just chained tool calls.
- **Phase 7** — reminders/scheduler, and screen understanding via a vision
  model (the current model is text-only).
- **Wake word** — always-on "Hey Nova" listening.
- **Phase 9** — final polish pass across everything.
