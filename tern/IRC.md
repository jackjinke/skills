# Tern Peer-Agent IRC Collaboration

Use this protocol to coordinate **independent headed coding agents** across Tern blocks—e.g. separate worktrees or projects collaborating, tasks requiring human visibility/steering in each block, or already-running blocks that temporarily join forces. (Keep lightweight single-session delegation in your agent's built-in subagent tool instead of spinning up Tern blocks.) All participants stay live and interactive in their own Tern blocks.

Script path (resolve relative to this skill directory): `IRC="python3 <skill_dir>/scripts/irc.py"`.
Channel root defaults to `/tmp/tern-irc/<channel>/` (override with `--root` or `TERN_IRC_ROOT`).

## Channel Layout

```text
/tmp/tern-irc/<channel>/
├── topic.md               # Goal, task breakdown, constraints
├── members/<block>.json   # Per-block presence, cursor (last_seq), TTL claims
├── log.jsonl              # Append-only channel feed (compact summaries + refs)
├── artifacts/             # Large briefs, diffs, reviews (auto-spilled >1.5KB)
├── doorbell/              # Dedup markers + flock for 0-token deferred waiters
└── PAUSE                  # Present when doorbells are frozen
```

## Lifecycle

1. **Create & Join** — Initiator creates the channel and joins; invite existing or newly launched headed blocks with a single paste giving the channel name and `$IRC` command:
   ```bash
   $IRC init auth-fix --topic "Fix OAuth refresh race; keep API contract intact"
   $IRC join auth-fix --nick lead --role lead --state available
   # Invite peer block $B (only after checking it is idle and not on a dialog):
   tern send "$B" paste "[IRC #auth-fix from lead@$TERN_PANE] Join channel: $IRC join auth-fix --nick reviewer --role worker && $IRC inbox auth-fix"
   tern send "$B" keys enter
   ```
2. **Claim before editing** — Reserve task ID and file globs with a lease TTL (default 15m; renewed on `state` updates):
   ```bash
   $IRC claim auth-fix T2 --files "src/auth/**" "tests/auth/**" --ttl 20
   ```
   A conflict (exit `2`) names the live owner and remaining TTL. Coordinate instead of editing the same files.
3. **Communicate via channel + safe doorbell** — Post structured updates to `log.jsonl`; attach large content via `--body-file` or `--artifact` (bodies >1.5KB spill into `artifacts/` automatically):
   ```bash
   # Ask peer to act and wake if idle (or arm 0-token deferred doorbell if busy):
   $IRC say auth-fix --kind request --to @reviewer --ring \
     --summary "Review refresh-token lock in src/auth/refresh.py" \
     --artifact /tmp/tern-irc/auth-fix/artifacts/t2-handoff.md

   # Informational update (no reply expected):
   $IRC say auth-fix --kind fyi --to @all --summary "API schema frozen in docs/auth.md"
   ```
4. **Drain at turn boundaries (no mid-task polling)** — Never poll while working. Run `inbox` only at natural boundaries: before claiming/editing shared files, before going idle/reporting completion, or when blocked:
   ```bash
   $IRC inbox auth-fix
   ```
   `inbox` advances `last_seq` (serving as a read receipt) and clears pending doorbell markers.
5. **Part cleanly (never close the block)** — Independent blocks often join temporarily and return to their own work afterward:
   ```bash
   $IRC part auth-fix --summary "T2 reviewed; findings in artifacts/t2-review.md" \
     --artifact /tmp/tern-irc/auth-fix/artifacts/t2-review.md
   ```
   `part` releases all claims, logs the handoff, and leaves the Tern block open.

## Coordination Rules

- **Message kinds & anti-ping-pong**:
  - `fyi`: read and absorb; **do not reply** (eliminates courtesy loops).
  - `request`: expects action or a concrete answer.
  - `handoff`: deliverable summary (`status`, `changes`, `tests`, `risks`, `next action`).
  - `blocked`: needs unblocking from peer or human.
- **Presence states**: `available` (idle in channel), `working` (busy on a channel task), `busy-external` (busy with an unrelated user/personal task — never interrupted mid-turn; deferred doorbell waits for idle + 5s quiet), `parted`, `quit`.
- **Zero-polling delivery & `--urgent`**:
  - Normal `--ring` wakes an idle peer once (deduped by `doorbell/<block>.rung`). If the peer is `working` or typing (`quiet_ms < 3000`, or `< 5000` for `busy-external`), `irc.py` spawns at most one detached 0-token waiter (`flock`-deduped) that exits silently if the peer drains on its own, or sends one merged wake-up when the peer becomes idle.
  - Reserve `--urgent` strictly for stop-work or direction-change interrupts that cannot wait for the peer's current turn to finish.
- **Dialog Guard**: `irc.py` inspects `tern capture <block> --surfaces` before sending Enter. If a confirmation, permission, or question prompt is visible, it withholds the doorbell (even for `--urgent`) and logs a `dialog_alert` for the human instead of accidentally approving the dialog.
- **No silent duplication (Cancel-before-Reassign)**: Slowness is not failure. Check live progress read-only with `$IRC status <ch>` and `tern capture <block> --surfaces`. Never duplicate a live `working` peer's claimed task. Reassign only after the owner `part`s, its block exits, its TTL expires while verified idle, or the lead explicitly cancels it first:
  ```bash
  $IRC kick auth-fix @slow-worker --interrupt --reason "Reassigning T2 after 15m stall"
  ```
- **Runaway kill switch**: Run `$IRC pause <ch> --reason "..."` to immediately halt all doorbells; `$IRC resume <ch>` to lift it.

## Heterogeneous / Sandboxed Blocks (`pull-only`)

If a headed block runs a sandboxed or protocol-unaware CLI that cannot read `/tmp/tern-irc` or run `irc.py`:

1. Register and claim on its behalf so other peers respect its ownership:
   ```bash
   $IRC join auth-fix --nick codex --role worker --mode pull-only --block "$B"
   $IRC claim auth-fix T3 --files "src/parser/**" --block "$B"
   ```
2. Send one single-flight brief with `tern send "$B" paste ...` + `enter` (verify idle and Dialog Guard clean first).
3. Monitor read-only via `tern inspect --json` (`.panes[] | select(.pane == $B)`) and `tern capture "$B" --surfaces --scrollback`; once complete, save the summary to `artifacts/` and close its membership with `$IRC part auth-fix --block "$B" --summary "..."`.

## Cross-Host Collaboration (`--host`)

Pick one machine as the **Channel Hub** (normally the initiator's local host, or a shared remote machine reachable by all peers). Identify remote blocks with `--host user@host --block <REMOTE_ID>` so `<host>:<block>` stays unique across daemons.

- **Control plane over SSH**: When a member has `host != local`, `irc.py` automatically wraps `tern inspect`, `tern capture --surfaces`, `tern send`, and `kick --interrupt` in `ssh -o BatchMode=yes <host> 'export PATH="$HOME/.local/bin:$PATH"; tern ...'`. Dialog Guard and 0-token deferred doorbells work unchanged across hosts.
- **Bidirectional SSH / shared hub (`full` mode)**: Remote agents invoke `ssh <hub> "python3 <hub_skill_dir>/scripts/irc.py inbox|say|part <ch> --host <my_ssh_name> --block $TERN_PANE"` (or access the same shared filesystem).
- **One-way SSH (`pull-only` mode — local reaches remote, remote cannot SSH back)**:
  1. Register and claim on the local Hub with `--host user@host --block "$REM_B" --mode pull-only`.
  2. Stage large briefs with `scp` to `/tmp/tern-irc-stage/<ch>/` on the remote host, then send a single-flight prompt via `ssh user@host "export PATH=\"\$HOME/.local/bin:\$PATH\"; tern send $REM_B paste ... && tern send $REM_B keys enter"` (verify idle + Dialog Guard first).
  3. Collect results via `scp` or `ssh user@host "... tern capture $REM_B --surfaces --scrollback"` once `.working == false`, record the summary in the Hub channel, and run `$IRC part <ch> --host user@host --block "$REM_B"`.
