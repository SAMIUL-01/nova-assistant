"""
Nova's hands: the actions she can actually perform on this computer.

=========================  READ THIS BEFORE EDITING  =========================
An AI deciding to delete files is genuinely dangerous, so every rule below
exists on purpose:

1. SANDBOX   Nova may only touch paths inside NOVA_WORKSPACE. Anything else
             is refused, including tricks like "..\\..\\Windows".
2. TRASH     Deletes are never permanent. Files go to the Recycle Bin, or to
             a .nova_trash folder if that is unavailable.
3. CONFIRM   Destructive actions do not run until you press Confirm in the UI.
4. LOG       Every attempted action is written to data/actions.log.
5. NO SHELL  There is no "run any command" tool. Only this fixed list.

These actions run on the machine hosting Nova. On your own PC that is your
PC. If you deploy Nova to a cloud server, they would affect that server --
which is why ACTIONS_ENABLED should be false in a cloud deployment.
==============================================================================
"""

import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict

from app.config import settings

logger = logging.getLogger(__name__)


class ActionError(Exception):
    """A refused or failed action. The message is safe to show the user."""


# --------------------------------------------------------------------------
# Handy shortcuts so "open youtube" works without a full URL
# --------------------------------------------------------------------------
SITES = {
    "youtube": "https://www.youtube.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "whatsapp": "https://web.whatsapp.com",
    "gmail": "https://mail.google.com",
    "mail": "https://mail.google.com",
    "email": "https://mail.google.com",
    "github": "https://github.com",
    "google": "https://www.google.com",
    "drive": "https://drive.google.com",
    "chatgpt": "https://chat.openai.com",
    "openrouter": "https://openrouter.ai",
    "stackoverflow": "https://stackoverflow.com",
    "linkedin": "https://www.linkedin.com",
    "twitter": "https://twitter.com",
    "x": "https://twitter.com",
    "netflix": "https://www.netflix.com",
    "wikipedia": "https://www.wikipedia.org",
}

# Only these programs may be launched. No arbitrary executables.
APPS = {
    "notepad": {"win": "notepad.exe", "linux": "gedit", "mac": "TextEdit"},
    "calculator": {"win": "calc.exe", "linux": "gnome-calculator", "mac": "Calculator"},
    "explorer": {"win": "explorer.exe", "linux": "xdg-open", "mac": "Finder"},
    "files": {"win": "explorer.exe", "linux": "xdg-open", "mac": "Finder"},
    "paint": {"win": "mspaint.exe", "linux": "gimp", "mac": "Preview"},
    "vscode": {"win": "code", "linux": "code", "mac": "Visual Studio Code"},
    "code": {"win": "code", "linux": "code", "mac": "Visual Studio Code"},
    "settings": {"win": "ms-settings:", "linux": "gnome-control-center", "mac": "System Settings"},
    "task manager": {"win": "taskmgr.exe", "linux": "gnome-system-monitor", "mac": "Activity Monitor"},
}

# Git subcommands Nova may use, and whether they change anything.
GIT_ALLOWED = {"status", "log", "diff", "branch", "add", "commit", "push", "pull"}
GIT_DESTRUCTIVE = {"push", "commit", "add", "pull"}


# --------------------------------------------------------------------------
# Safety helpers
# --------------------------------------------------------------------------
def workspace() -> Path:
    """The one folder Nova is allowed to touch. Created on demand."""
    ws = settings.NOVA_WORKSPACE.expanduser()
    ws.mkdir(parents=True, exist_ok=True)
    return ws.resolve()


