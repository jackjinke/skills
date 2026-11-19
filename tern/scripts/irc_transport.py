"""Storage, channel state, and Tern/SSH doorbell transport for tern IRC."""

from __future__ import annotations

import datetime as dt
import fcntl
import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

DEFAULT_ROOT = os.environ.get("TERN_IRC_ROOT", "/tmp/tern-irc")
TERN_BIN = os.environ.get("TERN_IRC_TERN_BIN", "tern")
SSH_BIN = os.environ.get("TERN_IRC_SSH_BIN", "ssh")
REMOTE_TERN_BIN = os.environ.get("TERN_IRC_REMOTE_TERN_BIN", "tern")
INLINE_BODY_LIMIT = 1500
DEFAULT_TTL_MINS = 15
DEFAULT_WAIT_TIMEOUT = 1800
POLL_INTERVAL_SECS = 2.0

CHANNEL_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
HOST_RE = re.compile(r"^[A-Za-z0-9._@:-]{1,128}$")
SLUG_RE = re.compile(r"[^a-z0-9]+")

ACTIVE_STATES = ("available", "working", "busy-external")
VALID_KINDS = ("fyi", "request", "handoff", "blocked")
VALID_MODES = ("full", "pull-only")

# Dialog Guard: detect open interactive confirmation/permission/question prompts
# in `tern capture --surfaces` tail so a doorbell Enter never approves them.
DIALOG_PATTERNS = [
    re.compile(r"\[[yY]/[nN]\]"),
    re.compile(r"\[[nN]/[yY]\]"),
    re.compile(r"\(y/n\)|\(yes/no\)", re.IGNORECASE),
    re.compile(r"(?:enter|↵|return)\s+to\s+(?:confirm|select|submit|approve|accept)", re.IGNORECASE),
    re.compile(r"(?:esc|escape)\s+to\s+(?:cancel|reject|deny|dismiss)", re.IGNORECASE),
    re.compile(r"(?:allow|approve|permit)\s+(?:once|always|this|tool|command|edit|for\s+session)", re.IGNORECASE),
    re.compile(r"do\s+you\s+want\s+to\s+(?:proceed|continue|run|allow|apply|create|edit|execute)", re.IGNORECASE),
    re.compile(r"(?:permission\s+required|approve\s+plan|waiting\s+for\s+(?:approval|confirmation|input))", re.IGNORECASE),
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_channel(name: str) -> str:
    if not CHANNEL_RE.match(name) or name in (".", ".."):
        raise SystemExit(f"error: invalid channel name {name!r} (allowed: [A-Za-z0-9._-], 1-64 chars)")
    return name


def validate_host(host: str | None) -> str:
    h = (host or os.environ.get("TERN_IRC_HOST", "") or "local").strip()
    if h == "local":
        return "local"
    if not HOST_RE.match(h) or h.startswith("-"):
        raise SystemExit(f"error: invalid --host value {h!r}")
    return h


def channel_dir(root: str, channel: str) -> Path:
    return Path(root) / validate_channel(channel)


def resolve_block(explicit: str | None) -> str:
    block = (explicit or os.environ.get("TERN_PANE", "")).strip()
    if not block:
        raise SystemExit("error: block ID required (set TERN_PANE or pass --block ID)")
    return block


def member_key(host: str, block: str) -> str:
    return str(block) if host == "local" else f"{host}:{block}"


def safe_file_stem(host: str, block: str) -> str:
    sb = re.sub(r"[^A-Za-z0-9._-]", "_", str(block))
    if host == "local":
        return sb
    sh = re.sub(r"[^A-Za-z0-9._-]", "_", str(host))
    return f"{sh}__{sb}"


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def ensure_channel_dirs(cdir: Path) -> None:
    for sub in ("members", "artifacts", "doorbell"):
        (cdir / sub).mkdir(parents=True, exist_ok=True)


def require_channel(cdir: Path) -> None:
    if not (cdir / "members").is_dir():
        raise SystemExit(f"error: channel not initialized at {cdir} (run `init` first)")


def read_log(cdir: Path) -> list[dict[str, Any]]:
    log_path = cdir / "log.jsonl"
    if not log_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                entries.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return entries


def latest_seq(cdir: Path) -> int:
    entries = read_log(cdir)
    return int(entries[-1]["seq"]) if entries else 0


def append_log(cdir: Path, entry: dict[str, Any]) -> dict[str, Any]:
    ensure_channel_dirs(cdir)
    lock_path = cdir / ".log.lock"
    log_path = cdir / "log.jsonl"
    with lock_path.open("a+", encoding="utf-8") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        try:
            seq = 0
            if log_path.exists():
                with log_path.open("r", encoding="utf-8") as rfh:
                    for raw in rfh:
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            seq = max(seq, int(json.loads(raw).get("seq", 0)))
                        except (json.JSONDecodeError, ValueError, TypeError):
                            pass
            seq += 1
            record = {"seq": seq, "ts": utc_now(), **entry}
            with log_path.open("a", encoding="utf-8") as afh:
                afh.write(json.dumps(record, ensure_ascii=False) + "\n")
                afh.flush()
                os.fsync(afh.fileno())
            return record
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


def member_path(cdir: Path, host: str, block: str) -> Path:
    return cdir / "members" / f"{safe_file_stem(host, block)}.json"


def load_members(cdir: Path) -> list[dict[str, Any]]:
    mdir = cdir / "members"
    if not mdir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(mdir.glob("*.json")):
        data = read_json(path)
        if isinstance(data, dict) and "block" in data:
            data.setdefault("host", "local")
            out.append(data)
    return out


def load_member(cdir: Path, host: str, block: str) -> dict[str, Any] | None:
    data = read_json(member_path(cdir, host, block))
    if isinstance(data, dict):
        data.setdefault("host", host)
        return data
    return None


def save_member(cdir: Path, member: dict[str, Any]) -> None:
    member.setdefault("host", "local")
    member["updated_at"] = time.time()
    atomic_write_json(member_path(cdir, str(member["host"]), str(member["block"])), member)


def find_member(cdir: Path, target: str) -> dict[str, Any] | None:
    key = target.lstrip("@").strip()
    members = load_members(cdir)
    for pred in (
        lambda m: member_key(str(m["host"]), str(m["block"])) == key,
        lambda m: m.get("host") == "local" and str(m.get("block")) == key,
        lambda m: str(m.get("block")) == key,
        lambda m: m.get("nick") == key and m.get("state") in ACTIVE_STATES,
        lambda m: m.get("nick") == key,
    ):
        for m in members:
            if pred(m):
                return m
    return None


def norm_pattern(pat: str) -> str:
    p = pat.strip().lstrip("./")
    while "//" in p:
        p = p.replace("//", "/")
    return p.rstrip("/") if p != "/" else p


def globs_overlap(a: str, b: str) -> bool:
    pa, pb = norm_pattern(a), norm_pattern(b)
    if not pa or not pb:
        return False
    if pa == pb:
        return True

    def base_prefix(p: str) -> str:
        for suffix in ("/**", "/*"):
            if p.endswith(suffix):
                return p[: -len(suffix)]
        return p

    ba, bb = base_prefix(pa), base_prefix(pb)
    if ba == bb:
        return True
    if pa.endswith(("/**", "/*")) and (bb == ba or bb.startswith(ba + "/")):
        return True
    if pb.endswith(("/**", "/*")) and (ba == bb or ba.startswith(bb + "/")):
        return True
    if fnmatch.fnmatch(pa, pb) or fnmatch.fnmatch(pb, pa):
        return True
    if ("*" not in pa and "?" not in pa) and pb.startswith(pa + "/"):
        return True
    if ("*" not in pb and "?" not in pb) and pa.startswith(pb + "/"):
        return True
    return False


def tern_run_cmd(args: list[str], host: str = "local", timeout: float = 8.0) -> subprocess.CompletedProcess[str] | None:
    if host == "local":
        cmd = [TERN_BIN, *args]
    else:
        remote_cmd = f'export PATH="$HOME/.local/bin:$PATH"; {REMOTE_TERN_BIN} {shlex.join(args)}'
        cmd = [SSH_BIN, "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, remote_cmd]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def inspect_all_panes(host: str = "local") -> dict[str, dict[str, Any]] | None:
    res = tern_run_cmd(["inspect", "--json"], host=host)
    if res is None or res.returncode != 0:
        return None
    try:
        payload = json.loads(res.stdout)
    except json.JSONDecodeError:
        return None
    panes = payload.get("panes")
    if not isinstance(panes, list):
        return None
    return {str(p.get("pane")): p for p in panes if "pane" in p}


def inspect_block(block: str, host: str = "local") -> dict[str, Any]:
    panes = inspect_all_panes(host=host)
    if panes is None:
        return {"available": False, "found": False}
    pane = panes.get(str(block))
    if pane is None:
        return {"available": True, "found": False}
    return {
        "available": True,
        "found": True,
        "working": bool(pane.get("working", False)),
        "quiet_ms": int(pane.get("quiet_ms", 0) or 0),
        "exited": pane.get("exited"),
        "title": str(pane.get("title") or ""),
    }


def check_dialog_guard(block: str, host: str = "local") -> tuple[bool, str | None]:
    res = tern_run_cmd(["capture", str(block), "--surfaces", "--json"], host=host)
    if res is None or res.returncode != 0:
        return True, None
    text = res.stdout
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "text" in parsed:
            text = str(parsed["text"] or "")
    except json.JSONDecodeError:
        pass
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()][-20:]
    for line in reversed(lines):
        for pat in DIALOG_PATTERNS:
            if pat.search(line):
                return False, line[:160]
    return True, None


def send_tern_doorbell(block: str, text: str, host: str = "local") -> bool:
    r1 = tern_run_cmd(["send", str(block), "paste", text], host=host)
    if r1 is None or r1.returncode != 0:
        return False
    r2 = tern_run_cmd(["send", str(block), "keys", "enter"], host=host)
    return r2 is not None and r2.returncode == 0


def doorbell_path(cdir: Path, host: str, block: str, suffix: str) -> Path:
    return cdir / "doorbell" / f"{safe_file_stem(host, block)}.{suffix}"


def clear_doorbell_markers(cdir: Path, host: str, block: str) -> None:
    for suffix in ("rung", "dialog"):
        try:
            doorbell_path(cdir, host, block, suffix).unlink()
        except FileNotFoundError:
            pass


def is_waiter_running(cdir: Path, host: str, block: str) -> bool:
    lpath = doorbell_path(cdir, host, block, "wait.lock")
    if not lpath.exists():
        return False
    try:
        with lpath.open("a+", encoding="utf-8") as fh:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            return False
    except OSError:
        return False


def spawn_deferred_waiter(
    cli_script: Path,
    root: str,
    channel: str,
    target_host: str,
    target_block: str,
    sender_nick: str,
    sender_key: str,
    timeout: int,
) -> bool:
    cdir = channel_dir(root, channel)
    lpath = doorbell_path(cdir, target_host, target_block, "wait.lock")
    lpath.parent.mkdir(parents=True, exist_ok=True)
    lock_fh = lpath.open("a+", encoding="utf-8")
    try:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_fh.close()
        return False
    # Pass held flock fd to child so the lock never drops across spawn.
    lock_fd = lock_fh.fileno()
    os.set_inheritable(lock_fd, True)
    cmd = [
        sys.executable,
        str(cli_script.resolve()),
        "_wait-ring",
        channel,
        str(target_block),
        "--root",
        root,
        "--target-host",
        target_host,
        "--sender-nick",
        sender_nick,
        "--sender-key",
        sender_key,
        "--timeout",
        str(timeout),
        "--lock-fd",
        str(lock_fd),
    ]
    try:
        subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            pass_fds=(lock_fd,),
            start_new_session=True,
        )
    finally:
        lock_fh.close()
    return True


