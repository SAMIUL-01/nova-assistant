"""
Setup doctor.

Checks everything the app needs and prints a plain-English report.
Run it any time something is not working:

    venv\\Scripts\\activate
    python check_setup.py

Exit code 0 = ready to run, 1 = something needs fixing.
"""

import os
import socket
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

OK = "[ OK ]"
BAD = "[FAIL]"
WARN = "[WARN]"

problems = []
warnings = []


def check(label, passed, detail="", fix="", warn_only=False):
    mark = OK if passed else (WARN if warn_only else BAD)
    print(f"{mark} {label}" + (f"  ->  {detail}" if detail else ""))
    if not passed:
        entry = (label, fix)
        (warnings if warn_only else problems).append(entry)
    return passed


print("=" * 68)
print("  SETUP DOCTOR - Personal AI Chat Web App")
print("=" * 68)
print()

# ---------------------------------------------------------------- 1. Python
print("--- Python ---")
version = sys.version_info
check(
    "Python 3.11 or newer",
    version >= (3, 11),
    f"you have {version.major}.{version.minor}.{version.micro}",
    "Install Python 3.11+ from python.org and tick 'Add python.exe to PATH'.",
)

in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
check(
    "Running inside the virtual environment",
    in_venv,
    sys.prefix,
    "Run:  venv\\Scripts\\activate      (you should see (venv) in your prompt)",
)

# ---------------------------------------------------------------- 2. Folder
print("\n--- Project folder ---")
expected = ["app/main.py", "static/js/app.js", "templates/index.html",
            "requirements.txt"]
missing = [p for p in expected if not (BASE_DIR / p).exists()]
if check(
    "All project files present",
    not missing,
    BASE_DIR.name if not missing else f"missing: {', '.join(missing)}",
    "Extract the zip again. Make sure there is no doubled folder like "
    "nova\\nova.",
):
    pass

nested = BASE_DIR / "nova" / "app" / "main.py"
if nested.exists():
    warnings.append((
        "Doubled folder detected",
        f"Your real project is inside {nested.parent.parent}. "
        "Work from that folder instead, or move its contents up one level.",
    ))
    print(f"{WARN} Doubled folder detected  ->  {nested.parent.parent}")

# ---------------------------------------------------------------- 3. Packages
print("\n--- Required packages ---")
packages = [
    ("fastapi", "fastapi", True),
    ("uvicorn", "uvicorn", True),
    ("openai", "openai", True),
    ("python-dotenv", "dotenv", True),
    ("jinja2", "jinja2", True),
    ("python-multipart", "multipart", False),
    ("pypdf", "pypdf", False),
    ("python-docx", "docx", False),
]
missing_pkgs = []
for pip_name, import_name, required in packages:
    try:
        __import__(import_name)
        found = True
    except Exception:
        found = False
    if not found:
        missing_pkgs.append(pip_name)
    label = f"{pip_name}" + ("" if required else "  (needed for file upload)")
    check(
        label,
        found,
        "installed" if found else "MISSING",
        "Run:  pip install -r requirements.txt",
        warn_only=not required,
    )

# ---------------------------------------------------------------- 4. .env
print("\n--- Configuration (.env) ---")
env_path = BASE_DIR / ".env"
has_env = env_path.exists()
check(
    ".env file exists",
    has_env,
    str(env_path) if has_env else "not found",
    "Run:  copy .env.example .env     then paste your key into it.",
)

key_ok = False
mock_on = False
if has_env:
    text = env_path.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("OPENROUTER_API_KEY="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            key_ok = bool(value) and not value.upper().startswith("YOUR_API_KEY")
        if line.startswith("AI_OFFLINE_MOCK="):
            mock_on = line.split("=", 1)[1].strip().lower() in ("1", "true", "yes", "on")

    check(
        "OPENROUTER_API_KEY is filled in",
        key_ok,
        "looks set" if key_ok else "still the placeholder, or empty",
        "Open .env in Notepad and replace YOUR_API_KEY_HERE with your real key "
        "from https://openrouter.ai/keys",
        warn_only=mock_on,
    )
    if mock_on:
        print(f"{WARN} AI_OFFLINE_MOCK=1  ->  replies are FAKE (good for testing)")
        print("       Set AI_OFFLINE_MOCK=0 in .env to talk to the real model.")

# ---------------------------------------------------------------- 5. Storage
print("\n--- Storage ---")
data_dir = BASE_DIR / "data"
try:
    data_dir.mkdir(exist_ok=True)
    probe = data_dir / ".write_test"
    probe.write_text("ok")
    probe.unlink()
    writable = True
except Exception as exc:  # noqa: BLE001
    writable = False
check(
    "data folder is writable",
    writable,
    str(data_dir),
    "Move the project out of a protected folder such as Program Files, "
    "or run CMD as Administrator.",
)

db = data_dir / "chat.db"
if db.exists():
    size_kb = db.stat().st_size / 1024
    print(f"{OK} existing database found  ->  {size_kb:.0f} KB (your old chats are safe)")
else:
    print(f"{OK} no database yet  ->  it will be created on first run")

icons_ok = (BASE_DIR / "static" / "icons" / "nova-192.png").exists()
if not icons_ok:
    print(f"{WARN} app icons missing  ->  run:  python tools\\make_icons.py")
    warnings.append(("App icons not generated",
                     "Run:  python tools\\make_icons.py   (cosmetic only)"))
else:
    print(f"{OK} app icons present")

# ---------------------------------------------------------------- 6. Port
print("\n--- Network ---")
port_free = True
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(1)
    if sock.connect_ex(("127.0.0.1", 8000)) == 0:
        port_free = False
check(
    "port 8000 is free",
    port_free,
    "free" if port_free else "already in use",
    "Close the other server window, or start with:  --port 8001",
    warn_only=True,
)

# ---------------------------------------------------------------- 7. App boot
print("\n--- Application ---")
boot_ok = False
boot_error = ""
try:
    sys.path.insert(0, str(BASE_DIR))
    os.environ.setdefault("AI_OFFLINE_MOCK", "1")
    from app.main import UPLOADS_AVAILABLE, app  # noqa: F401

    boot_ok = True
except Exception as exc:  # noqa: BLE001
    boot_error = f"{type(exc).__name__}: {exc}"

check(
    "the app imports without errors",
    boot_ok,
    "ready" if boot_ok else boot_error[:120],
    "Run:  pip install -r requirements.txt      then try again.",
)

if boot_ok:
    from app.main import UPLOADS_AVAILABLE

    print(f"{OK if UPLOADS_AVAILABLE else WARN} file upload feature  ->  "
          f"{'enabled' if UPLOADS_AVAILABLE else 'disabled (install python-multipart)'}")

# ---------------------------------------------------------------- Summary
print("\n" + "=" * 68)
if problems:
    print(f"  {len(problems)} PROBLEM(S) TO FIX:")
    print("=" * 68)
    for i, (label, fix) in enumerate(problems, 1):
        print(f"\n  {i}. {label}")
        print(f"     FIX: {fix}")
    if warnings:
        print("\n  Also worth noting:")
        for label, fix in warnings:
            print(f"   - {label}: {fix}")
    print()
    sys.exit(1)

print("  EVERYTHING IS READY")
print("=" * 68)
if warnings:
    print("\n  Notes (not blocking):")
    for label, fix in warnings:
        print(f"   - {label}: {fix}")
print("\n  Start the app with:  START.bat")
print("  Then open:           http://127.0.0.1:8000\n")
sys.exit(0)
