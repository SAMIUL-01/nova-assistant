# Security

Nova can act on the computer she runs on, so the safety rules are part of the
design rather than an afterthought.

## How a tool call is decided

Every tool call passes through `app/services/security.py`, which returns
**allow**, **confirm** or **deny**. Nothing bypasses it — not the model, not
the fast-path router, not the confirmation endpoint.

| Risk | Examples | Behaviour |
|---|---|---|
| `SAFE` | time, list files, read file | runs immediately |
| `MODERATE` | create file, open app, volume | runs immediately |
| `SENSITIVE` | screenshots, messaging | **always confirms** |
| `DESTRUCTIVE` | delete, move, git push | **always confirms** |

## Guarantees

1. `SENSITIVE` and `DESTRUCTIVE` always require confirmation. Settings can only
   make Nova stricter, never looser.
2. **No arbitrary command execution.** There is no shell tool. If the model
   asks for `run_shell` or `execute_command`, the gate denies it because the
   tool is not in the registry.
3. **Filesystem is sandboxed** to the Nova workspace. Absolute paths, drive
   letters, UNC shares and `..` traversal are refused on every OS.
4. **Deletes are recoverable** — files go to the Recycle Bin, or to a
   `.nova_trash` folder.
5. **Approval is not a master key.** A disabled capability stays disabled even
   if the user presses Confirm.
6. **Nova never sends a message on her own.** Messaging tools open a draft;
   the human presses Send.
7. **Secrets are scrubbed** from `data/actions.log` (API keys, tokens,
   passwords, email addresses).
8. Screen capture is `SENSITIVE` and its capability is **off by default**.

Each of these is covered by a test in `tests/test_security.py` and
`tests/test_jarvis_tools.py`.

## Deploying Nova online

- **Set `AUTH_PASSWORD`.** Without it, anyone with the URL can use your API key
  and act on your machine.
- **Set `ACTIONS_ENABLED=false` for cloud deployments.** On a server, "delete
  my files" would mean the server's files, not yours. To control your own PC
  from your phone, use a Cloudflare Tunnel so Nova keeps running locally.
- Keep `.env` out of git. It already is, via `.gitignore`.

## Reporting a problem

Open an issue. Please do not include your API key, session cookie, or the
contents of `data/actions.log` in a public report.
