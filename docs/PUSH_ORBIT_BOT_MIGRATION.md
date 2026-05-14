# One-time push to ORBit-BOT (preserved `Fabio_bot/` history)

The branch **`orbit-bot-export-main`** in the **Cursor Projects** monorepo is a `git subtree split` of **`Fabio_bot/`** only. It is suitable to become **`main`** on [ORBit-BOT](https://github.com/connectwithclayton-cpu/ORBit-BOT).

## Regenerate the branch (optional)

From the monorepo root:

```bash
cd "/path/to/Cursor Projects"
git fetch origin
git subtree split --prefix=Fabio_bot -b orbit-bot-export-main
```

## Push (requires GitHub auth)

HTTPS (prompts or uses credential helper):

```bash
git remote add orbit-bot https://github.com/connectwithclayton-cpu/ORBit-BOT.git   # once, if missing
git push -u orbit-bot orbit-bot-export-main:main
```

SSH:

```bash
git remote add orbit-bot git@github.com:connectwithclayton-cpu/ORBit-BOT.git
git push -u orbit-bot orbit-bot-export-main:main
```

If the remote already has commits (for example an initial README), use **`--force-with-lease`** only if you intend to replace them:

```bash
git push --force-with-lease orbit-bot orbit-bot-export-main:main
```

## After a successful push

1. Clone **ORBit-BOT** to a dedicated folder and open that folder as your Cursor project root (see [`CURSOR_WORKSPACE.md`](CURSOR_WORKSPACE.md)).
2. Optional: delete the local branch `orbit-bot-export-main` in the monorepo when you no longer need it (`git branch -D orbit-bot-export-main`).

## Alternative: `git filter-repo`

For a **standalone clone** whose root is only Fabio (same history end-state), use a fresh clone and `python3 -m git_filter_repo --subdirectory-filter Fabio_bot/` on your machine, then `git remote add origin …` and push. That is equivalent to consuming the subtree branch but keeps a clean single-purpose clone.
