# /setup — AIO Analytics Builder Setup Wizard

You are running the AIO Analytics Builder setup wizard. Your job is to guide the user through configuring their connections conversationally — asking one question at a time, testing each connection before moving on, and writing credentials to config.json. Do not dump all questions at once.

---

## Step 0 — Connect to remote + update check

**Do this before anything else, every time.**

First, check if this is a git repo connected to the remote:

```bash
git rev-parse --is-inside-work-tree 2>/dev/null && git remote get-url origin 2>/dev/null
```

**If either fails** (not a git repo, or no remote configured), this is a ZIP download or folder copy. Auto-connect it:

```bash
git init 2>/dev/null
git remote remove origin 2>/dev/null
git remote add origin https://github.com/metorpey063/AIO-Analytics-Builder.git
git fetch origin main
git reset --hard origin/main
```

Tell the user:
> "I've connected this project to the AIO Analytics Builder repository and pulled the latest code. You're all set."

Then skip to Step 1 — the hard reset already applied the update.

**If git is set up and remote exists**, check for updates:

```bash
git fetch origin main 2>/dev/null && git rev-list HEAD..origin/main --count
```

- If the command fails (no network) — skip silently and continue.
- If the result is `0` — skip silently and continue.
- If the result is **1 or more** — apply the update automatically:

```bash
git stash push -m "pre-update-stash" -- config.json 2>/dev/null
git reset --hard origin/main
git stash pop 2>/dev/null
```

Tell the user:
> "Updated to the latest version (`N` new commits applied). Here's what changed:"

Show: `git log HEAD~N..HEAD --oneline`

Then continue setup as normal.

---

## Step 1 — Ask about autonomous mode

Before doing anything else, ask:
> "To speed things up, I can run in autonomous mode — that means I won't pause to ask permission before running commands or reading files. Would you like that? (You can always undo it later.)"

- If **yes**: invoke the `update-config` skill with the instruction: "Add permissions to allow Bash commands, file reads, and web fetch requests without prompting, scoped to the project local settings — set allow to [\"Bash(*)\", \"Read\", \"WebFetch(*)\"]." Then confirm to the user: "Autonomous mode enabled — I'll run without interruptions from here."
- If **no**: acknowledge and continue normally. No action needed.

---

## Step 1b — Load existing config and show saved profiles

Run this to see what's already saved:

```bash
python3 -c "
from connections import load_full_config, list_profiles
full = load_full_config()
profiles = list_profiles(full)
if profiles:
    for p in profiles:
        print(f'  [{p[\"key\"]}] {p[\"label\"]} — {p[\"capabilities\"]}{\" (active)\" if p[\"active\"] else \"\"}')
else:
    print('  No saved profiles.')
print('ACTIVE:', full.get('active_profile', 'none'))
"
```

**If profiles exist**, ask the user:
> "You have these saved connections: [list them]. Would you like to use one of these, set up a new connection, or reconfigure an existing one?"

- If they choose an existing profile, set it as active and skip to Step 5 (validation).
- If they choose to reconfigure an existing profile, load it and continue from Step 2.
- If they choose a new connection, ask them to name it (e.g. "Engine Demo Org"), then continue.

**If no profiles exist**, say:
> "No connections saved yet — let's set one up. What would you like to name this connection? (e.g. 'My Demo Org', 'Engine Demo Org')"

---

## Step 2 — Ask which solution to configure

Ask the user:
> "Which solution do you want to configure?
> 1. Tableau Cloud + Pulse — publish Pulse metrics to Tableau Cloud
> 2. Tableau Next (Salesforce Data Cloud) — build Tableau Next demos
> 3. Both — needed for all output modes in /build-demo"

Record their choice. If they choose 1, skip the Salesforce steps. If they choose 2, skip the Tableau steps.

---

## Step 3 — Tableau Cloud (skip if user chose option 2 in Step 2)

Before asking for credentials, check if any existing profiles already have Tableau Cloud configured:

```bash
python3 -c "
from connections import load_full_config
import json
full = load_full_config()
profiles = full.get('profiles', {})
tableau_profiles = {k: v for k, v in profiles.items() if v.get('tableau', {}).get('server_url')}
for k, v in tableau_profiles.items():
    tc = v['tableau']
    print(f'  [{k}] {v.get(\"label\", k)} — {tc[\"server_url\"]} / {tc[\"site_name\"]}')
print('COUNT:', len(tableau_profiles))
"
```

**If existing Tableau profiles are found**, ask:
> "You already have Tableau Cloud configured in another profile ([list them]). Would you like to reuse that same Tableau Cloud connection for this profile?"

- If **yes**: copy the `tableau` section from the chosen profile into the new profile. Skip the credential questions below and go straight to the connection test.
- If **no**: continue and ask for new credentials.

**If no existing Tableau profiles**, skip the question and proceed directly to asking for credentials.

Tell the user:
> "I need a Personal Access Token (PAT) from your Tableau Cloud site. If you don't have one: sign in → click your avatar → Account Settings → Personal Access Tokens → Create new token (name it 'Claude Code') → copy the secret (shown once only)."

Ask these one at a time, waiting for each answer:
1. "What is your Tableau Cloud URL?" (e.g. `https://us-east-1.online.tableau.com/`)
2. "What is your site name?" (the slug in your URL, not the full URL)
3. "What is your PAT secret?"

Then test the connection immediately:

```bash
python3 -c "
import tableauserverclient as TSC, requests, sys
server_url = 'URL_HERE'
site_name = 'SITE_HERE'
pat_secret = 'SECRET_HERE'
try:
    auth = TSC.PersonalAccessTokenAuth('Claude Code', pat_secret, site_id=site_name)
    server = TSC.Server(server_url, use_server_version=True)
    server.auth.sign_in(auth)
    r = requests.get(server_url.rstrip('/') + '/api/-/pulse/definitions?page_size=1',
        headers={'x-tableau-auth': server.auth_token, 'Accept': 'application/json'})
    server.auth.sign_out()
    print('OK' if r.status_code == 200 else f'PULSE_FAIL:{r.status_code}')
except Exception as e:
    print(f'FAIL:{e}')
"
```

- If output is `OK`: tell the user "Tableau Cloud connected successfully" and save to config.
- If `FAIL`: tell the user what went wrong and ask them to check their credentials. Do not proceed until this passes.

---

## Step 4 — Salesforce + Data Cloud (skip if user chose option 1)

### Step 4a — External Client App

Ask the user:
> "Do you already have a Salesforce External Client App set up for AIO Analytics Builder, or do you need to create one?"

**If they already have one**, skip ahead and ask:
1. "Is this a sandbox org?" (yes → use `https://test.salesforce.com`, no → use `https://login.salesforce.com`)
2. "What is your Consumer Key (Client ID)?"
3. "What is your Consumer Secret?"

**If they need to create one**, walk them through the following steps one at a time. For every value they need to type or paste, display it in a fenced code block so the copy button appears automatically. Wait for the user to confirm each step before proceeding to the next.

---

**Step 1 — Basic Information**

> "Let's create the External Client App. Go to Salesforce Setup → search **'App Manager'** → click **'New External Client App'** (top right). Fill in these fields, then type **next** when done:"

- **External Client App Name:**
```
AIO Analytics Builder
```
- **Contact Email:** your email
- **Distribution State:** Local

---

**Step 2 — Enable OAuth**

> "Now expand the **'API (Enable OAuth Settings)'** section and check **'Enable OAuth'**. Set the Callback URL to:"
```
http://localhost:8080/callback
```
> "Type **next** when that's done."

---

**Step 3 — OAuth Scopes**

> "Under **Available OAuth Scopes**, find and move each of these to the **Selected** side (scroll to find them):"
```
Manage user data via APIs (api)
```
```
Manage Data Cloud Ingestion API data (cdp_ingest_api)
```
```
Perform SQL queries on Data Cloud data (cdp_query_api)
```
```
Perform requests at any time (refresh_token)
```
```
Access the Salesforce API Platform (sfap_api)
```
> "Type **next** when all five are selected."

---

**Step 4 — Flow Enablement**

> "Under **Flow Enablement**, check this box:"
```
Enable Authorization Code and Credentials Flow
```
> "Type **next** when done."

---

**Step 5 — Security**