def safe_path(relative: str, must_exist: bool = False) -> Path:
    """
    Turn a user/AI supplied path into an absolute path inside the workspace.

    Refuses anything that escapes the workspace, absolute system paths, and
    symlinks pointing outside.

    The checks are deliberately platform independent: a Windows-style path
    like "..\\..\\Windows" must be refused even when Nova runs on Linux,
    otherwise the same prompt would behave differently on different machines.
    """
    ws = workspace()
    raw = (relative or "").strip().strip('"').strip("'")
    if not raw or raw in (".", "./"):
        return ws

    # Normalise separators so Windows paths are understood everywhere.
    normalised = raw.replace("\\", "/")

    # Reject drive letters (C:\...) and UNC shares (\\server\share).
    if re.match(r"^[A-Za-z]:", normalised) or normalised.startswith("//"):
        raise ActionError(
            f"For safety I can only work inside my workspace folder ({ws}). "
            f"'{raw}' is an absolute system path, so I did not touch it."
        )

    # Reject any attempt to climb out with "..".
    if any(part == ".." for part in normalised.split("/")):
        raise ActionError(
            f"For safety I can only work inside my workspace folder ({ws}). "
            f"'{raw}' tries to leave it, so I did not touch it."
        )

    candidate = Path(normalised)
    target = candidate if candidate.is_absolute() else ws / candidate

    try:
        resolved = target.resolve()
    except (OSError, RuntimeError) as exc:
        raise ActionError(f"That path is not usable: {raw}") from exc

    if resolved != ws and ws not in resolved.parents:
        raise ActionError(
            f"For safety I can only work inside my workspace folder ({ws}). "
            f"'{raw}' is outside it, so I did not touch it."
        )

    if must_exist and not resolved.exists():
        raise ActionError(f"'{raw}' does not exist in the workspace.")
    return resolved


def _rel(path: Path) -> str:
    """Show a short path relative to the workspace."""
    try:
        return str(path.relative_to(workspace())) or "."
    except ValueError:
        return str(path)


