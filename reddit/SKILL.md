---
name: reddit
description: This skill should be used when the user asks to "read Reddit", "check Reddit", "browse a subreddit", "read a Reddit post", "search Reddit", or "what's trending on Reddit". Also use this skill automatically whenever any Reddit content needs to be accessed. Fetches posts, comments, and search results from Reddit via OAuth API.
user-invocable: true
allowed-tools:
  - Bash(reddit-cli *)
  - Bash(*/reddit-cli *)
  - Read
---

# /reddit — Browse and Read Reddit

Read Reddit content using the `reddit-cli` tool. The tool authenticates via Reddit OAuth API using environment variables `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`.

Arguments passed: `$ARGUMENTS`

---

## CLI Reference

The `reddit-cli` script is located at `~/Projects/skills/reddit/scripts/reddit-cli`.

```
reddit-cli <command> [args...]
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

- No arguments or bare subreddit name → `reddit-cli hot <subreddit> 10`
- A Reddit URL → `reddit-cli post <url>`
- A search query → `reddit-cli search "<query>" <subreddit>`
- Explicit command (e.g., "top posts on r/python this month") → `reddit-cli top python month 10`

## Examples

```bash
# Browse hot posts
reddit-cli hot programming 5

# Top posts this week
reddit-cli top python week 10

# Read a specific post with comments
reddit-cli post https://reddit.com/r/programming/comments/1s6b9zt/i_decompiled_the_white_houses_new_app/ 20

# Search across all subreddits
reddit-cli search "async rust" programming 5

# User's posts
reddit-cli user spez 5
```
