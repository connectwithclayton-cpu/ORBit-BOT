# Team access: GitHub

Use this checklist when you need to work in this repository on GitHub. Replace placeholders with the real org/user and repo name your lead gives you (same values as in the root [README.md](../../README.md) clone instructions).

## 1. Account and access

1. **GitHub account** — Use a personal account you control (not a shared login).
2. **Two-factor authentication (2FA)** — If the org or repo owner requires 2FA, enable it under GitHub **Settings → Password and authentication** before accepting an invite.
3. **Invitation** — Ask the repo owner to add you:
   - **Collaborator** on a single private repo, or
   - **Member** of a GitHub Organization with access to the right team/repo.
4. **Accept the invite** — Check email or GitHub **Notifications**; the invite expires if ignored.

If you cannot see the repo after accepting, confirm you are logged into the correct GitHub account in the browser and in Git.

## 2. Choose how Git authenticates

| Method | Best for | Notes |
|--------|-----------|--------|
| **SSH** | Daily laptop development | One-time key setup; no PAT in remote URL. |
| **HTTPS + token** | Quick clone, CI, or hosts where SSH is awkward | GitHub no longer accepts account passwords for Git over HTTPS; use a **Personal Access Token (PAT)** as the password. |

### SSH (recommended for developers)

1. Generate a key (ed25519):

   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com" -f ~/.ssh/id_ed25519_github
   ```

2. Start the agent and add the key (macOS example):

   ```bash
   eval "$(ssh-agent -s)"
   ssh-add ~/.ssh/id_ed25519_github
   ```

3. Copy the **public** key (`.pub`) and add it in GitHub under **Settings → SSH and GPG keys → New SSH key**.

4. Test:

   ```bash
   ssh -T git@github.com
   ```

5. Clone:

   ```bash
   git clone git@github.com:YOUR_ORG_OR_USER/YOUR_REPO_NAME.git
   ```

Optional: use `~/.ssh/config` to set `Host github.com` and `IdentityFile` so the right key is used automatically.

### HTTPS + fine-grained PAT

1. GitHub **Settings → Developer settings → Personal access tokens** — create a **fine-grained** token scoped to this repository with contents read (and write if you will push).
2. Clone:

   ```bash
   git clone https://github.com/YOUR_ORG_OR_USER/YOUR_REPO_NAME.git
   ```

3. When Git prompts for credentials, use your GitHub **username** and the **token** as the password. On macOS, Git Credential Manager can store this securely.

## 3. Local clone alignment with the team

- Clone into a path you own; the root [README.md](../../README.md) suggests a folder name and Python venv steps.
- Default branch is usually **`main`**. After clone:

  ```bash
  git status
  git pull origin main
  ```

- Prefer **short-lived feature branches** and **pull requests** if the repo uses branch protection (ask the owner).

## 4. Security rules everyone follows

- **Never commit** API keys, `.env` files, tokens, or broker credentials. This repo uses `.gitignore` for local secrets; if something sensitive was ever committed, tell the owner immediately so credentials can be **rotated**.
- Do not paste PATs or private keys into chat, tickets, or screenshots.
- CI secrets belong in **GitHub Actions secrets** (or your org’s secret store), not in the codebase.

## 5. If something fails

| Symptom | Things to check |
|---------|-------------------|
| `Repository not found` | Wrong URL, wrong account, or invite not accepted / no permission. |
| `Permission denied (publickey)` | SSH key not added to GitHub, wrong key loaded, or wrong `Host`/`IdentityFile` in SSH config. |
| HTTPS `Authentication failed` | Using password instead of PAT; token expired or missing `repo` scope. |
| Cannot push | Read-only access; need write role or PR workflow only. |

**Escalation** — Contact the repository owner with: your GitHub username, whether you use SSH or HTTPS, and the **exact** error message (redact tokens).