def audit(action: str, args: dict, outcome: str) -> None:
    """Append one line to the action log. Never raises."""
    try:
        settings.ACTION_LOG.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "action": action,
            "args": args,
            "outcome": outcome[:400],
        })
        with open(settings.ACTION_LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:  # noqa: BLE001
        logger.exception("Could not write the action log")


def _os_key() -> str:
    system = platform.system().lower()
    if system.startswith("win"):
        return "win"
    if system == "darwin":
        return "mac"
    return "linux"


# --------------------------------------------------------------------------
# The actions themselves
# --------------------------------------------------------------------------
def act_open_website(url: str = "", site: str = "") -> str:
    """Open a website in the default browser."""
    target = (site or url or "").strip()
    if not target:
        raise ActionError("Tell me which website to open.")

    key = target.lower().replace(" ", "").replace(".com", "")
    if key in SITES:
        final = SITES[key]
    else:
        # Check the scheme BEFORE adding https://, otherwise "file:///x"
        # would silently become "https://file:///x" and slip through.
        lowered_input = target.lower().lstrip()
        if lowered_input.startswith(("file:", "javascript:", "data:", "vbscript:",
                                     "about:", "chrome:")):
            raise ActionError("I can only open normal web addresses.")

        final = target
        if not final.startswith(("http://", "https://")):
            final = "https://" + final

    webbrowser.open(final)
    return f"Opened {final} in the browser."


def act_open_app(name: str) -> str:
    """Launch one of the allowed programs."""
    key = (name or "").strip().lower()
    if key not in APPS:
        allowed = ", ".join(sorted(APPS))
        raise ActionError(f"I can only open these apps: {allowed}.")

    command = APPS[key][_os_key()]
    try:
        if _os_key() == "win":
            os.startfile(command)  # noqa: S606  (fixed whitelist, not user input)
        elif _os_key() == "mac":
            subprocess.Popen(["open", "-a", command])
        else:
            subprocess.Popen([command], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    except FileNotFoundError as exc:
        raise ActionError(f"{name} does not seem to be installed.") from exc
    except Exception as exc:  # noqa: BLE001
        raise ActionError(f"Could not open {name}.") from exc
    return f"Opened {name}."


def act_list_files(path: str = ".") -> str:
    """List what is inside a workspace folder."""
    target = safe_path(path, must_exist=True)
    if not target.is_dir():
        raise ActionError(f"'{path}' is a file, not a folder.")

    entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    entries = [e for e in entries if e.name != ".nova_trash"]
    if not entries:
        return f"'{_rel(target)}' is empty."

    lines = []
    for e in entries[:100]:
        if e.is_dir():
            lines.append(f"[folder] {e.name}")
        else:
            lines.append(f"         {e.name}  ({e.stat().st_size:,} bytes)")
    more = "" if len(entries) <= 100 else f"\n...and {len(entries) - 100} more"
    return f"Contents of '{_rel(target)}':\n" + "\n".join(lines) + more


def act_create_folder(path: str) -> str:
    target = safe_path(path)
    if target.exists():
        return f"Folder '{_rel(target)}' already exists."
    target.mkdir(parents=True, exist_ok=True)
    return f"Created folder '{_rel(target)}'."


def act_create_file(path: str, content: str = "") -> str:
    target = safe_path(path)
    if target.is_dir():
        raise ActionError(f"'{path}' is a folder.")
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    target.write_text(content or "", encoding="utf-8")
    verb = "Updated" if existed else "Created"
    return f"{verb} file '{_rel(target)}' ({len(content or '')} characters)."


def act_read_file(path: str) -> str:
    target = safe_path(path, must_exist=True)
    if target.is_dir():
        raise ActionError(f"'{path}' is a folder, not a file.")
    if target.stat().st_size > 200_000:
        raise ActionError("That file is too big for me to read in one go.")
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        raise ActionError("I could not read that file.") from exc
    return f"Contents of '{_rel(target)}':\n\n{text[:8000]}"


def act_search_files(query: str, path: str = ".") -> str:
    root = safe_path(path, must_exist=True)
    needle = (query or "").strip().lower()
    if not needle:
        raise ActionError("Tell me what to search for.")
    hits = [
        _rel(p) for p in root.rglob("*")
        if needle in p.name.lower() and ".nova_trash" not in str(p)
    ][:60]
    if not hits:
        return f"Nothing matching '{query}' in '{_rel(root)}'."
    return f"Found {len(hits)} match(es) for '{query}':\n" + "\n".join(hits)


def act_delete(path: str) -> str:
    """Delete to the Recycle Bin (or to .nova_trash as a fallback)."""
    target = safe_path(path, must_exist=True)
    if target == workspace():
        raise ActionError("I will not delete the workspace folder itself.")

    # Preferred: the operating system's Recycle Bin, so you can restore it.
    try:
        from send2trash import send2trash  # optional dependency

        send2trash(str(target))
        return f"Moved '{_rel(target)}' to the Recycle Bin. You can restore it from there."
    except Exception:  # noqa: BLE001  (not installed, or no trash on this OS)
        pass

    trash = workspace() / ".nova_trash" / time.strftime("%Y%m%d-%H%M%S")
    trash.mkdir(parents=True, exist_ok=True)
    shutil.move(str(target), str(trash / target.name))
    return (f"Moved '{_rel(target)}' to '{_rel(trash)}'. "
            "Nothing was permanently deleted.")


def act_move(source: str, destination: str) -> str:
    src = safe_path(source, must_exist=True)
    dst = safe_path(destination)
    if dst.is_dir():
        dst = dst / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        raise ActionError(f"'{_rel(dst)}' already exists.")
    shutil.move(str(src), str(dst))
    return f"Moved '{_rel(src)}' to '{_rel(dst)}'."


def act_git(command: str, message: str = "", path: str = ".") -> str:
    """Run one allowed git subcommand inside the git root."""
    sub = (command or "").strip().lower()
    if sub not in GIT_ALLOWED:
        raise ActionError(f"I can only run these git commands: {', '.join(sorted(GIT_ALLOWED))}.")

    root = settings.GIT_ROOT.expanduser().resolve()
    repo = (root / path).resolve() if path not in ("", ".") else root
    if repo != root and root not in repo.parents:
        raise ActionError(f"I can only run git inside {root}.")
    if not (repo / ".git").exists():
        raise ActionError(f"'{repo}' is not a git repository.")

    if sub == "commit":
        if not message.strip():
            raise ActionError("A commit needs a message.")
        args = ["git", "commit", "-m", message.strip()]
    elif sub == "add":
        args = ["git", "add", "-A"]
    else:
        args = ["git", sub]

    try:
        result = subprocess.run(args, cwd=repo, capture_output=True, text=True,
                                timeout=120)
    except FileNotFoundError as exc:
        raise ActionError("Git is not installed on this computer.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ActionError("The git command took too long.") from exc

    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        return f"git {sub} failed:\n{output[:1200]}"
    return f"git {sub} done:\n{output[:1500] or '(no output)'}"


def act_system_info() -> str:
    ws = workspace()
    total, used, free = shutil.disk_usage(ws.anchor or "/")
    now = datetime.now().astimezone()
    return (
        f"Time: {now.strftime('%A %d %B %Y, %I:%M %p')}\n"
        f"System: {platform.system()} {platform.release()}\n"
        f"Computer: {platform.node()}\n"
        f"Python: {sys.version.split()[0]}\n"
        f"Disk: {free // 2**30} GB free of {total // 2**30} GB\n"
        f"Workspace: {ws}"
    )


def act_current_time() -> str:
    now = datetime.now().astimezone()
    return now.strftime("It is %I:%M %p on %A, %d %B %Y.")


# --------------------------------------------------------------------------
# Registry: name -> (function, destructive?, JSON schema for the model)
# --------------------------------------------------------------------------
REGISTRY: Dict[str, dict] = {
    "open_website": {
        "fn": act_open_website,
        "destructive": False,
        "description": "Open a website in the user's browser. Accepts a full URL "
                       "or a short name like youtube, facebook, instagram, gmail, github.",
        "params": {
            "site": {"type": "string", "description": "Short name or full URL."},
        },
        "required": ["site"],
    },
    "open_app": {
        "fn": act_open_app,
        "destructive": False,
        "description": "Open a program on the computer. Allowed: "
                       + ", ".join(sorted(APPS)),
        "params": {"name": {"type": "string", "description": "Program name."}},
        "required": ["name"],
    },
    "list_files": {
        "fn": act_list_files,
        "destructive": False,
        "description": "List files and folders inside the Nova workspace.",
        "params": {"path": {"type": "string",
                            "description": "Folder relative to the workspace. Use '.' for the top."}},
        "required": [],
    },
    "read_file": {
        "fn": act_read_file,
        "destructive": False,
        "description": "Read a text file from the Nova workspace.",
        "params": {"path": {"type": "string", "description": "File path in the workspace."}},
        "required": ["path"],
    },
    "search_files": {
        "fn": act_search_files,
        "destructive": False,
        "description": "Search the workspace for files whose name contains the query.",
        "params": {
            "query": {"type": "string", "description": "Text to look for in file names."},
            "path": {"type": "string", "description": "Folder to search in. Default '.'"},
        },
        "required": ["query"],
    },
    "create_folder": {
        "fn": act_create_folder,
        "destructive": False,
        "description": "Create a new folder inside the Nova workspace.",
        "params": {"path": {"type": "string", "description": "Folder path to create."}},
        "required": ["path"],
    },
    "create_file": {
        "fn": act_create_file,
        "destructive": False,
        "description": "Create or overwrite a text file inside the Nova workspace.",
        "params": {
            "path": {"type": "string", "description": "File path in the workspace."},
            "content": {"type": "string", "description": "Text to write into the file."},
        },
        "required": ["path"],
    },
    "delete_path": {
        "fn": act_delete,
        "destructive": True,
        "description": "Delete a file or folder from the workspace. It goes to the "
                       "Recycle Bin and can be restored. Requires user confirmation.",
        "params": {"path": {"type": "string", "description": "What to delete."}},
        "required": ["path"],
    },
    "move_path": {
        "fn": act_move,
        "destructive": True,
        "description": "Move or rename a file or folder inside the workspace.",
        "params": {
            "source": {"type": "string", "description": "Existing path."},
            "destination": {"type": "string", "description": "New path or folder."},
        },
        "required": ["source", "destination"],
    },
    "git": {
        "fn": act_git,
        "destructive": True,
        "description": "Run a git command in the git root folder. Allowed: "
                       + ", ".join(sorted(GIT_ALLOWED)),
        "params": {
            "command": {"type": "string", "description": "status, log, diff, branch, add, commit, push or pull."},
            "message": {"type": "string", "description": "Commit message, for commit only."},
            "path": {"type": "string", "description": "Repository folder. Default '.'"},
        },
        "required": ["command"],
    },
    "system_info": {
        "fn": act_system_info,
        "destructive": False,
        "description": "Report time, operating system, disk space and workspace location.",
        "params": {},
        "required": [],
    },
    "current_time": {
        "fn": act_current_time,
        "destructive": False,
        "description": "Get the current date and time.",
        "params": {},
        "required": [],
    },
}


def is_destructive(name: str) -> bool:
    spec = REGISTRY.get(name)
    if not spec:
        return True                       # unknown = treat as dangerous
    if name == "git":
        return True                       # decided per subcommand at call time
    return bool(spec["destructive"])


def git_is_destructive(arguments: dict) -> bool:
    return (arguments.get("command") or "").strip().lower() in GIT_DESTRUCTIVE


def needs_confirmation(name: str, arguments: dict) -> bool:
    if not settings.ACTIONS_CONFIRM:
        return False
    if name == "git":
        return git_is_destructive(arguments)
    return is_destructive(name)


def tool_schemas() -> list:
    """The tool list sent to the model, in OpenAI function-calling format."""
    tools = []
    for name, spec in REGISTRY.items():
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": spec["description"],
                "parameters": {
                    "type": "object",
                    "properties": spec["params"],
                    "required": spec["required"],
                },
            },
        })
    return tools


