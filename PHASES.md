# Build Phases

Nova is being upgraded into a full JARVIS-style assistant one phase at a time.
Each phase must pass its tests, and must not break the phase before it.

| # | Phase | Status |
|---|---|---|
| 1 | Stabilise existing Nova | ✅ done |
| 2 | JARVIS core: router, tool registry, security & permissions | ✅ done |
| 3 | PC control (volume, media keys, windows, screenshots) | ⬜ next |
| 4 | Browser / web automation | ⬜ |
| 5 | Communication & media (WhatsApp, Telegram, music) | ⬜ |
| 6 | Multi-step agent (task planning) | ⬜ |
| 7 | Advanced memory, vision, scheduler | ⬜ |
| 8 | Anime avatar, female voice persona, wake word | ⬜ |
| 9 | Final integrated experience | ⬜ |

---

## Phase 1 — Stabilise ✅

Baseline confirmed green before any new work: chat, streaming, history,
memory, file upload, voice I/O, rate limiting, login.

**Tests: 78 passing.**

## Phase 2 — JARVIS core ✅

- **Risk levels** on every tool: `SAFE`, `MODERATE`, `SENSITIVE`, `DESTRUCTIVE`
- **Security layer** (`app/services/security.py`) that every tool call passes
  through. Returns allow / confirm / deny.
- **Permission manager**: five capabilities the user can switch on and off,
  stored in SQLite, editable from the UI.
- **Command router** (`app/services/router.py`): one pipeline for typed and
  spoken commands, with a fast path that skips the model for common commands.

### Invariants (enforced by tests, not by convention)

1. `SENSITIVE` and `DESTRUCTIVE` always confirm — settings can only make Nova
   stricter, never looser.
2. Unknown tools are denied, so the model cannot invent `run_shell`.
3. No arbitrary-command tool exists anywhere in the registry.
4. A disabled capability stays disabled even if the user presses Confirm.
5. Secrets are scrubbed from the audit log.
6. The router cannot bypass the security layer.

**Tests: 125 passing** (47 new). Fast path measured at ~150 ms versus roughly
a second and a half through the model.

## Phase 3 — PC control (next)

Planned: volume, play/pause/next, window focus, screenshot capture. Each new
tool gets a risk level and a capability, so the security layer covers it the
day it is added.