def build_doorbell_message(
    cli_script: Path,
    channel: str,
    root: str,
    sender_nick: str,
    sender_key: str,
    target_host: str,
    last_seq: int,
    cur_seq: int,
    urgent: bool,
    hint: str = "",
) -> str:
    root_arg = f" --root {root}" if root != DEFAULT_ROOT else ""
    host_arg = f" --host {target_host}" if target_host != "local" else ""
    unread = max(1, cur_seq - last_seq)
    tag = "IRC URGENT" if urgent else "IRC"
    extra = f" — {hint}" if hint else ""
    return (
        f"[{tag} #{channel} from {sender_nick}@{sender_key}] "
        f"{unread} unread (seq {last_seq + 1}..{cur_seq}){extra}. "
        f"Run: python3 {cli_script.resolve()} inbox {channel}{root_arg}{host_arg}"
    )


def maybe_log_dialog_alert(cdir: Path, target: dict[str, Any], cur_seq: int, detail: str | None) -> None:
    thost, tblock = str(target["host"]), str(target["block"])
    dpath = doorbell_path(cdir, thost, tblock, "dialog")
    prev = read_json(dpath)
    if isinstance(prev, dict) and int(prev.get("seq", -1)) >= cur_seq:
        return
    atomic_write_json(dpath, {"seq": cur_seq, "ts": time.time(), "detail": detail or ""})
    append_log(
        cdir,
        {
            "type": "dialog_alert",
            "from": "irc-guard",
            "from_block": "system",
            "to": ["@all"],
            "summary": (
                f"Block {member_key(thost, tblock)} (@{target['nick']}) appears to be on a "
                f"confirmation/permission dialog; doorbell withheld ({detail or 'prompt detected'})."
            ),
        },
    )


