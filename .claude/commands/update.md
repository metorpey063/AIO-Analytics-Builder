# /update — Update AIO Analytics Builder

Pull the latest version of AIO Analytics Builder from the git repository and show what changed.

---

## Steps

### 1. Fetch and check for updates

Run:

```bash
git fetch origin main 2>/dev/null && git rev-list HEAD..origin/main --count
```

- If the command **fails** (no network, not a git repo, etc.): tell the user "Couldn't reach the remote repository. Check your network connection and try again."
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
