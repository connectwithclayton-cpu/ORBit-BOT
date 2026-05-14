# Cursor / local workspace after ORBit-BOT

When `Fabio_bot` is the **Git repository root** (for example after cloning [ORBit-BOT](https://github.com/connectwithclayton-cpu/ORBit-BOT)):

1. In Cursor: **File → Open Folder…** and choose the clone directory (the folder that contains `backend/`, `frontend/`, `portal/`, and `README.md`).
2. Use a single venv at the repo root; install with `pip install -r backend/requirements.txt` (and optional `-r backend/requirements-dev.txt`).
3. Run Python with `PYTHONPATH=backend:frontend` (matches CI and `backend/pytest.ini`).

If you still open the parent **Cursor Projects** monorepo, treat **`Fabio_bot/`** as the only subtree that syncs to ORBit-BOT; avoid editing duplicate paths outside it for bot code.