def ring_target(
    cli_script: Path,
    root: str,
    channel: str,
    target: dict[str, Any],
    sender_nick: str,
    sender_key: str,
    *,
    urgent: bool = False,
    defer: bool = True,
    timeout: int = DEFAULT_WAIT_TIMEOUT,
    hint: str = "",
    allow_no_unread: bool = False,
) -> dict[str, Any]:
    cdir = channel_dir(root, channel)
    thost, tblock = str(target.get("host", "local")), str(target["block"])
    tnick = str(target.get("nick", member_key(thost, tblock)))

    if (cdir / "PAUSE").exists():
        return {"target": tnick, "host": thost, "block": tblock, "status": "paused"}
    if target.get("state") not in ACTIVE_STATES:
        return {"target": tnick, "host": thost, "block": tblock, "status": "not_in_channel"}
    if target.get("mode") == "pull-only":
        return {"target": tnick, "host": thost, "block": tblock, "status": "pull_only"}

    cur_seq = latest_seq(cdir)
    last_seq = int(target.get("last_seq", 0))
    if cur_seq <= last_seq and not allow_no_unread:
        return {"target": tnick, "host": thost, "block": tblock, "status": "no_unread"}

    rung = read_json(doorbell_path(cdir, thost, tblock, "rung"))
    if not urgent and isinstance(rung, dict) and int(rung.get("seq", 0)) >= cur_seq and not allow_no_unread:
        return {"target": tnick, "host": thost, "block": tblock, "status": "already_rung", "rung_seq": rung.get("seq")}

    info = inspect_block(tblock, host=thost)
    if not info.get("available"):
        return {"target": tnick, "host": thost, "block": tblock, "status": "tern_unavailable"}
    if not info.get("found") or info.get("exited") is not None:
        return {"target": tnick, "host": thost, "block": tblock, "status": "exited"}

    min_quiet = 5000 if target.get("state") == "busy-external" else 3000
    is_working = bool(info.get("working", False))
    quiet_ms = int(info.get("quiet_ms", 0))
    if (is_working or quiet_ms < min_quiet) and not urgent:
        if defer:
            spawned = spawn_deferred_waiter(cli_script, root, channel, thost, tblock, sender_nick, sender_key, timeout)
            return {
                "target": tnick,
                "host": thost,
                "block": tblock,
                "status": "deferred" if spawned else "already_deferred",
                "working": is_working,
                "quiet_ms": quiet_ms,
            }
        return {"target": tnick, "host": thost, "block": tblock, "status": "busy", "working": is_working, "quiet_ms": quiet_ms}

    safe, matched = check_dialog_guard(tblock, host=thost)
    if not safe:
        maybe_log_dialog_alert(cdir, target, cur_seq, matched)
        if defer:
            spawn_deferred_waiter(cli_script, root, channel, thost, tblock, sender_nick, sender_key, timeout)
        return {"target": tnick, "host": thost, "block": tblock, "status": "dialog_blocked", "detail": matched}

    # Revalidate after inspect/capture I/O so a peer that drained mid-check is not rung.
    if (cdir / "PAUSE").exists():
        return {"target": tnick, "host": thost, "block": tblock, "status": "paused"}
    fresh = load_member(cdir, thost, tblock)
    if fresh is None or fresh.get("state") not in ACTIVE_STATES:
        return {"target": tnick, "host": thost, "block": tblock, "status": "not_in_channel"}
    cur_seq = latest_seq(cdir)
    last_seq = int(fresh.get("last_seq", 0))
    if cur_seq <= last_seq and not allow_no_unread:
        return {"target": tnick, "host": thost, "block": tblock, "status": "no_unread"}

    msg = build_doorbell_message(cli_script, channel, root, sender_nick, sender_key, thost, last_seq, cur_seq, urgent, hint)
    if not send_tern_doorbell(tblock, msg, host=thost):
        return {"target": tnick, "host": thost, "block": tblock, "status": "send_failed"}

    atomic_write_json(doorbell_path(cdir, thost, tblock, "rung"), {"seq": cur_seq, "ts": time.time(), "urgent": urgent})
    return {
        "target": tnick,
        "host": thost,
        "block": tblock,
        "status": "rung_urgent" if urgent else "rung",
        "seq": cur_seq,
        "unread": max(0, cur_seq - last_seq),
    }
