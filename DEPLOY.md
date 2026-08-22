# Deployment Guide

Get your assistant online with an `https://` address you can open from any
phone, on any network.

**Why https matters:** browsers only allow microphone access on a secure
connection. Voice input works on `localhost`, but over your Wi-Fi IP
(`http://192.168.x.x`) the mic is blocked. Deploying fixes that.

---

## Step 1 — Put the code on GitHub

Make sure your key is not going with it:

```cmd
git init
git add .
git status
```

Look at the file list. **`.env` must NOT appear.** If it does, stop and check
that `.gitignore` exists in the project root.

```cmd
git commit -m "Personal AI chat app with memory, voice, and file upload"
```

Create an empty repository on <https://github.com/new> (do **not** add a README),
then:

```cmd
git remote add origin https://github.com/YOUR-USERNAME/nova.git
git branch -M main
git push -u origin main
```

---

## Step 2 — Pick a host

| Host | Free? | Chats survive restarts? | Effort |
|---|---|---|---|
| **Cloudflare Tunnel** | Yes | ✅ (runs on your PC) | Easy — one command |
| **Render** | Yes | ❌ No (needs a paid disk) | Easiest — all clicking |
| **Fly.io** | Yes | ✅ Yes (free volume) | A few CLI commands |
| **Railway** | Trial credit | ✅ Yes | Easy |
| **Your own VPS** | No | ✅ Yes | Most work |

**Which should you pick?**

- Want Nova to **control your PC** (open apps, manage files)? → **Cloudflare
  Tunnel.** It is the only option where Nova still runs on your own machine.
- Just want to **chat from anywhere**, PC switched off? → **Fly.io**
  (and set `ACTIONS_ENABLED=false`).
- Want it live in 5 minutes and don't mind losing history? → **Render.**

⚠️ For every option: **set `AUTH_PASSWORD` first.**

---

## Option A — Cloudflare Tunnel (best if you want JARVIS actions)

This gives your **own PC** a public `https://` address. Nova keeps running on
your computer, so it can still open your apps and manage your files — but you
can reach it from your phone, anywhere, and the microphone works because it is
proper https.

**Set a password first. This is not optional.** In `.env`:

```env
AUTH_PASSWORD=pick-something-long-and-random
```

Restart Nova, then:

1. Download `cloudflared` from
   <https://github.com/cloudflare/cloudflared/releases> (the
   `cloudflared-windows-amd64.exe` file) and rename it to `cloudflared.exe`.
2. Start Nova as usual.
3. In a new Command Prompt:

```cmd
cloudflared.exe tunnel --url http://127.0.0.1:8000
```

It prints a URL like `https://random-words-1234.trycloudflare.com`. Open that
on your phone, log in with your password, and you have Nova — with voice and
with control over your PC.

Notes:
- The free quick tunnel URL changes each time you restart it. For a permanent
  address, log in with `cloudflared tunnel login` and create a named tunnel.
- Nova must stay running on your PC. Close it and the link stops working.
- Anyone with the URL **and** your password can act on your computer, so use a
  strong password and do not share the link publicly.

---

## Option B — Render (easiest, chat only)

1. Sign up at <https://render.com> with your GitHub account.
2. **New +** → **Web Service** → pick your `nova` repo.
3. Fill in:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** Free
4. Open **Advanced** → **Add Environment Variable**, and add:

   | Key | Value |
   |---|---|
   | `OPENROUTER_API_KEY` | your real key |
   | `AI_MODEL` | `nvidia/nemotron-3.5-lightning:free` |
   | `PYTHON_VERSION` | `3.12.6` |

5. **Create Web Service**, then watch the log until you see
   `Uvicorn running on http://0.0.0.0:10000`.
6. Open your URL: `https://your-app-name.onrender.com`

> Your repo already contains `render.yaml`, so you can instead use
> **New +** → **Blueprint** and Render will read all the settings from it.

### Two things to know about Render's free plan