def describe(name: str, arguments: dict) -> str:
    """A short human sentence describing what is about to happen."""
    a = arguments or {}
    return {
        "open_website": f"Open {a.get('site', a.get('url', '?'))}",
        "open_app": f"Open the app '{a.get('name', '?')}'",
        "list_files": f"List files in '{a.get('path', '.')}'",
        "read_file": f"Read the file '{a.get('path', '?')}'",
        "search_files": f"Search for '{a.get('query', '?')}'",
        "create_folder": f"Create the folder '{a.get('path', '?')}'",
        "create_file": f"Create the file '{a.get('path', '?')}'",
        "delete_path": f"DELETE '{a.get('path', '?')}' (goes to the Recycle Bin)",
        "move_path": f"Move '{a.get('source', '?')}' to '{a.get('destination', '?')}'",
        "git": f"Run git {a.get('command', '?')}"
               + (f" -m \"{a.get('message')}\"" if a.get("message") else ""),
        "system_info": "Check this computer's details",
        "current_time": "Check the current time",
    }.get(name, f"Run {name}")


def execute(name: str, arguments: dict) -> str:
    """Run an action. Raises ActionError with a user-safe message on failure."""
    if not settings.ACTIONS_ENABLED:
        raise ActionError("Actions are switched off. Set ACTIONS_ENABLED=true in .env.")

    spec = REGISTRY.get(name)
    if not spec:
        raise ActionError(f"I do not have an action called '{name}'.")

    arguments = arguments or {}
    allowed = set(spec["params"].keys())
    cleaned = {k: v for k, v in arguments.items() if k in allowed}

    fn: Callable = spec["fn"]
    try:
        result = fn(**cleaned)
    except ActionError as exc:
        audit(name, cleaned, f"REFUSED: {exc}")
        raise
    except TypeError as exc:
        audit(name, cleaned, f"BAD ARGS: {exc}")
        raise ActionError(f"I could not run {name} with those details.") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Action %s failed", name)
        audit(name, cleaned, f"ERROR: {exc}")
        raise ActionError(f"Something went wrong while trying to {describe(name, cleaned).lower()}.") from exc

    audit(name, cleaned, f"OK: {result[:200]}")
    return result


def system_prompt_note() -> str:
    """Told to the model so it knows what it can do."""
    if not settings.ACTIONS_ENABLED:
        return ""
    return (
        "## Actions\n"
        "You can control this computer with the provided tools: opening websites "
        "and apps, managing files in your workspace, and running git.\n"
        f"Your workspace folder is: {settings.NOVA_WORKSPACE}\n"
        "Rules you must follow:\n"
        "- Only use a tool when the user actually asks you to do something.\n"
        "- You cannot touch files outside the workspace. Do not promise otherwise.\n"
        "- Deleting and moving files needs the user's confirmation; say so plainly.\n"
        "- After a tool runs, tell the user the result in one short sentence.\n"
        "- Never claim you did something that the tool did not report as done."
    )
