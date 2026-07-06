# /update — Update AIO Analytics Builder

Pull the latest version of AIO Analytics Builder from the git repository and show what changed.

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
> "Would you like to update now?"

### 3. Pull the update

If the user confirms (or didn't object):

```bash
git pull origin main
```

Then show what changed in detail:

```bash
git log HEAD~N..HEAD --oneline
```

Where N is the number of commits that were pulled.

### 4. Summarize changes

After pulling, briefly summarize the changes in plain language:
- Group by type: fixes, new features, documentation updates
- Highlight anything that affects the user's workflow (new required fields, changed API patterns, new commands)
- If CHANGELOG.md was updated, read the new entries and present them as the summary instead of interpreting commit messages

### 5. Confirm success

> "Updated successfully. You're now on the latest version."

If any of the updated files are currently open or were recently used in this session, mention that they should restart their Claude Code session to pick up the changes to skill files.