- **It sleeps.** After ~15 minutes of no traffic the service stops, and the
  next visit takes 30–60 seconds to wake up. Normal, not a bug.
- **Data is not permanent.** The filesystem resets on every deploy and on wake,
  so `chat.db` (your chats *and* your memories) starts empty again.
  To fix it: upgrade to a paid instance, add a **Disk** mounted at `/var/data`,
  and set `DB_PATH=/var/data/chat.db` plus `UPLOAD_DIR=/var/data/uploads`.
  The commented `KEEP-DATA` lines in `render.yaml` do exactly this.

---

## Option C — Fly.io (free, and your chats persist)

Install the CLI, then in your project folder:

```cmd
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
fly auth signup
fly launch --no-deploy
```

When asked, **keep the existing `fly.toml`**. Then create the storage volume
and set your key:

```cmd
fly volumes create chat_data --size 1 --region sin
fly secrets set OPENROUTER_API_KEY=sk-or-your-real-key
fly deploy
fly open
```

The volume mounted at `/data` keeps your database and uploads across every
deploy. Change `app = "nova"` in `fly.toml` if that name is taken.

---

## Option D — Any Docker host (Railway, Cloud Run, VPS)

Your `Dockerfile` is ready:

```cmd
docker build -t ai-chat .
docker run -p 8000:8000 -e OPENROUTER_API_KEY=sk-or-... -v chatdata:/data ai-chat
```

The `-v chatdata:/data` part is what keeps your chats. On Railway, add the same
environment variables and attach a volume at `/data`.

---

## Step 3 — Lock it down

Once you know your real URL, set this environment variable and redeploy:

```
ALLOWED_ORIGINS=https://your-app-name.onrender.com
```

**Important:** your app has no login. Anyone with the URL can chat using your
API key and read your memories. Options:

- Keep the URL private (fine for personal use, and the default).
- Add HTTP Basic Auth — about 15 lines of FastAPI middleware.
- Add full accounts + PostgreSQL (bigger job; see README "Possible Next Steps").

Do not post your URL publicly while it is unauthenticated.

---

## Step 4 — Test it from your phone

Open your `https://` URL on your phone and check:

- [ ] A message gets a reply
- [ ] The reply streams in gradually
- [ ] 🎤 asks for microphone permission and types what you say
- [ ] 🔊 reads a reply out loud
- [ ] 📎 uploads a PDF, and asking about it gives an answer from the file
- [ ] 🧠 shows the facts it learned about you
- [ ] Open a **new chat** and ask "what's my name?" — it should know
- [ ] The ☰ menu opens the chat list

**Add it to your home screen** for an app-like feel: in Chrome, tap ⋮ →
*Add to Home screen*. It then opens fullscreen with no browser bar.

---

## Troubleshooting

| Problem | Cause and fix |
|---|---|
| Build fails on `pip install` | Set `PYTHON_VERSION` to `3.12.6`. Very old Python breaks FastAPI. |
| Deploy succeeds, page is blank | Check the start command uses `--port $PORT`. Hosts assign the port. |
| "No AI API key is configured" | The env var was not saved, or you redeployed before saving it. |
| Replies appear all at once, not streaming | A proxy is buffering. On Fly, keep `pristine = true`. On Render this works by default. |
| Mic button does nothing | You are on `http://`, not `https://`. Also check the site's mic permission. |
| Voice reads nothing on iPhone | iOS blocks speech until you tap something first. Tap 🔊 once, then send. |
| All my chats vanished | Free Render has no persistent disk. Add a disk, or move to Fly.io. |
| First visit takes 50 seconds | Free tier cold start. Expected. |
| 502 after ~90 seconds | Model was slow. Lower `AI_MAX_TOKENS`, or pick a faster model. |

Read the host's live logs (Render: **Logs** tab; Fly: `fly logs`) — the friendly
message shown in the browser always has a detailed version there.

---

## Updating your app later

```cmd
git add .
git commit -m "describe your change"
git push
```

Render and Fly redeploy automatically on push. On Render's free plan, remember
this also wipes the database.
