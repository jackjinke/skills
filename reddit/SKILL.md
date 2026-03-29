---
name: reddit
description: This skill should be used when the user asks to "read Reddit", "check Reddit", "browse a subreddit", "read a Reddit post", "search Reddit", or "what's trending on Reddit". Also use this skill automatically whenever any Reddit content needs to be accessed. Fetches posts, comments, and search results from Reddit via OAuth API.
user-invocable: false
allowed-tools:
  - Bash(python scripts/cli.py *)
  - Read
---

# /reddit — Browse and Read Reddit

Read Reddit content using `python scripts/cli.py`. The script authenticates via Reddit OAuth API using environment variables `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`.

Arguments passed: `$ARGUMENTS`

---

## CLI Reference

```
python scripts/cli.py <command> [args...]
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
python scripts/cli.py hot programming 5
python scripts/cli.py top python week 10
python scripts/cli.py post https://reddit.com/r/programming/comments/1s6b9zt/title 20
python scripts/cli.py search "async rust" programming 5
python scripts/cli.py user spez 5
```