> "Under **Security**, leave **Require Proof Key for Code Exchange (PKCE)** checked — our OAuth flow supports PKCE. No changes needed here. Type **next** to continue."

---

**Step 6 — Save and wait**

> "Click **Create** at the bottom. Then **wait 2–10 minutes** for Salesforce to activate the app before we continue. Type **next** when you're ready."

---

**Step 7 — Get Consumer Key and Secret**

> "Now go to Setup → search **'App Manager'** → click **'External Client App Manager'** → click the app name **'AIO Analytics Builder'** (blue link) → click the **'Settings'** tab → scroll to **'OAuth Settings'** → click **'Consumer Key and Secret'** (may ask you to verify your identity). Copy the Consumer Key and paste it here."

After they paste the Consumer Key, ask for the Consumer Secret.

Also ask:
- "Is this a sandbox org?" (yes → use `https://test.salesforce.com`, no → use `https://login.salesforce.com`)

### Step 4b — OAuth browser flow

Tell the user:
> "Opening your browser now for Salesforce authorization — log in and click Allow, then come back here."

Run the OAuth flow:

```bash
python3 -c "
import sys
sys.path.insert(0, '.')
from oauth_flow import get_refresh_token
import json
try:
    tokens = get_refresh_token('CLIENT_ID_HERE', 'CLIENT_SECRET_HERE', 'LOGIN_URL_HERE')
    print(json.dumps({'refresh_token': tokens['refresh_token'], 'instance_url': tokens['instance_url']}))
except Exception as e:
    print(f'FAIL:{e}')
"
```

If that succeeds, immediately test the Data Cloud token exchange:

```bash
python3 -c "
import requests, json
sf_login_url = 'LOGIN_URL_HERE'
client_id = 'CLIENT_ID_HERE'
client_secret = 'CLIENT_SECRET_HERE'
refresh_token = 'REFRESH_TOKEN_HERE'
try:
    r = requests.post(f'{sf_login_url}/services/oauth2/token',
        data={'grant_type':'refresh_token','refresh_token':refresh_token,
              'client_id':client_id,'client_secret':client_secret})
    sf_token = r.json()['access_token']
    sf_instance = r.json()['instance_url']
    r2 = requests.post(f'{sf_instance}/services/a360/token',
        headers={'Content-Type':'application/x-www-form-urlencoded'},
        data={'grant_type':'urn:salesforce:grant-type:external:cdp',
              'subject_token':sf_token,
              'subject_token_type':'urn:ietf:params:oauth:token-type:access_token'})
    dc = r2.json()
    print(json.dumps({'sf_instance': sf_instance, 'dc_domain': dc['instance_url']}))
except Exception as e:
    print(f'FAIL:{e}')
"
```

- If successful: tell the user both connections are working and save credentials.
- If `FAIL`: diagnose based on the error and guide the user to fix it.

**Common browser auth errors and fixes:**

- **`invalid_client_id`** — The app isn't fully activated yet. Salesforce can take 2–10 minutes after creation before it accepts the Consumer Key. Wait a few minutes and try again.

- **`Cross-org OAuth flows are not supported for this external client app`** — The browser that opened is already logged into a *different* Salesforce org, and Salesforce won't allow the OAuth flow to cross org boundaries. Fix:
  1. Open your browser and sign out of all Salesforce orgs (visit `https://login.salesforce.com`, click your avatar → Log Out, and repeat for any other tabs or orgs)
  2. Log back in to the *target* org — the one where you created the External Client App
  3. Come back here and say **go** to re-open the authorization window

  > "It looks like your browser was logged into a different Salesforce org. Please sign out of all Salesforce sessions in your browser, log back into the org where you created the AIO Analytics Builder app, then come back here and say **go** to try again."

### Step 4c — Ingest Connector

Tell the user:
> "Looking for an existing Data Cloud Ingest API connector..."

Run:

