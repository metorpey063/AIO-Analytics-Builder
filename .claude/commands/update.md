# /update — Update AIO Analytics Builder

Pull the latest version of AIO Analytics Builder from the git repository. This ensures you have exactly what's in git — no merge conflicts, no stale local fixes.

**Remote repository:** `https://github.com/metorpey063/AIO-Analytics-Builder.git`

---

## Steps

### 0. Check if this is a git repo

Run:

```bash
git rev-parse --is-inside-work-tree 2>/dev/null
```

If this returns `false` or fails (exit code != 0), the user has the project files but **not** the git repo. This happens when the project was copied, downloaded as a ZIP, or shared without `.git/`.

**Fix it for them automatically:**

```bash
git init
git remote add origin https://github.com/metorpey063/AIO-Analytics-Builder.git
git fetch origin main
git reset --mixed origin/main
```

Tell the user:

> "I've connected this project to the AIO Analytics Builder repository. You're now set up to receive updates. Running the update now..."

Then continue to Step 1.

### 1. Fetch and check for updates

Run:

```bash
git fetch origin main 2>/dev/null && git rev-list HEAD..origin/main --count
```

- If the command **fails** (no network): tell the user "Couldn't reach the remote repository. Check your network connection and try again."
- If the result is `0`: tell the user "You're already on the latest version." and show the most recent commit: `git log --oneline -1`
- If the result is **1 or more**: continue to Step 2.

### 2. Show what's available

Tell the user how many commits are available, then show a preview:

```bash
git log HEAD..origin/main --oneline
```

Format the output clearly:

> "There are `N` update(s) available:"
> (list of commit messages)
> "Updating now..."

**Do NOT ask for confirmation** — always proceed with the update. The user invoked `/update` specifically to get updates.

### 3. Apply the update (hard reset to origin/main)

**Critical:** Do NOT use `git pull` or `git merge`. These can cause merge conflicts when Claude has made local fixes to shared files during a session. Instead, force-reset all tracked files to match `origin/main` exactly.

**Protected files** (never overwritten by update):
- `config.json` — user credentials
- `demos/` — user's generated demo assets
- `.claude/settings.local.json` — user's local settings
- `CLAUDE.local.md` — user's private instructions

**Steps:**

```bash
# Stash any uncommitted changes to protected files (safety net)
git stash push -m "pre-update-stash" -- config.json 2>/dev/null

# Hard reset tracked files to match origin/main exactly
git reset --hard origin/main

# Restore config.json from stash if it was stashed
git stash pop 2>/dev/null
```

If `config.json` was not modified (stash is empty), that's fine — `git stash pop` will just say "No stash entries found."

**Why hard reset instead of pull:**
- Guarantees every user has byte-for-byte identical shared code
- Eliminates merge conflicts entirely
- Prevents stale local fixes from persisting after the fix is properly committed upstream
- The only files users modify locally (`config.json`, `demos/`) are either gitignored or stash-protected

### 4. Verify the update landed

```bash
git log --oneline -5
```

Confirm HEAD now matches origin/main:

```bash
git rev-list HEAD..origin/main --count
```

This should return `0`.

### 5. Summarize changes

After updating, briefly summarize the changes in plain language:
- Read the commits that were applied: `git log HEAD~N..HEAD --oneline` (where N is the number of new commits)
- Group by type: fixes, new features, documentation updates
- Highlight anything that affects the user's workflow (new required fields, changed API patterns, new commands)
- If CHANGELOG.md was updated, read the new entries and present them as the summary instead of interpreting commit messages

### 6. Confirm success

> "Updated successfully. You're now on the latest version — all shared files match the repository exactly."

If any of the updated files are skill files (`.claude/commands/`) or `CLAUDE.md`, tell the user:

> "Core instructions were updated. Please start a new Claude Code session to pick up the changes."
