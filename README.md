# Nova

[![tests](https://github.com/SAMIUL-01/nova-assistant/actions/workflows/tests.yml/badge.svg)](https://github.com/SAMIUL-01/nova-assistant/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

Your own personal AI assistant, running on your machine. Nova chats, remembers
who you are, listens and speaks, reads your documents, and can **do things on
your computer** — open apps and websites, manage files, run git.

---

## ▶ Try Nova right now

**No install, no API key** — runs in your browser in about two minutes:

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/SAMIUL-01/nova-assistant?quickstart=1)

It starts in demo mode with fake replies so you can click around. Add an
OpenRouter key to `.env` and set `AI_OFFLINE_MOCK=0` for real answers.

**Want your own Nova on the internet?** One click, your own copy, your own URL:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/SAMIUL-01/nova-assistant)

**Want the full JARVIS version that controls your PC?** That one has to run on
your own computer — download, then double-click `SETUP.bat`:

[⬇ Download Nova](https://github.com/SAMIUL-01/nova-assistant/archive/refs/heads/main.zip)

> Why can't you just click a link and have the full thing? GitHub only serves
> files — it cannot run a Python server, and no cloud server can open apps on
> *your* laptop. Codespaces and Render give you the chat; `SETUP.bat` gives you
> the assistant that controls your machine.

---

Frontend is plain HTML/CSS/JavaScript. Backend is Python + FastAPI. The AI comes
from OpenRouter (NVIDIA Nemotron 3.5 Lightning, free tier). Your API key stays on
the server and is never sent to the browser.

---

## Features

| Feature | Status |
|---|---|
| Chat with an AI model | ✅ |
| Conversation memory (AI remembers the current chat) | ✅ |
| **Long-term memory — it knows you across every chat** | ✅ |
| **Voice input (speak your message)** | ✅ |
| **Voice output (it reads replies aloud)** | ✅ |
| **Actions — opens apps/sites, manages files, runs git** | ✅ |
| **Password login** (needed if you expose Nova online) | ✅ |
| **File upload — ask questions about PDFs, Word, text, code** | ✅ |
| Multiple conversations + sidebar | ✅ |
| Auto-generated chat titles | ✅ |
| Delete conversations | ✅ |
| SQLite storage, created automatically | ✅ |
| Streaming replies (word by word, like ChatGPT) | ✅ |
| Markdown + syntax highlighting + copy buttons | ✅ |
| Dark / light theme, remembered in localStorage | ✅ |
| Mobile responsive with slide-out sidebar | ✅ |
| Friendly error handling, no key/traceback leaks | ✅ |
| Offline mock mode for testing without a key | ✅ |
| Swap AI model without code changes | ✅ |
| Ready to deploy (Docker, Render, Fly.io configs included) | ✅ |

---

## Screenshots

> The PNG files are not stored in git (binary files bloat a repo). Run
> `SETUP.bat` and see it live in 2 minutes — or grab them from the
> [release zip](https://github.com/SAMIUL-01/nova-assistant/releases).

- **Chat** — streaming replies, markdown, syntax highlighting, copy buttons
- **Memory panel** — every fact Nova knows about you, editable
- **Action cards** — green for done, amber with Confirm/Cancel for risky ones
- **Mobile** — slide-out sidebar, full width, install to home screen
- **Themes** — dark by default, light with one click

---

## The three big features

### 🦾 Actions — Nova can actually do things

Ask in plain language (or with your voice) and Nova performs it:

```
"open youtube"                      -> opens it in your browser
"make a folder called college"      -> creates it in your workspace
"write my todo list to notes.txt"   -> creates the file
"what's in my projects folder?"     -> lists it
"delete old.txt"                    -> asks you to confirm, then bins it
"commit and push my changes"        -> runs git, after confirmation
```

| Ability | Confirmation needed |
|---|---|
| Open a website (youtube, facebook, instagram, gmail, github, any URL) | no |
| Open an app (notepad, calculator, explorer, vscode, paint, …) | no |
| List / read / search files, create files and folders | no |
| Check the time, disk space, system info | no |
| **Delete** a file or folder | **yes** |
| **Move / rename** | **yes** |
| **git add / commit / push / pull** | **yes** |

#### The safety rules (please read)

Letting an AI touch your files is genuinely risky, so Nova is boxed in:

1. **One folder only.** Nova can only read or change things inside your
   workspace (`C:\Users\You\Nova` by default). Paths like `C:\Windows` or
   `../../secrets` are refused — on every operating system, not just Windows.
2. **Nothing is permanently deleted.** Deletes go to the Recycle Bin, or to a
   `.nova_trash` folder. You can always get files back.
3. **You approve destructive actions.** Nova stops and shows a Confirm /
   Cancel card. Nothing happens until you click.
4. **Everything is logged** to `data/actions.log`.
5. **There is no "run any command" tool.** Only the fixed list above. Nova
   cannot be talked into running arbitrary shell commands.

Turn actions off completely with `ACTIONS_ENABLED=false`.

> ⚠️ Actions run on **the machine Nova runs on**. On your PC, that is your PC.
> If you deploy Nova to a cloud server, set `ACTIONS_ENABLED=false` — otherwise
> "delete my files" would mean the server's files. To control your own PC from
> your phone, use a Cloudflare Tunnel instead (see `DEPLOY.md`).

---

### 🔒 Password login

Empty `AUTH_PASSWORD` = no login, which is fine on your own PC.

Set `AUTH_PASSWORD=something-strong` and Nova shows a login page. Sessions are
signed cookies that last 30 days.

**Set a password before making Nova reachable from the internet.** Without one,
anybody with the link can spend your API credits, read everything Nova
remembers about you, and run actions on your computer.

---

### 🧠 Long-term memory — it knows you

Tell it something once and it remembers in **every future chat**:

```
You:  My name is Sam and I'm a computer science student.
AI:   Nice to meet you, Sam!

... a brand new chat, days later ...

You:  What should I learn next?
AI:   Since you're studying computer science, Sam, ...
```

Facts are found two ways:

1. **Rules** — instant regex patterns like *"my name is …"*, *"I live in …"*,
   *"remember that …"*. Free, offline, never fails.
2. **AI** — after each reply the model is asked to pull out durable facts as
   JSON. Catches what the rules miss. Turn it off with
   `MEMORY_AI_EXTRACTION=false` to save requests.

Click **🧠 Memory** in the sidebar to see everything it knows, add a fact
yourself, delete one, or forget everything. Nothing is stored secretly, and
memory failures can never break a chat.

**Say this to teach it directly:** *"Remember that I prefer short answers."*

### 🎤 Voice — speak and listen

- **🎤 in the composer** — speak, and your words appear in the input box.
- **🔊 in the header** — toggle spoken replies on/off.
- **🔊 Read** under any reply — hear just that message.
- **Hands-free mode** — in the Memory panel, tick *"Send automatically when I
  stop speaking"*. Then it's speak → answer → speak, with no typing.

Voice uses your browser's built-in Web Speech API: no extra service, no cost,
nothing sent anywhere except the AI request itself.

> **Requires https or localhost.** Browsers block the microphone on plain
> `http://`, so voice input works on `127.0.0.1` but not over your Wi-Fi IP.
> Deploying (see `DEPLOY.md`) gives you https and fixes this on your phone.
> Voice input needs Chrome, Edge, or Safari — Firefox does not support it.

### 📎 File upload — chat with your documents

Click 📎 or drag a file onto the page. Supported: **PDF, DOCX, TXT, MD, CSV,
JSON**, and code files (`.py .js .java .html .css .sql .log`). Limit 10 MB.

How it works: the text is extracted, split into overlapping chunks, and the
chunks most relevant to your question are attached to that question. Retrieval
is a small TF-IDF scorer in pure Python — **no embeddings API, no extra cost**,
and it stays instant for personal-sized documents.

Files attach to the current conversation and show as chips above the input box.
Delete a chip to remove the file; deleting a chat removes its files too.

**Scanned PDFs won't work** — they contain pictures of text, which needs OCR.
**Images can't be read** by this text-only model; switch `AI_MODEL` to a vision
model such as `nvidia/nemotron-nano-12b-v2-vl:free` for that.

---

```
Frontend   HTML5 · CSS3 · Vanilla JavaScript
Backend    Python 3.11+ · FastAPI · Uvicorn
AI         OpenRouter → nvidia/nemotron-3.5-lightning:free
Database   SQLite (Python stdlib sqlite3 — no ORM)
Config     python-dotenv (.env)
```

---

## Requirements

- Python 3.11 or newer ([python.org](https://www.python.org/downloads/) — tick
  **"Add python.exe to PATH"** during install)
- A free OpenRouter API key: <https://openrouter.ai/keys>

Check Python is installed (Windows CMD):

```cmd
python --version
```

---

## Installation (Windows)

**The easy way:** double-click **`SETUP.bat`**, then **`START.bat`**. That's it.
`SETUP.bat` checks Python, builds the virtual environment, installs everything,
asks for your API key, and verifies the result. See `START-HERE.txt`.

**The manual way**, if you prefer typing commands:

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python check_setup.py
```

`check_setup.py` is the setup doctor — it checks 20+ things and prints an exact
fix for anything wrong. `DOCTOR.bat` runs the same check by double-click.

Open `.env` in Notepad and replace `YOUR_API_KEY_HERE` with your real
OpenRouter key. Save the file.

> On macOS/Linux use `python3 -m venv venv`, `source venv/bin/activate`,
> and `cp .env.example .env`. The `.bat` files are Windows-only.

---

## Run it

```cmd
venv\Scripts\activate
uvicorn app.main:app --reload
```

Expected output:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
2026-01-01 12:00:00 | INFO | app | Nova starting up
2026-01-01 12:00:00 | INFO | app | Model: nvidia/nemotron-3.5-lightning:free
```

Then open <http://127.0.0.1:8000> in your browser.

### Easier ways to start Nova

| Method | What happens |
|---|---|
| **Desktop icon** (run `INSTALL-SHORTCUT.bat` once) | Server starts hidden, Nova opens in its own app window. No black window. |
| `Nova.vbs` | Same as the desktop icon, launched from the folder. |
| `START.bat` | Classic way: shows the console with live logs. Good for debugging. |
| `STOP-NOVA.bat` | Stops Nova when it is running hidden. |

`INSTALL-SHORTCUT.bat` can also make Nova **start with Windows**, so it is
always ready in the background.

### Install it like a real app

Nova is a Progressive Web App. Open it in Chrome/Edge/Brave and click the
**install icon** in the address bar — you get a Start-menu entry, a taskbar
icon, and a window with no address bar. On a phone: menu → *Add to Home screen*.

Logs go to `nova.log` when Nova runs hidden.

---

## Try it without an API key

Set this in `.env` and restart:

```env
AI_OFFLINE_MOCK=1
```

The app replies with fake messages so you can test the entire interface —
streaming, markdown, code blocks, history, themes, mobile — with no key and no
internet. Set it back to `0` to talk to the real model.

---

## Open it on your phone (same Wi-Fi)

1. Find your PC's IP address:

   ```cmd
   ipconfig
   ```

   Look for **IPv4 Address**, e.g. `192.168.0.105`.

2. Start the server so it listens on the whole network:

   ```cmd
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

3. On your phone's browser, open:

   ```
   http://192.168.0.105:8000
   ```

If it does not load, allow Python through **Windows Defender Firewall**
(Private networks), and make sure both devices are on the same Wi-Fi.

---

## Configuration (`.env`)

| Variable | Default | What it does |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Your OpenRouter key. Required (unless mock mode). |
| `AI_MODEL` | `nvidia/nemotron-3.5-lightning:free` | Change this to swap models. |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Provider endpoint. |
| `AI_TEMPERATURE` | `0.7` | Higher = more creative. |
| `AI_MAX_TOKENS` | `2048` | Max length of a reply. |
| `AI_TIMEOUT_SECONDS` | `90` | Give up after this long. |
| `AI_OFFLINE_MOCK` | `0` | `1` = fake replies, no API calls. |
| `APP_NAME` | `Nova` | Shown in the browser tab and header. |
| `DEBUG` | `0` | `1` = verbose server logs. |
| `MAX_MESSAGE_CHARS` | `10000` | Longest message a user can send. |
| `HISTORY_LIMIT` | `20` | How many past messages are used as memory. |
| `ALLOWED_ORIGINS` | `*` | CORS. Use your real domain in production. |
| `RATE_LIMIT_PER_MINUTE` | `60` | Max chat/upload requests per minute per IP. `0` disables it. |
| `AUTH_PASSWORD` | (empty) | Password for the login page. Empty = no login. **Set it before exposing Nova online.** |
| `SESSION_HOURS` | `720` | How long a login lasts. |
| `ACTIONS_ENABLED` | `true` | Let Nova open apps/sites and manage files. Set `false` for cloud deploys. |
| `ACTIONS_CONFIRM` | `true` | Ask before deleting/moving/git push. Keep this on. |
| `NOVA_WORKSPACE` | `~/Nova` | The only folder Nova may touch. |
| `GIT_ROOT` | `~/Nova` | Folder git commands may run in. |
| `SYSTEM_PROMPT` | (built in) | Override the assistant's personality. |
| `DB_PATH` | `data/chat.db` | Where conversations are stored. |
| `MEMORY_ENABLED` | `true` | Long-term memory on/off. |
| `MEMORY_AI_EXTRACTION` | `true` | Also use the AI to spot facts (extra request per reply). |
| `MEMORY_MAX_FACTS` | `120` | Cap on stored facts. |
| `MAX_UPLOAD_MB` | `10` | Largest file you can attach. |
| `DOC_CONTEXT_CHARS` | `6000` | Characters of document excerpts sent per question. |
| `DOC_MAX_CHUNKS` | `6` | Most excerpts attached to one question. |
| `DOC_CHUNK_CHARS` | `1400` | Size of each document chunk. |
| `UPLOAD_DIR` | `data/uploads` | Where uploaded files are kept. |

**Switching models** needs no code change. Example:

```env
AI_MODEL=google/gemma-4-31b-it:free
```

---

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | The chat web page |
| GET | `/api/health` | Status, model, whether a key is configured |
| POST | `/api/login` · `/api/logout` | Session login (when a password is set) |
| GET | `/api/actions` | Everything Nova is allowed to do |
| POST | `/api/actions/confirm` · `/api/actions/cancel` | Approve or reject a risky action |
| GET | `/api/actions/log` | Recent action history |
| GET | `/api/conversations` | List chats for the sidebar |
| POST | `/api/conversations` | Create an empty chat |
| GET | `/api/conversations/{id}` | One chat with all its messages |
| DELETE | `/api/conversations/{id}` | Delete a chat and its messages |
| POST | `/api/chat` | Send a message, get the full reply |
| POST | `/api/chat/stream` | Send a message, stream the reply (SSE) |
| GET | `/api/memory` | Every fact the assistant knows about you |
| POST | `/api/memory` | Add a fact yourself |
| DELETE | `/api/memory/{id}` | Forget one fact |
| DELETE | `/api/memory` | Forget everything |
| GET | `/api/upload/info` | Allowed file types and size limit |
| POST | `/api/upload` | Upload a document (multipart form) |
| GET | `/api/conversations/{id}/documents` | Files attached to a chat |
| DELETE | `/api/documents/{id}` | Remove a file |

Interactive API docs are built in at <http://127.0.0.1:8000/docs>.

Example request:

```json
POST /api/chat
{ "conversation_id": 1, "message": "Explain Java Servlet" }
```

Example response:

```json
{ "conversation_id": 1, "message": "A Java Servlet is...", "title": "Java Servlet" }
```

Omit `conversation_id` and a new conversation is created and titled automatically.

---

## Project Structure

```text
nova/
├── app/
│   ├── main.py              FastAPI app, routers, error handlers, startup
│   ├── config.py            All settings, read from .env
│   ├── routes/
│   │   ├── chat.py          POST /api/chat and /api/chat/stream
│   │   ├── conversations.py Conversation CRUD
│   │   ├── memory.py        Long-term memory CRUD
│   │   └── uploads.py       File upload + document management
│   ├── services/
│   │   ├── ai_service.py    ALL AI/provider logic lives here
│   │   ├── memory.py        Fact extraction (rules + AI) and recall
│   │   ├── documents.py     Text extraction, chunking, TF-IDF retrieval
│   │   ├── rate_limit.py    Sliding-window request limiting
│   │   └── titles.py        Chat titles from plain text processing
│   ├── database/
│   │   └── db.py            All SQL. Tables created on startup.
│   └── models/
│       └── schemas.py       Request/response validation
├── static/
│   ├── css/style.css        Layout, themes (CSS variables), responsive
│   ├── js/app.js            All frontend logic. No API keys here.
│   ├── icons/               App icons (PWA + Windows .ico)
│   ├── manifest.webmanifest Makes Nova installable as an app
│   └── sw.js                Service worker (installability only, no caching)
├── templates/
│   └── index.html           Single page: sidebar, chat, composer, memory panel
├── data/
│   ├── chat.db              SQLite database (auto-created, git-ignored)
│   └── uploads/             Your uploaded files (git-ignored)
├── docs/screenshots/        Images used in this README
├── tests/
│   ├── test_api.py          Core API tests
│   ├── test_features.py     Memory + upload tests
│   └── test_rate_limit.py   Rate limiting + streaming regression tests
├── .env                     Your secrets (git-ignored — never commit)
├── .env.example             Template to copy
├── requirements.txt
├── START-HERE.txt           Read this first — 3 steps
├── SETUP.bat                One-click setup (run once)
├── INSTALL-SHORTCUT.bat     Desktop icon + optional start-with-Windows
├── Nova.vbs                 Silent launcher (hidden server, app window)
├── START.bat                Classic run with a visible console
├── STOP-NOVA.bat            Stop Nova when it runs hidden
├── DOCTOR.bat               One-click diagnostics when something breaks
├── check_setup.py           The setup doctor itself
├── Dockerfile               For Fly.io / Railway / VPS
├── render.yaml              Render blueprint
├── fly.toml                 Fly.io config (with persistent volume)
├── DEPLOY.md                Step-by-step deployment guide
└── README.md
```

### Database tables

```text
conversations ──< messages          your chats
memories                            facts about you, used in every chat
documents ──< doc_chunks            uploaded files, split for retrieval
```

### How a message flows

```
Browser (app.js)
   │  POST /api/chat/stream
   ▼
FastAPI route (routes/chat.py)
   │  save user message → load history from SQLite
   ▼
AIService (services/ai_service.py)   ← the API key lives only here, server-side
   │
   ▼
OpenRouter → NVIDIA Nemotron
   │  reply streams back token by token
   ▼
Saved to SQLite → rendered as markdown in the browser
```

---

## Testing

```cmd
venv\Scripts\activate
pytest -v
```

**48 tests** cover: health, homepage, conversation create/list/get/delete, chat,
conversation memory, streaming, empty messages, over-long messages, unknown
conversation IDs, title generation, memory rule extraction, AI-fact JSON
parsing, duplicate-fact rejection, memory CRUD, memory reuse in a new chat,
document chunking, retrieval ranking, TXT and PDF upload, and rejection of
images, unsupported types, empty files, oversized files, rate limiting, and a
regression test proving the limiter did not break streaming. They use mock mode,
so they never call OpenRouter and never need a key.

Manual checklist for the new features:

- [ ] Say "my name is X", then start a **new chat** and ask "what's my name?"
- [ ] Open 🧠 Memory — the fact is listed as *learned*
- [ ] Add a fact manually, then delete it
- [ ] Attach a PDF with 📎, then ask a question only that file can answer
- [ ] Toggle 🔊 and send a message — the reply is spoken
- [ ] Press 🎤 and dictate a message (needs https or localhost)

Manual checklist:

- [ ] Send a message, get a reply
- [ ] Reply streams in gradually
- [ ] Ask "my name is X", then "what is my name?" (memory)
- [ ] New Chat, switch between chats, delete a chat
- [ ] Copy button on a reply and on a code block
- [ ] Toggle dark/light, reload — theme persists
- [ ] Open on your phone, test the ☰ menu
- [ ] Send an empty message and a 10,000+ character message

---

## Troubleshooting

| Problem | Fix |
|---|---|
| **Anything at all** | **Double-click `DOCTOR.bat` — it names the exact problem and the fix.** |
| `'python' is not recognized` | Reinstall Python with "Add to PATH" ticked. |
| `'uvicorn' is not recognized` | Activate the venv: `venv\Scripts\activate` |
| `ModuleNotFoundError: No module named 'app'` | Run uvicorn from the project root folder, not from inside `app/`. |
| "The AI API key was rejected" | Check `OPENROUTER_API_KEY` in `.env`, then restart the server. |
| "No AI API key is configured" | You still have `YOUR_API_KEY_HERE` in `.env`. |
| "The model ... was not found" | Check `AI_MODEL` spelling against <https://openrouter.ai/models>. |
| "The AI is rate limited" | Free models have limits. Wait a minute, or switch `AI_MODEL`. |
| Sidebar/theme buttons do nothing | Hard-refresh with `Ctrl + F5` to clear cached JS. |
| Phone cannot connect | Use `--host 0.0.0.0`, same Wi-Fi, allow Python in the firewall. |
| Port 8000 already in use | Run with `--port 8001`. |
| Want to wipe all chats | Stop the server, delete `data/chat.db`, start again. |
| Mic button does nothing | Voice needs `https://` or `localhost`, and Chrome/Edge/Safari. |
| It forgot my name | Open 🧠 Memory to check the fact was stored. Try "remember that my name is X". |
| It remembered something wrong | Open 🧠 Memory and delete that fact. |
| PDF upload says "no text" | It's a scanned PDF (pictures of text). That needs OCR. |
| Answers ignore my file | Ask using words that appear in the document, or raise `DOC_CONTEXT_CHARS`. |
| Upload fails on a big file | Raise `MAX_UPLOAD_MB`, or split the file. |

Detailed technical errors always appear in the server console; the browser only
ever sees a safe, friendly message.

---

## Security Notes

- The API key lives in `.env`, is read only by the backend, and never reaches the
  browser. `app.js` contains no key.
- `.env` and `data/*.db` are in `.gitignore`. **Never commit them.**
- Input is validated: empty messages and messages over `MAX_MESSAGE_CHARS` are
  rejected with a 400.
- **Rate limiting**: `/api/chat` and `/api/upload` allow 60 requests per minute
  per IP by default, returning a friendly `429` with a `Retry-After` header
  beyond that. This protects your API credits from a runaway loop or abuse.
  Reading your own history is never rate limited. Tune with
  `RATE_LIMIT_PER_MINUTE`, or set it to `0` to disable.
- Exceptions are logged server-side; the API returns generic messages.
- Before deploying publicly, set `ALLOWED_ORIGINS` to your real domain and add
  authentication and rate limiting.

---

## Git

```cmd
git init
git add .
git commit -m "Initial AI chat web app"
```

Confirm your key is not staged (this should print nothing):

```cmd
git status --porcelain | findstr ".env"
```

---

## Deployment

**See [`DEPLOY.md`](DEPLOY.md) for the full step-by-step guide.** Short version:

| Host | Free? | Chats survive redeploys? |
|---|---|---|
| Render | Yes | ❌ needs a paid disk |
| Fly.io | Yes | ✅ free volume (`fly.toml` included) |
| Any Docker host | Varies | ✅ mount a volume at `/data` |

- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Set `OPENROUTER_API_KEY` in the platform's environment variables / secrets UI —
  never commit `.env`.
- Set `ALLOWED_ORIGINS` to your real domain.
- Deploying gives you `https://`, which is what makes **voice input work on your
  phone**.
- Keep it to **one worker** — SQLite does not like concurrent writers.
- ⚠️ The app has **no login**. Anyone with the URL can use your API key and read
  your memories. Keep the URL private, or add authentication first.

---

## Possible Next Steps

- A model selector in the UI (the backend already supports any OpenRouter model)
- Web search tool so the AI can answer current-events questions
- Login/accounts and PostgreSQL for multi-user use
- Editing/regenerating messages, and stopping a reply mid-stream
- OCR for scanned PDFs, and a vision model for images
- Export a chat to Markdown or PDF
