#!/usr/bin/env python3
"""CLI for lightweight IRC-style coordination across headed Tern blocks."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import time
from pathlib import Path
from typing import Any

from irc_transport import (
    ACTIVE_STATES,
    DEFAULT_ROOT,
    DEFAULT_TTL_MINS,
    DEFAULT_WAIT_TIMEOUT,
    INLINE_BODY_LIMIT,
    POLL_INTERVAL_SECS,
    SLUG_RE,
    VALID_KINDS,
    VALID_MODES,
    append_log,
    atomic_write_json,
    atomic_write_text,
    build_doorbell_message,
    channel_dir,
    check_dialog_guard,
    clear_doorbell_markers,
    doorbell_path,
    ensure_channel_dirs,
    find_member,
    globs_overlap,
    inspect_all_panes,
    inspect_block,
    is_waiter_running,
    latest_seq,
    load_member,
    load_members,
    maybe_log_dialog_alert,
    member_key,
    norm_pattern,
    read_json,
    read_log,
    require_channel,
    resolve_block,
    ring_target,
    save_member,
    send_tern_doorbell,
    tern_run_cmd,
    utc_now,
    validate_host,
)

CLI_SCRIPT = Path(__file__).resolve()


def emit(data: Any, as_json: bool, text: str) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2) if as_json else text)


def cmd_init(args: argparse.Namespace) -> int:
    cdir = channel_dir(args.root, args.channel)
    ensure_channel_dirs(cdir)
    topic = Path(args.topic_file).read_text(encoding="utf-8") if args.topic_file else (args.topic or "")
    if topic or not (cdir / "topic.md").exists():
        atomic_write_text(cdir / "topic.md", (topic.rstrip() + "\n") if topic else f"# Channel #{args.channel}\n")
    host = validate_host(args.host)
    block = (args.block or os.environ.get("TERN_PANE", "")).strip() or "host"
    rec = append_log(
        cdir,
        {
            "type": "init",
            "from": args.nick or block,
            "from_host": host,
            "from_block": block,
            "summary": (topic.splitlines()[0] if topic else f"Initialized #{args.channel}")[:160],
        },
    )
    emit(
        {"channel": args.channel, "dir": str(cdir), "seq": rec["seq"]},
        args.json,
        f"Initialized #{args.channel} at {cdir} (seq {rec['seq']})",
    )
    return 0


def cmd_join(args: argparse.Namespace) -> int:
    cdir = channel_dir(args.root, args.channel)
    ensure_channel_dirs(cdir)
    if not (cdir / "topic.md").exists():
        atomic_write_text(cdir / "topic.md", f"# Channel #{args.channel}\n")

    host = validate_host(args.host)
    block = resolve_block(args.block)
    mkey = member_key(host, block)
    nick = args.nick.lstrip("@").strip()
    if not nick:
        raise SystemExit("error: --nick cannot be empty")

    for existing in load_members(cdir):
        ekey = member_key(str(existing["host"]), str(existing["block"]))
        if existing.get("nick") == nick and ekey != mkey and existing.get("state") in ACTIVE_STATES:
            raise SystemExit(f"error: nick @{nick} is already in use by active block {ekey}")

    prev = load_member(cdir, host, block)
    cur_seq = latest_seq(cdir)
    member = {
        "nick": nick,
        "host": host,
        "block": block,
        "role": args.role,
        "mode": args.mode,
        "state": args.state,
        "note": args.note or "",
        "claims": prev.get("claims", []) if isinstance(prev, dict) and prev.get("state") in ACTIVE_STATES else [],
        "last_seq": int(prev.get("last_seq", cur_seq)) if isinstance(prev, dict) else cur_seq,
        "joined_at": float(prev.get("joined_at", time.time())) if isinstance(prev, dict) else time.time(),
        "updated_at": time.time(),
    }
    save_member(cdir, member)
    rec = append_log(
        cdir,
        {
            "type": "join",
            "from": nick,
            "from_host": host,
            "from_block": block,
            "role": args.role,
            "mode": args.mode,
            "state": args.state,
            "summary": f"@{nick} ({mkey}, {args.role}/{args.mode}) joined [{args.state}]",
        },
    )
    if prev is None:
        member["last_seq"] = rec["seq"]
        save_member(cdir, member)

    emit(
        {"member": member, "seq": rec["seq"]},
        args.json,
        f"Joined #{args.channel} as @{nick} ({mkey}, state={args.state}, seq={rec['seq']})",
    )
    return 0


def cmd_state(args: argparse.Namespace) -> int:
    cdir = channel_dir(args.root, args.channel)
    require_channel(cdir)
    host = validate_host(args.host)
    block = resolve_block(args.block)
    member = load_member(cdir, host, block)
    if member is None:
        raise SystemExit(f"error: {member_key(host, block)} has not joined #{args.channel}")
    member["state"] = args.state
    if args.note is not None:
        member["note"] = args.note
    now = time.time()
    for claim in member.get("claims", []):
        if float(claim.get("expires_at", 0)) > now:
            claim["expires_at"] = now + float(claim.get("ttl_mins", DEFAULT_TTL_MINS)) * 60.0
    save_member(cdir, member)
    emit({"member": member}, args.json, f"@{member['nick']} ({member_key(host, block)}) state -> {args.state}")
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    cdir = channel_dir(args.root, args.channel)
    require_channel(cdir)
    host = validate_host(args.host)
    block = resolve_block(args.block)
    mkey = member_key(host, block)
    member = load_member(cdir, host, block)
    if member is None or member.get("state") not in ACTIVE_STATES:
        raise SystemExit(f"error: {mkey} must join #{args.channel} before claiming")

    now = time.time()
    req_files = [norm_pattern(f) for f in (args.files or []) if norm_pattern(f)]
    panes_by_host: dict[str, dict[str, dict[str, Any]] | None] = {}
    conflicts: list[dict[str, Any]] = []

    for other in load_members(cdir):
        ohost, oblock = str(other["host"]), str(other["block"])
        if member_key(ohost, oblock) == mkey or other.get("state") not in ACTIVE_STATES:
            continue
        if ohost not in panes_by_host:
            panes_by_host[ohost] = inspect_all_panes(host=ohost)
        panes = panes_by_host[ohost]
        if panes is not None:
            opane = panes.get(oblock)
            if opane is None or opane.get("exited") is not None:
                continue
        for c in other.get("claims", []):
            if float(c.get("expires_at", 0)) <= now:
                continue
            reason = f"task {args.task!r} already claimed" if c.get("task") == args.task else None
            if not reason:
                for rf in req_files:
                    match = next((of for of in c.get("files", []) if globs_overlap(rf, of)), None)
                    if match:
                        reason = f"file overlap {rf!r} vs {match!r}"
                        break
            if reason:
                conflicts.append(
                    {
                        "owner": other.get("nick"),
                        "host": ohost,
                        "block": oblock,
                        "task": c.get("task"),
                        "files": c.get("files", []),
                        "ttl_left_s": int(float(c.get("expires_at", 0)) - now),
                        "reason": reason,
                    }
                )

    if conflicts and not args.force:
        emit(
            {"ok": False, "conflicts": conflicts},
            args.json,
            "CLAIM CONFLICT:\n"
            + "\n".join(
                f"  - {c['reason']} by @{c['owner']} ({member_key(c['host'], c['block'])}, ttl {c['ttl_left_s']}s left)"
                for c in conflicts
            )
            + "\nCoordinate or kick/cancel owner before reclaiming (or pass --force after explicit handoff).",
        )
        return 2

    ttl_mins = max(1, int(args.ttl))
    claims = [c for c in member.get("claims", []) if c.get("task") != args.task and float(c.get("expires_at", 0)) > now]
    new_claim = {
        "task": args.task,
        "files": req_files,
        "ttl_mins": ttl_mins,
        "claimed_at": now,
        "expires_at": now + ttl_mins * 60.0,
    }
    claims.append(new_claim)
    member["claims"] = claims
    if member.get("state") == "available":
        member["state"] = "working"
    save_member(cdir, member)

    rec = append_log(
        cdir,
        {
            "type": "claim",
            "from": member["nick"],
            "from_host": host,
            "from_block": block,
            "task": args.task,
            "files": req_files,
            "ttl_mins": ttl_mins,
            "summary": f"@{member['nick']} claimed {args.task}"
            + (f" ({', '.join(req_files)})" if req_files else "")
            + f" [ttl {ttl_mins}m]",
        },
    )
    emit(
        {"ok": True, "claim": new_claim, "seq": rec["seq"]},
        args.json,
        f"Claimed {args.task} for @{member['nick']} (ttl {ttl_mins}m, seq {rec['seq']})",
    )
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    cdir = channel_dir(args.root, args.channel)
    require_channel(cdir)
    host = validate_host(args.host)
    block = resolve_block(args.block)
    member = load_member(cdir, host, block)
    if member is None:
        raise SystemExit(f"error: {member_key(host, block)} has not joined #{args.channel}")

    before = member.get("claims", [])
    if args.all or not args.tasks:
        released = [c.get("task") for c in before]
        member["claims"] = []
    else:
        wanted = set(args.tasks)
        released = [c.get("task") for c in before if c.get("task") in wanted]
        member["claims"] = [c for c in before if c.get("task") not in wanted]
    if not member["claims"] and member.get("state") == "working":
        member["state"] = "available"
    save_member(cdir, member)

    rec = append_log(
        cdir,
        {
            "type": "release",
            "from": member["nick"],
            "from_host": host,
            "from_block": block,
            "tasks": released,
            "summary": f"@{member['nick']} released {', '.join(released) if released else 'none'}",
        },
    )
    emit(
        {"released": released, "seq": rec["seq"]},
        args.json,
        f"Released {', '.join(released) if released else 'nothing'} (seq {rec['seq']})",
    )
    return 0


def cmd_say(args: argparse.Namespace) -> int:
    cdir = channel_dir(args.root, args.channel)
    require_channel(cdir)
    host = validate_host(args.host)
    block = resolve_block(args.block)
    mkey = member_key(host, block)
    member = load_member(cdir, host, block)
    sender_nick = member["nick"] if isinstance(member, dict) else mkey

    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else (args.body or "")
    summary = (args.summary or "").strip()
    if not summary:
        first_line = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
        summary = first_line[:140] if first_line else f"{args.kind} message"

    targets = [t.strip() for t in (args.to or ["@all"]) if t.strip()]
    spilled_body = body if (body and (len(body.encode("utf-8")) > INLINE_BODY_LIMIT or args.body_file)) else None
    if spilled_body is not None:
        body = ""

    entry: dict[str, Any] = {
        "type": "msg",
        "kind": args.kind,
        "from": sender_nick,
        "from_host": host,
        "from_block": block,
        "to": targets,
        "urgent": bool(args.urgent),
        "summary": summary,
    }
    if body:
        entry["body"] = body
    if args.artifact:
        entry["artifact"] = str(Path(args.artifact).resolve()) if Path(args.artifact).exists() else args.artifact
    elif spilled_body is not None:
        slug = SLUG_RE.sub("-", summary.lower()).strip("-")[:32] or args.kind
        art = cdir / "artifacts" / f"{latest_seq(cdir) + 1:04d}-{slug}-{int(time.time()) % 10000:04d}.md"
        atomic_write_text(art, spilled_body.rstrip() + "\n")
        entry["artifact"] = str(art)

    rec = append_log(cdir, entry)
    if isinstance(member, dict):
        if int(member.get("last_seq", 0)) == rec["seq"] - 1:
            member["last_seq"] = rec["seq"]
        save_member(cdir, member)

    ring_results: list[dict[str, Any]] = []
    if args.ring or args.urgent:
        resolved: list[dict[str, Any]] = []
        seen: set[str] = set()
        for tok in targets:
            candidates = load_members(cdir) if tok in ("@all", "all", "*") else ([m] if (m := find_member(cdir, tok)) else [])
            for m in candidates:
                k = member_key(str(m["host"]), str(m["block"]))
                if k != mkey and m.get("state") in ACTIVE_STATES and k not in seen:
                    seen.add(k)
                    resolved.append(m)
        for tm in resolved:
            ring_results.append(
                ring_target(
                    CLI_SCRIPT,
                    args.root,
                    args.channel,
                    tm,
                    sender_nick,
                    mkey,
                    urgent=bool(args.urgent),
                    defer=not args.no_defer,
                    timeout=args.timeout,
                    hint=summary[:60] if args.urgent else "",
                )
            )

    lines = [f"[seq {rec['seq']}] #{args.channel} ({args.kind}) @{sender_nick} -> {', '.join(targets)}: {summary}"]
    if entry.get("artifact"):
        lines.append(f"  artifact: {entry['artifact']}")
    for rr in ring_results:
        lines.append(f"  ring @{rr['target']} ({member_key(rr['host'], rr['block'])}): {rr['status']}")
    emit({"record": rec, "rings": ring_results}, args.json, "\n".join(lines))
    return 0


def cmd_inbox(args: argparse.Namespace) -> int:
    cdir = channel_dir(args.root, args.channel)
    require_channel(cdir)
    host = validate_host(args.host)
    block = resolve_block(args.block)
    mkey = member_key(host, block)
    member = load_member(cdir, host, block)
    if member is None:
        raise SystemExit(f"error: {mkey} has not joined #{args.channel}")

    last_seq = int(member.get("last_seq", 0))
    entries = read_log(cdir)
    max_seq = int(entries[-1]["seq"]) if entries else last_seq
    nick = str(member.get("nick", ""))

    unread: list[dict[str, Any]] = []
    for e in entries:
        if int(e.get("seq", 0)) <= last_seq:
            continue
        efrom_key = member_key(str(e.get("from_host", "local")), str(e.get("from_block", "")))
        if not args.all and efrom_key == mkey:
            continue
        to_list = e.get("to") or []
        unread.append({**e, "direct": any(t.lstrip("@") in (nick, block, mkey) for t in to_list)})

    if not args.peek:
        member["last_seq"] = max_seq
        save_member(cdir, member)
        clear_doorbell_markers(cdir, host, block)

    if args.quiet and not unread:
        return 0
    if not unread:
        emit({"unread": [], "last_seq": max_seq}, args.json, f"No unread messages in #{args.channel} (seq {max_seq}).")
        return 0

    lines = [f"Unread in #{args.channel} ({len(unread)} entries, seq {last_seq + 1}..{max_seq}):"]
    for e in unread:
        prefix = "*" if e.get("direct") else " "
        kind = e.get("kind") or e.get("type")
        urg = " [URGENT]" if e.get("urgent") else ""
        to_str = f" -> {','.join(e['to'])}" if e.get("to") else ""
        lines.append(f"{prefix} #{e['seq']} [{kind}{urg}] @{e.get('from')}{to_str}: {e.get('summary', '')}")
        if e.get("body"):
            lines.extend(f"    {bl}" for bl in str(e["body"]).splitlines())
        if e.get("artifact"):
            lines.append(f"    artifact: {e['artifact']}")
    emit({"unread": unread, "last_seq": max_seq}, args.json, "\n".join(lines))
    return 0


def cmd_ring(args: argparse.Namespace) -> int:
    cdir = channel_dir(args.root, args.channel)
    require_channel(cdir)
    host = validate_host(args.host)
    sender_block = (args.block or os.environ.get("TERN_PANE", "")).strip() or "host"
    skey = member_key(host, sender_block)
    sender = load_member(cdir, host, sender_block)
    sender_nick = sender["nick"] if isinstance(sender, dict) else skey

    target = find_member(cdir, args.target)
    if target is None:
        raise SystemExit(f"error: member {args.target!r} not found in #{args.channel}")

    res = ring_target(
        CLI_SCRIPT,
        args.root,
        args.channel,
        target,
        sender_nick,
        skey,
        urgent=bool(args.urgent),
        defer=not args.no_defer,
        timeout=args.timeout,
        hint=args.hint or "",
        allow_no_unread=bool(args.force),
    )
    emit(res, args.json, f"ring @{res['target']} ({member_key(res['host'], res['block'])}): {res['status']}")
    return 0


def cmd_wait_ring(args: argparse.Namespace) -> int:
    """Internal 0-token background waiter: rings target once when idle & clean."""
    cdir = channel_dir(args.root, args.channel)
    thost = validate_host(args.target_host)
    if not (cdir / "members").is_dir():
        return 0
    if args.lock_fd is not None:
        lock_fh = os.fdopen(args.lock_fd, "a+", encoding="utf-8")
    else:
        lpath = doorbell_path(cdir, thost, args.target_block, "wait.lock")
        lpath.parent.mkdir(parents=True, exist_ok=True)
        lock_fh = lpath.open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_fh.close()
            return 0
    with lock_fh:
        try:
            lock_fh.seek(0)
            lock_fh.truncate()
            lock_fh.write(f"{os.getpid()}\n")
            lock_fh.flush()
            deadline = time.time() + max(5, int(args.timeout))
            while time.time() < deadline:
                if (cdir / "PAUSE").exists():
                    return 0
                target = load_member(cdir, thost, args.target_block)
                if target is None or target.get("state") not in ACTIVE_STATES or target.get("mode") == "pull-only":
                    return 0
                cur_seq = latest_seq(cdir)
                if cur_seq <= int(target.get("last_seq", 0)):
                    return 0
                rung = read_json(doorbell_path(cdir, thost, args.target_block, "rung"))
                if isinstance(rung, dict) and int(rung.get("seq", 0)) >= cur_seq:
                    return 0

                info = inspect_block(args.target_block, host=thost)
                if not info.get("available") or not info.get("found") or info.get("exited") is not None:
                    return 0

                min_quiet = 5000 if target.get("state") == "busy-external" else 3000
                if not info.get("working") and int(info.get("quiet_ms", 0)) >= min_quiet:
                    safe, matched = check_dialog_guard(args.target_block, host=thost)
                    if not safe:
                        maybe_log_dialog_alert(cdir, target, cur_seq, matched)
                    else:
                        # Revalidate after inspect/capture I/O to prevent TOCTOU double-ring.
                        if (cdir / "PAUSE").exists():
                            return 0
                        fresh = load_member(cdir, thost, args.target_block)
                        if fresh is None or fresh.get("state") not in ACTIVE_STATES:
                            return 0
                        cur_seq = latest_seq(cdir)
                        last_seq = int(fresh.get("last_seq", 0))
                        if cur_seq <= last_seq:
                            return 0
                        msg = build_doorbell_message(
                            CLI_SCRIPT,
                            args.channel,
                            args.root,
                            args.sender_nick,
                            args.sender_key,
                            thost,
                            last_seq,
                            cur_seq,
                            urgent=False,
                        )
                        if send_tern_doorbell(args.target_block, msg, host=thost):
                            atomic_write_json(
                                doorbell_path(cdir, thost, args.target_block, "rung"),
                                {"seq": cur_seq, "ts": time.time(), "urgent": False},
                            )
                        return 0
                time.sleep(POLL_INTERVAL_SECS)
            return 0
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


def cmd_part(args: argparse.Namespace) -> int:
    """Leave channel cleanly: release claims & clear doorbells, NEVER close block."""
    cdir = channel_dir(args.root, args.channel)
    require_channel(cdir)
    host = validate_host(args.host)
    block = resolve_block(args.block)
    mkey = member_key(host, block)
    member = load_member(cdir, host, block)
    if member is None:
        raise SystemExit(f"error: {mkey} is not a member of #{args.channel}")

    released = [c.get("task") for c in member.get("claims", [])]
    member["claims"] = []
    member["state"] = "parted"
    member["parted_at"] = time.time()
    save_member(cdir, member)
    clear_doorbell_markers(cdir, host, block)

    entry: dict[str, Any] = {
        "type": "part",
        "from": member["nick"],
        "from_host": host,
        "from_block": block,
        "released": released,
        "summary": args.summary or f"@{member['nick']} parted ({mkey} stays open)",
    }
    if args.artifact:
        entry["artifact"] = str(Path(args.artifact).resolve()) if Path(args.artifact).exists() else args.artifact
    rec = append_log(cdir, entry)
    emit(
        {"member": member, "released": released, "seq": rec["seq"]},
        args.json,
        f"Parted #{args.channel} as @{member['nick']} (released: {', '.join(released) or 'none'}; {mkey} left open; seq {rec['seq']})",
    )
    return 0


def cmd_kick(args: argparse.Namespace) -> int:
    cdir = channel_dir(args.root, args.channel)
    require_channel(cdir)
    actor_host = validate_host(args.host)
    actor_block = (args.block or os.environ.get("TERN_PANE", "")).strip() or "host"
    actor = load_member(cdir, actor_host, actor_block)
    actor_nick = actor["nick"] if isinstance(actor, dict) else member_key(actor_host, actor_block)

    target = find_member(cdir, args.target)
    if target is None:
        raise SystemExit(f"error: member {args.target!r} not found in #{args.channel}")
    thost, tblock = str(target["host"]), str(target["block"])
    tkey = member_key(thost, tblock)

    interrupted = False
    if args.interrupt:
        res = tern_run_cmd(["send", tblock, "keys", "ctrl+c"], host=thost)
        interrupted = res is not None and res.returncode == 0

    released = [c.get("task") for c in target.get("claims", [])]
    target["claims"] = []
    target["state"] = "quit"
    target["quit_at"] = time.time()
    save_member(cdir, target)
    clear_doorbell_markers(cdir, thost, tblock)

    rec = append_log(
        cdir,
        {
            "type": "kick",
            "from": actor_nick,
            "from_host": actor_host,
            "from_block": actor_block,
            "target": target["nick"],
            "target_host": thost,
            "target_block": tblock,
            "released": released,
            "interrupted": interrupted,
            "summary": f"@{actor_nick} marked @{target['nick']} ({tkey}) quit"
            + (f": {args.reason}" if args.reason else ""),
        },
    )
    emit(
        {"target": target, "released": released, "interrupted": interrupted, "seq": rec["seq"]},
        args.json,
        f"Marked @{target['nick']} ({tkey}) quit; released {', '.join(released) or 'none'} (ctrl+c={interrupted}, seq={rec['seq']})",
    )
    return 0


def cmd_pause(args: argparse.Namespace) -> int:
    cdir = channel_dir(args.root, args.channel)
    require_channel(cdir)
    host = validate_host(args.host)
    block = (args.block or os.environ.get("TERN_PANE", "")).strip() or "host"
    member = load_member(cdir, host, block)
    nick = member["nick"] if isinstance(member, dict) else member_key(host, block)
    atomic_write_json(cdir / "PAUSE", {"by": nick, "host": host, "block": block, "ts": utc_now(), "reason": args.reason or ""})
    rec = append_log(
        cdir,
        {"type": "pause", "from": nick, "from_host": host, "from_block": block, "summary": f"PAUSE enabled by @{nick}" + (f": {args.reason}" if args.reason else "")},
    )
    emit({"paused": True, "seq": rec["seq"]}, args.json, f"Paused doorbells for #{args.channel} (seq {rec['seq']})")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    cdir = channel_dir(args.root, args.channel)
    require_channel(cdir)
    host = validate_host(args.host)
    block = (args.block or os.environ.get("TERN_PANE", "")).strip() or "host"
    member = load_member(cdir, host, block)
    nick = member["nick"] if isinstance(member, dict) else member_key(host, block)
    try:
        (cdir / "PAUSE").unlink()
    except FileNotFoundError:
        pass
    rec = append_log(
        cdir,
        {"type": "resume", "from": nick, "from_host": host, "from_block": block, "summary": f"PAUSE cleared by @{nick}"},
    )
    emit({"paused": False, "seq": rec["seq"]}, args.json, f"Resumed doorbells for #{args.channel} (seq {rec['seq']})")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cdir = channel_dir(args.root, args.channel)
    require_channel(cdir)
    now = time.time()
    cur_seq = latest_seq(cdir)
    paused = read_json(cdir / "PAUSE")
    topic = (cdir / "topic.md").read_text(encoding="utf-8").strip() if (cdir / "topic.md").exists() else ""
    members = load_members(cdir)
    panes_by_host: dict[str, dict[str, dict[str, Any]] | None] = (
        {} if args.no_live else {h: inspect_all_panes(host=h) for h in sorted({str(m["host"]) for m in members})}
    )

    rows: list[dict[str, Any]] = []
    for m in members:
        h, b = str(m["host"]), str(m["block"])
        live = None
        if not args.no_live and panes_by_host.get(h) is not None:
            p = panes_by_host[h].get(b)
            live = (
                {"found": False}
                if p is None
                else {
                    "found": True,
                    "working": bool(p.get("working", False)),
                    "quiet_ms": int(p.get("quiet_ms", 0) or 0),
                    "exited": p.get("exited"),
                }
            )
        claims_view = [
            {**c, "expired": (float(c.get("expires_at", 0)) - now) <= 0, "ttl_left_s": int(float(c.get("expires_at", 0)) - now)}
            for c in m.get("claims", [])
        ]
        rows.append(
            {
                "nick": m.get("nick"),
                "host": h,
                "block": b,
                "role": m.get("role"),
                "mode": m.get("mode"),
                "state": m.get("state"),
                "unread": max(0, cur_seq - int(m.get("last_seq", 0))),
                "last_seq": int(m.get("last_seq", 0)),
                "claims": claims_view,
                "waiter": is_waiter_running(cdir, h, b),
                "rung": read_json(doorbell_path(cdir, h, b, "rung")),
                "dialog_blocked": read_json(doorbell_path(cdir, h, b, "dialog")),
                "live": live,
            }
        )

    lines = [
        f"Channel #{args.channel} ({cdir}) | seq={cur_seq} | paused={'YES' if paused else 'no'}",
        f"Topic: {topic.splitlines()[0] if topic else '(none)'}",
        "Members:",
    ]
    for r in rows:
        live_str = ""
        if r["live"] is not None:
            if not r["live"]["found"]:
                live_str = " live=MISSING"
            elif r["live"]["exited"] is not None:
                live_str = f" live=EXITED({r['live']['exited']})"
            else:
                live_str = f" working={r['live']['working']} quiet={r['live']['quiet_ms']}ms"
        claim_str = ""
        if r["claims"]:
            parts = [
                f"{c['task']}{':' + ','.join(c['files']) if c.get('files') else ''}({'EXPIRED' if c['expired'] else str(c['ttl_left_s']) + 's'})"
                for c in r["claims"]
            ]
            claim_str = " claims=[" + "; ".join(parts) + "]"
        flags = [f for f, cond in (("waiter", r["waiter"]), ("DIALOG_BLOCKED", r["dialog_blocked"])) if cond]
        flag_str = f" ({', '.join(flags)})" if flags else ""
        lines.append(
            f"  - @{r['nick']} {member_key(r['host'], r['block'])} [{r['state']}/{r['mode']}] unread={r['unread']}{live_str}{claim_str}{flag_str}"
        )

    emit({"channel": args.channel, "dir": str(cdir), "seq": cur_seq, "paused": paused, "topic": topic, "members": rows}, args.json, "\n".join(lines))
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=DEFAULT_ROOT, help=f"IRC root dir (default: {DEFAULT_ROOT})")
    common.add_argument("--host", default=None, help="Host target ('local' or SSH user@host)")
    common.add_argument("--block", default=None, help="Block ID (defaults to $TERN_PANE)")
    common.add_argument("--json", action="store_true", help="Output JSON")

    parser = argparse.ArgumentParser(prog="irc.py", description="Lightweight IRC channel coordinator for headed Tern blocks.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", parents=[common], help="Create a channel and topic.md")
    p_init.add_argument("channel")
    p_init.add_argument("--topic", default="")
    p_init.add_argument("--topic-file", default=None)
    p_init.add_argument("--nick", default=None)
    p_init.set_defaults(func=cmd_init)

    p_join = sub.add_parser("join", parents=[common], help="Join a channel")
    p_join.add_argument("channel")
    p_join.add_argument("--nick", required=True)
    p_join.add_argument("--role", default="peer")
    p_join.add_argument("--mode", choices=VALID_MODES, default="full")
    p_join.add_argument("--state", choices=ACTIVE_STATES, default="available")
    p_join.add_argument("--note", default="")
    p_join.set_defaults(func=cmd_join)

    p_state = sub.add_parser("state", parents=[common], help="Update presence state and renew claim TTLs")
    p_state.add_argument("channel")
    p_state.add_argument("state", choices=ACTIVE_STATES)
    p_state.add_argument("--note", default=None)
    p_state.set_defaults(func=cmd_state)

    p_claim = sub.add_parser("claim", parents=[common], help="Claim a task and optional file globs with TTL")
    p_claim.add_argument("channel")
    p_claim.add_argument("task")
    p_claim.add_argument("--files", nargs="*", default=[])
    p_claim.add_argument("--ttl", type=int, default=DEFAULT_TTL_MINS)
    p_claim.add_argument("--force", action="store_true")
    p_claim.set_defaults(func=cmd_claim)

    p_rel = sub.add_parser("release", parents=[common], help="Release one or all claims")
    p_rel.add_argument("channel")
    p_rel.add_argument("tasks", nargs="*")
    p_rel.add_argument("--all", action="store_true")
    p_rel.set_defaults(func=cmd_release)

    p_say = sub.add_parser("say", parents=[common], help="Post a message to the channel log")
    p_say.add_argument("channel")
    p_say.add_argument("--kind", choices=VALID_KINDS, default="fyi")
    p_say.add_argument("--to", nargs="+", default=["@all"])
    p_say.add_argument("--summary", default="")
    p_say.add_argument("--body", default="")
    p_say.add_argument("--body-file", default=None)
    p_say.add_argument("--artifact", default=None)
    p_say.add_argument("--ring", action="store_true")
    p_say.add_argument("--urgent", action="store_true")
    p_say.add_argument("--no-defer", action="store_true")
    p_say.add_argument("--timeout", type=int, default=DEFAULT_WAIT_TIMEOUT)
    p_say.set_defaults(func=cmd_say)

    p_inbox = sub.add_parser("inbox", parents=[common], help="Read unread messages and clear doorbell")
    p_inbox.add_argument("channel")
    p_inbox.add_argument("--peek", action="store_true")
    p_inbox.add_argument("--all", action="store_true")
    p_inbox.add_argument("--quiet", action="store_true")
    p_inbox.set_defaults(func=cmd_inbox)

    p_ring = sub.add_parser("ring", parents=[common], help="Ring a single target member safely")
    p_ring.add_argument("channel")
    p_ring.add_argument("target")
    p_ring.add_argument("--urgent", action="store_true")
    p_ring.add_argument("--no-defer", action="store_true")
    p_ring.add_argument("--force", action="store_true")
    p_ring.add_argument("--hint", default="")
    p_ring.add_argument("--timeout", type=int, default=DEFAULT_WAIT_TIMEOUT)
    p_ring.set_defaults(func=cmd_ring)

    p_part = sub.add_parser("part", parents=[common], help="Leave channel cleanly (never closes Tern block)")
    p_part.add_argument("channel")
    p_part.add_argument("--summary", default="")
    p_part.add_argument("--artifact", default=None)
    p_part.set_defaults(func=cmd_part)

    p_kick = sub.add_parser("kick", parents=[common], help="Mark a dead/cancelled member quit and release its claims")
    p_kick.add_argument("channel")
    p_kick.add_argument("target")
    p_kick.add_argument("--reason", default="")
    p_kick.add_argument("--interrupt", action="store_true")
    p_kick.set_defaults(func=cmd_kick)

    p_pause = sub.add_parser("pause", parents=[common], help="Emergency kill switch: stop all doorbells")
    p_pause.add_argument("channel")
    p_pause.add_argument("--reason", default="")
    p_pause.set_defaults(func=cmd_pause)

    p_resume = sub.add_parser("resume", parents=[common], help="Clear PAUSE kill switch")
    p_resume.add_argument("channel")
    p_resume.set_defaults(func=cmd_resume)

    p_status = sub.add_parser("status", parents=[common], help="Show channel roster, claims, and live block state")
    p_status.add_argument("channel")
    p_status.add_argument("--no-live", action="store_true")
    p_status.set_defaults(func=cmd_status)

    p_wait = sub.add_parser("_wait-ring", parents=[common], help=argparse.SUPPRESS)
    p_wait.add_argument("channel")
    p_wait.add_argument("target_block")
    p_wait.add_argument("--target-host", default="local")
    p_wait.add_argument("--sender-nick", required=True)
    p_wait.add_argument("--sender-key", required=True)
    p_wait.add_argument("--timeout", type=int, default=DEFAULT_WAIT_TIMEOUT)
    p_wait.add_argument("--lock-fd", type=int, default=None)
    p_wait.set_defaults(func=cmd_wait_ring)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