```bash
python3 -c "
import requests, json
sf_login_url = 'LOGIN_URL_HERE'
client_id = 'CLIENT_ID_HERE'
client_secret = 'CLIENT_SECRET_HERE'
refresh_token = 'REFRESH_TOKEN_HERE'
r = requests.post(f'{sf_login_url}/services/oauth2/token',
    data={'grant_type':'refresh_token','refresh_token':refresh_token,
          'client_id':client_id,'client_secret':client_secret})
sf_token = r.json()['access_token']
sf_instance = r.json()['instance_url']
r2 = requests.get(f'{sf_instance}/services/data/v62.0/ssot/connections',
    headers={'Authorization': f'Bearer {sf_token}', 'Content-Type': 'application/json'},
    params={'connectorType': 'IngestApi', 'limit': 100})
connectors = r2.json().get('connections', [])
print(json.dumps(connectors))
"
```

- If connectors are found: show the list and ask the user which one to use.
- If none found: the connector must be created manually in the Salesforce UI. Tell the user:

> "No Ingestion API connector found. You need to create one in Salesforce Setup:
> 1. In Setup, search **"Ingestion API"** — it's under **Data Cloud → External Integrations → Ingestion API**
> 2. Click **"New"** (top right)
> 3. Enter the connector name:
> ```
> analytics_builder_demo
> ```
> 4. Complete any other required fields and save
> 5. Come back here once it's created"

After the user confirms it's created, re-run the connector lookup to get the connector ID and name, then save to config.

---

## Step 5 — Save config and validate

Write the completed profile to config.json using:

```bash
python3 -c "
from connections import load_full_config, save_profile, set_active_profile
import json

full = load_full_config()
profile = {
    'label': 'LABEL_HERE',
    'tableau': {
        'server_url': 'URL_HERE',
        'site_name': 'SITE_HERE',
        'pat_name': 'Claude Code',
        'pat_secret': 'SECRET_HERE',
    },
    'salesforce': {
        'sf_login_url': 'LOGIN_URL_HERE',
        'client_id': 'CLIENT_ID_HERE',
        'client_secret': 'CLIENT_SECRET_HERE',
        'refresh_token': 'REFRESH_TOKEN_HERE',
        'data_cloud_domain': 'DC_DOMAIN_HERE',
        'ingestion_connector_name': 'CONNECTOR_NAME_HERE',
        'connector_sf_id': 'CONNECTOR_ID_HERE',
        'connector_uuid_name': 'CONNECTOR_UUID_HERE',
    }
}
save_profile(full, 'PROFILE_KEY_HERE', profile)
set_active_profile(full, 'PROFILE_KEY_HERE')
print('Saved.')
"
```

Then run a final validation:

```bash
python3 -c "
from connections import load_config, get_tableau_token, tableau_headers, get_sf_token, get_dc_token, sf_headers
import requests

config = load_config()
results = {}

# Tableau
try:
    tc = config['tableau']
    server, token, site_id = get_tableau_token(config)
    r = requests.get(tc['server_url'].rstrip('/') + '/api/-/pulse/definitions?page_size=1',
        headers=tableau_headers(token))
    server.auth.sign_out()
    results['tableau'] = 'OK' if r.status_code == 200 else f'FAIL:{r.status_code}'
except Exception as e:
    results['tableau'] = f'FAIL:{e}'

# Salesforce
try:
    sf_token, sf_instance = get_sf_token(config)
    dc_token, dc_domain = get_dc_token(sf_token, sf_instance)
    results['salesforce'] = f'OK — {sf_instance}'
    results['data_cloud'] = f'OK — {dc_domain}'
except Exception as e:
    results['salesforce'] = f'FAIL:{e}'
    results['data_cloud'] = 'SKIPPED'

connector = config.get('salesforce', {}).get('connector_sf_id', '')
results['connector'] = f'OK — {connector}' if connector else 'NOT SET'

for k, v in results.items():
    print(f'  {k}: {v}')
"
```

Report the results to the user clearly. If everything is OK, say:
> "All systems go! You're ready to build demos. Run /build-demo to get started."

If anything failed, diagnose the issue and guide the user to fix it before finishing.

---

## Notes

- Only ask for credentials that are relevant to the chosen mode (skip Tableau questions for Tableau Next only, skip Salesforce questions for Pulse only).
- Never show the user raw Python errors — translate them into plain English.
- If a connection test fails, do not save that section to config.json until it passes.
- config.json is gitignored — it is safe to write credentials there.
