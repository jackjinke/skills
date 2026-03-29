---
name: reddit
description: This skill should be used when the user asks to "read Reddit", "check Reddit", "browse a subreddit", "read a Reddit post", "search Reddit", or "what's trending on Reddit". Also use this skill automatically whenever any Reddit content needs to be accessed. Fetches posts, comments, and search results from Reddit via OAuth API.
user-invocable: true
allowed-tools:
  - Bash(~/.claude/skills/reddit/scripts/reddit-cli *)
  - Read
---

# /reddit — Browse and Read Reddit

Read Reddit content using the bundled `reddit-cli` script at `~/.claude/skills/reddit/scripts/reddit-cli`. The script authenticates via Reddit OAuth API using environment variables `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`.

Arguments passed: `$ARGUMENTS`

---

## CLI Reference

```
~/.claude/skills/reddit/scripts/reddit-cli <command> [args...]
```

| Command | Arguments | Description |
|---------|-----------|-------------|
| `hot`   | `<subreddit> [limit]` | Hot posts (default: programming, 10) |
| `top`   | `<subreddit> [time] [limit]` | Top posts (time: hour/day/week/month/year/all) |
| `new`   | `<subreddit> [limit]` | New posts |
| `post`  | `<url> [comment_limit]` | Read a specific post + comments |
| `search`| `<query> [subreddit] [limit]` | Search posts |
| `user`  | `<username> [limit]` | User's submitted posts |

## Handling Arguments

Parse `$ARGUMENTS` to determine the command:

- No arguments or bare subreddit name → `hot <subreddit> 10`
- A Reddit URL → `post <url>`
- A search query → `search "<query>" <subreddit>`
- Explicit command (e.g., "top posts on r/python this month") → `top python month 10`

## Examples

```bash
~/.claude/skills/reddit/scripts/reddit-cli hot programming 5
~/.claude/skills/reddit/scripts/reddit-cli top python week 10
~/.claude/skills/reddit/scripts/reddit-cli post https://reddit.com/r/programming/comments/1s6b9zt/i_decompiled_the_white_houses_new_app/ 20
~/.claude/skills/reddit/scripts/reddit-cli search "async rust" programming 5
~/.claude/skills/reddit/scripts/reddit-cli user spez 5
```
