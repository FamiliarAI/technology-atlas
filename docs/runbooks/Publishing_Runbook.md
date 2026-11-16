# Publishing Runbook

Updated November 16, 2026. Four pieces of deferred work, in order: prepare the repository for a public GitHub release, deploy the static site to Cloudflare Pages, write a contributor guide, and add CI. Every step is the owner's to run; nothing here has been run yet. Commands are run from the repository root unless a step says otherwise. Numbers quoted as "measured" were taken on November 16 from read-only commands; re-measure before acting.

Placeholders: `OLD_EMAIL` (the address in today's history), `NEW_NAME` and `NEW_EMAIL` (the public identity), `YOUR_DOMAIN` (the site's domain), `PUBLIC_REPO` (for example `FamiliarAI/technology-atlas`). Never write the real old address into a committed file.

## State on November 16

| Item | Measured |
| --- | --- |
| Commits | 310 on `master`; one author identity (`myprak`, a personal Gmail address), the same for committer |
| Remote | `origin` is `git@github.com:FamiliarAI/technology-atlas.git`, a **private** repository (`atlas/web/src/site.js` says so). `origin/master` holds the first 130 commits (to November 12) and `origin/v1` exists. The history has been pushed, privately |
| Other refs | Local branch `v1`; two `refs/codex/turn-diffs/...` checkpoint refs |
| Tracked files | 971: 875 under `atlas/core`, the rest code, tests, prompts and docs. No `atlas/data`, `ingestion/runs`, `.env`, database or saved copy is tracked |
| History | 825 paths no longer in the tree, about 59 MiB of blobs, under the retired top-level folders `Atlas/`, `research/`, `web/` and `AI_Takeoff_Project_Plan.md` (section 1c) |
| Secrets | None found in history or in tracked files (section 1a). `.env` (one line, the OpenRouter key) has never been committed and is ignored by `.gitignore` |
| Checks | `ruff format --check atlas ingestion`: 40 files already formatted. Atlas tests 112 OK; ingestion tests 111 OK; `python3 -m atlas.core check` exit 0. The same pass in a fresh clone with no `atlas/data` or `ingestion/runs` |
| Public export | `atlas/data/public`: 1,680 files, 42 MB, 829 pages (759 published breakthroughs, 67 fields), largest file `assets/index-*.js` at 453 KB, then `data/search.json` 200 KB. 0 share images |
| Share images | `atlas/data/share-out/share` holds 809 PNGs from November 13: older than the database and the built site, and covering unpublished breakthroughs too (section 1e) |

## 1. Pre-publish prep

Do this in one sitting, with no `atlas.page`, `atlas.review` or `run_pages.sh` job running, because the rewrite in 1b replaces every commit. Start with a backup that holds every ref:

```bash
git status --short                          # must be empty
pgrep -fl 'atlas\.(page|review|find|brief)|run_pages' || echo 'nothing running'
git bundle create ~/atlas-backup-$(date +%Y%m%d).bundle --all
git bundle verify ~/atlas-backup-$(date +%Y%m%d).bundle
cp .env ~/atlas-env-backup                  # the rewrite does not touch ignored files; this is belt and braces
```

Done: the bundle verifies, and lists `refs/heads/master`, `refs/heads/v1` and the `refs/codex/...` refs. Keep it off the repository folder until the public repository has been live for a while. `atlas/data` (22 GB) and `ingestion/runs` (5.3 GB) are ignored and are not in the bundle; they are untouched by everything below.

Install the tools once:

```bash
brew install gitleaks trufflehog git-filter-repo
```

### 1a. Secret scan

Scan all of history (every ref, not only `master`) and the files that would be published.

```bash
gitleaks git --log-opts="--all" -v .                    # history; gitleaks 8.19 or later
rm -rf /tmp/atlas-tree && mkdir /tmp/atlas-tree && git archive HEAD | tar -x -C /tmp/atlas-tree
gitleaks dir -v /tmp/atlas-tree                         # tracked files only (not .env, not atlas/data)
gitleaks dir -v atlas/data/public                       # the site that will be uploaded
trufflehog git file://. --results=verified,unknown      # second opinion; scans every branch
```

With gitleaks older than 8.19 the commands are `gitleaks detect --source . --log-opts="--all" -v` and `gitleaks detect --no-git --source /tmp/atlas-tree -v`. Do not run a directory scan on the repository root: it reads `.env` and the 27 GB of ignored data.

Then the pattern grep across `git log -p`. These print counts and locations, never values:

```bash
KEYS='(^|[^A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}|sk-(or|proj|ant)-|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|github_pat_|AIza[0-9A-Za-z_-]{30}|BEGIN [A-Z ]*PRIVATE KEY'
ASSIGN='(OPENROUTER|OPENAI|ANTHROPIC|XAI|GROK)?_?API_KEY *[=:] *["'\'']?[A-Za-z0-9_-]{16,}'
git log --all -p | grep -c -E "$KEYS"                  # expect 0
git log --all -p | grep -c -E "$ASSIGN"                # expect 0
git log --all --format=%B | grep -c -E "$KEYS"         # commit messages; expect 0
git log --all -p | grep -c -E 'OPENROUTER|OPENAI_API|API_KEY'   # 16 on Nov 16: code that reads the key, not keys
git log --all --format=%h -- .env '**/.env' | wc -l    # expect 0: .env was never committed
git check-ignore -v .env                               # .gitignore:12:.env
```

The word boundary in `KEYS` matters: a bare `sk-` pattern matches 47 lines inside words such as `risk-` in source URLs in `atlas/core`. Measured November 16: every expected-0 line was 0, and the gitleaks and trufflehog runs had not yet been done.

If a count is not 0, find where without printing it: `git log --all -G'<the pattern>' --format='%h %ad' --date=short --name-only`.

**If something is found:**

1. **Rotate first.** Treat the key as leaked: the private `origin` already holds every commit up to November 12. For OpenRouter, delete the key at openrouter.ai (Keys), create a new one, and put it in `.env` (or `OPENROUTER_API_KEY` in the environment; `ingestion/providers.py` reads either). For a model CLI login, sign out and in again.
2. **Then rewrite history**, in the same pass as 1b. For a file that should never have been committed, add `--path FILE` to the `--invert-paths` list. For a value inside a file that must stay, write a file `../replacements.txt` with one line `literal:THE_OLD_VALUE==>REDACTED` (keep it outside the repository and delete it afterwards) and add `--replace-text ../replacements.txt` to the filter-repo command.
3. **Rescan** with every command above. Done when all report nothing.

### 1b. Clean the private email from history

All 310 commits carry the personal Gmail address as author and committer. Replace it with a GitHub noreply address, which keeps commits linked to the GitHub account without publishing a mailbox. The owner looks up their own:

```bash
gh api user --jq '"\(.id)+\(.login)@users.noreply.github.com"'   # this is NEW_EMAIL
```

Choose `NEW_NAME` to match the site's byline (the `AUTHOR` constant in `atlas/web/src/site.js`) rather than the handle `myprak`. In GitHub settings (Emails), turn on "Keep my email addresses private" and "Block command line pushes that expose my email".

Write the mailmap outside the repository, so the old address is never committed:

```bash
printf '%s\n' 'NEW_NAME <NEW_EMAIL> <OLD_EMAIL>' > ../atlas-mailmap.txt   # fill in the three values in the file
```

Drop the Codex checkpoint refs (they are in the bundle), decide on `v1` (it is 215 commits behind `master`; delete it with `git branch -D v1` unless it is wanted publicly), then rewrite in place. One run applies the mailmap and removes the paths chosen in 1c:

```bash
git for-each-ref --format='%(refname)' refs/codex | xargs -n1 git update-ref -d
git filter-repo --force \
  --mailmap ../atlas-mailmap.txt \
  --invert-paths \
  --path Atlas/archive/sources/ \
  --path AI_Takeoff_Project_Plan.md          # drop this line to keep it; add any other path chosen in 1c
git config user.name 'NEW_NAME'
git config user.email 'NEW_EMAIL'
rm ../atlas-mailmap.txt
```

`--force` is needed because this is a working copy, not a fresh clone; it is why the backup comes first. Rewriting in place keeps `.env`, `atlas/data` and `ingestion/runs`. Every commit hash changes. That is acceptable because the history has only been pushed to the private `origin`, which is retired in 1f, never to a public place. filter-repo removes the `origin` remote; `git remote -v` shows it.

Checks:

```bash
git log --all --format='%an <%ae> | %cn <%ce>' | sort | uniq -c       # one line, NEW_NAME <NEW_EMAIL> twice
git log --all --format='%ae %ce %B' | grep -c -F 'OLD_EMAIL'          # 0
git grep -c -F 'OLD_EMAIL'                                           # nothing
git rev-list --objects --all | grep -c '^[0-9a-f]* Atlas/archive/sources/'   # 0
git rev-list --count master                                          # 310, less any commit that only touched purged paths
python3 -m atlas.core check && python3 -m unittest discover -s atlas/tests
```

Done: one author identity, no purged path reachable from any ref, the check and tests still pass. Commits that `atlas.core new` and the other writers make from now on use the new local identity.

### 1c. Large or private files

What is tracked today is clean:

```bash
git ls-files | wc -l                                                  # 971
git ls-files | cut -d/ -f1-2 | sort | uniq -c | sort -rn | head
git ls-files | grep -E '^(atlas/data|ingestion/runs)/|(^|/)\.env$|\.sqlite3$|/sources/|\.(pdf|xlsx)$'   # nothing
git check-ignore -v .env atlas/data ingestion/runs atlas/static/site
```

`ingestion/runs/` (5.3 GB) holds the pipeline's attempts, caches, raw model output and 2,638 saved source copies (PDF and HTML), including pages from paywalled publishers. `atlas/data/` (22 GB) holds the database, call records and the copies `atlas.add` saved. Both stay ignored and are never published; the [data reference](../data-reference.md) (section 5, "Deliberately left out") keeps saved copies, provenance and local paths out of the site data too. Neither folder has ever been tracked.

History is a different matter. List what was once tracked and no longer is:

```bash
git log --all --format= --name-only --diff-filter=A | sort -u > /tmp/hist.txt
git ls-files | sort > /tmp/now.txt
comm -23 /tmp/hist.txt /tmp/now.txt | cut -d/ -f1-2 | sort | uniq -c | sort -rn
git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)' \
  | awk '$1=="blob"' | sort -k2 -rn | head -15                       # largest blobs
```

| Path in history | What it is | Recommendation |
| --- | --- | --- |
| `Atlas/archive/sources/` | 25 saved source copies (HTML and one 2 MB PDF) from nature.com, sciencedirect.com, PubMed, arpa-h.gov and others; added in `2e15091` and untracked in `ec1b178` (October 31) | **Purge.** Publisher copies must not be published |
| `AI_Takeoff_Project_Plan.md` | The deprecated paid-report plan | Purge unless the owner wants it public |
| `web/sources/` | 66 `v2_<field>.md` lists and `AI_Takeoff_Master_Table.xlsx` | Owner's call; purge if the spreadsheet is private |
| `research/` | Source audit, connection review and a 27 MB `reviewed-project-state.json` | Owner's call; harmless but large |
| `Atlas/research/` | Raw prompts and Grok session logs from the October 31 pilots | Owner's call |

Add each purged path as a `--path` line in the 1b command (a folder ends in `/`). After the rewrite, rerun the `comm` list: only the paths kept on purpose remain. GitHub refuses files over 100 MB; the largest blob is 27 MB, so nothing has to go for size alone.

`docs/ingestion-status-2026-11-01.md` contains 76 absolute paths under the home folder, which show the macOS user name. Harmless; replace them with repository-relative paths in a normal commit if wanted.

### 1d. Byline, About page and license

The name appears in four places. Make them agree before the first public push.

| Where | Today | Change |
| --- | --- | --- |
| Site footer and About byline | `AUTHOR` in `atlas/web/src/site.js` | Keep or change the constant |
| Repository link and "open an issue" | `REPOSITORY_URL` (`https://github.com/FamiliarAI/technology-atlas`), `REPOSITORY_PUBLIC = false` | Set `REPOSITORY_URL` to `PUBLIC_REPO`, `REPOSITORY_PUBLIC = true`, then `npm run build` and re-export. The footer then links the repository and the Method page links its issues |
| Commit author | `myprak` | `NEW_NAME` from 1b |
| `LICENSE` | none | see below |

There is also no `README.md` at the repository root. A public repository needs one: two sentences on what the atlas is (a map, not a forecast), a link to the live site, links to `atlas/README.md`, `docs/data-reference.md` and `CONTRIBUTING.md`, and the license summary.

**License: a decision for the owner, not a default.** The repository holds two kinds of thing, and they are usually licensed apart:

| Part | Common choices | Notes |
| --- | --- | --- |
| Code (`atlas/*.py`, `ingestion/`, `atlas/web/src`, prompts) | MIT (short, permissive) or Apache-2.0 (adds a patent grant) | |
| Data (`atlas/core/`, the exported `data/`) | CC BY 4.0 (reuse with credit), CC BY-SA 4.0 (reuse must stay open), CC0 (no conditions) | Quotations and titles from sources in the records are excerpts of others' works and are not relicensed; say so in the license notice |
| Bundled fonts and libraries | Their own licenses (Jura, Newsreader, JetBrains Mono under the SIL Open Font License, via `@fontsource`) | Nothing to do beyond not claiming them |

A frequent pairing is MIT for code plus CC BY 4.0 for data: a `LICENSE` file with the MIT text (`Copyright (c) 2026 NEW_NAME`), a `LICENSE-DATA` file or section naming CC BY 4.0 for `atlas/core/`, and one line in the root README and on the About page. Decide before the first push; relicensing later is harder once others have copied it.

Done: footer, About, commits and `LICENSE` show the same name; `REPOSITORY_PUBLIC` is true in the build that will be deployed.

### 1e. Share images

`atlas.export` copies **every** PNG in the `--share` folder, so a folder with cards for unpublished breakthroughs would publish their titles. Make a fresh folder holding only the cards the public export uses. `atlas.share` needs Playwright with Chromium and the local server; both work with the default `python3` (miniforge) on this computer.

```bash
python3 -m atlas.store && (cd atlas/web && npm run build)
python3 -m atlas.export atlas/data/public --public            # gives the public catalog
python3 -m atlas.server --port 8765 &
IDS=$(python3 -c "import json; c = json.load(open('atlas/data/public/data/catalog.json')); print(' '.join(['default'] + [f['id'] for f in c['fields']] + [b['id'] for b in c['breakthroughs']]))")
python3 -m atlas.share atlas/data/share-public --only $IDS --workers 4
kill %1
python3 -m atlas.export atlas/data/public --public --share atlas/data/share-public --base-url https://YOUR_DOMAIN
```

Until a custom domain exists, use `https://<project>.pages.dev` as the base URL, and re-export with the final domain later: `og:image` and `og:url` are absolute only with `--base-url`, and link previews on most networks need them absolute.

Checks:

```bash
ls atlas/data/share-public/share | wc -l                      # 827 today: 759 + 67 + default
grep -o '<meta property="og:image"[^>]*>' atlas/data/public/b/QUA-01/index.html
```

Open two or three PNGs. Done: the export prints `0 pages have none`, and `og:image` is `https://YOUR_DOMAIN/share/QUA-01.png`. Leave `atlas/data/share-out` (November 13, all 809 cards) alone or delete it; do not pass it to a public export.

### 1f. Create the public GitHub repository

The private `FamiliarAI/technology-atlas` holds the old history (old email, the 25 publisher copies). **Do not make it public**: GitHub keeps old commits reachable by hash. Rename it aside (or delete it once the bundle is safe), then create a fresh public repository at the name the site already links to:

```bash
gh repo view FamiliarAI/technology-atlas --json visibility,isPrivate     # confirm PRIVATE
gh repo rename -R FamiliarAI/technology-atlas technology-atlas-private-archive
gh repo create PUBLIC_REPO --public --source=. --remote=origin \
  --description 'A map of the breakthroughs worth working towards, and the milestones that show how close each is.'
git push -u origin master
gh repo edit PUBLIC_REPO --enable-secret-scanning
gh repo edit PUBLIC_REPO --enable-secret-scanning-push-protection
```

Push `master` only (and `v1` only if kept on purpose). Before pushing, run the 1a scans one last time on the rewritten history, and commit `LICENSE`, `README.md`, `CONTRIBUTING.md` (section 3) and the `site.js` change.

Checks: `gh repo view PUBLIC_REPO --json visibility,defaultBranchRef`; on github.com, open Insights, Contributors (one identity, the new one), search the repository for `OLD_EMAIL` (no results), and open a commit to see the noreply author. Done: a public repository whose history matches the local `master` hash for hash.

## 2. Cloudflare Pages deploy

The owner creates the Cloudflare account and logs in; nothing here does it for them.

```bash
npx wrangler login                 # wrangler 4.90.0 is installed globally; `wrangler` works too
npx wrangler whoami
npx wrangler pages project create technology-atlas --production-branch master
```

### Option A: Direct Upload (recommended)

```bash
gitleaks dir -v atlas/data/public
find atlas/data/public -type f | wc -l                                   # 1,680 today; about 2,510 with share images
find atlas/data/public -type f -exec stat -f '%z %N' {} + | sort -rn | head -3   # largest file
npx wrangler pages deploy atlas/data/public --project-name technology-atlas --branch master \
  --commit-hash "$(git rev-parse HEAD)" --commit-message "$(git log -1 --format=%s)"
```

Each deploy prints a preview URL and updates `technology-atlas.pages.dev`. A deploy with `--branch` other than `master` is a preview, useful for checking an export before it goes live.

### Option B: GitHub Actions builds and deploys

A workflow checks out the repository, runs `python3 -m atlas.store`, `npm ci && npm run build` in `atlas/web`, `python3 -m atlas.export site --public --base-url ...`, and deploys with `cloudflare/wrangler-action` using a `CLOUDFLARE_API_TOKEN` secret (Pages: Edit) and the account ID. Cloudflare's own Git build is not needed. It is feasible: measured November 16, a fresh clone with no `atlas/data` and no `ingestion/runs` rebuilds the database (all 3,947 saved copies reported missing and skipped) and writes a public export byte-for-byte identical to `atlas/data/public` (`diff -rq`: no differences). Share images are the hard part: they need Playwright, Chromium and the server running inside the job.

### Recommendation: Option A

Publishing is an editorial act: the site design says publishing needs the owner's authorization, and `atlas.review` decides what is public. A deploy that runs on every push to `master` would publish whatever the page and review passes last committed, including unattended `run_pages.sh` commits. Direct Upload deploys exactly the export the owner previewed at `http://127.0.0.1:8766` (see the [data reference](../data-reference.md), section 7), with share images made locally where Playwright already works, and no Cloudflare token stored in GitHub. Revisit Option B if deploys become frequent; the clean-clone result above shows it would produce the same site.

### Custom domain

In the Cloudflare dashboard: Workers & Pages, `technology-atlas`, Custom domains, Set up a custom domain. If the domain's DNS is on Cloudflare the record is added for you; otherwise add a `CNAME` from the name to `technology-atlas.pages.dev` at the DNS host. Wait for the certificate to show Active. Then re-export with `--base-url https://YOUR_DOMAIN` (1e) and deploy again, so share tags point at the final domain.

### 404 page

`atlas.export` writes `404.html` at the root ("Off the chart"). Pages serves it with status 404 for any path without a file, and its presence also turns off Pages' single-page-app fallback, which is right here: every real route has its own `index.html`. Pages serves `b/QUA-01/index.html` at `/b/QUA-01/` and redirects `/b/QUA-01` to it.

### Limits

Pages allows 20,000 files per deployment and 25 MiB per file. Today: 1,680 files and a 453 KB largest file; with 827 share images about 2,510 files. Each published breakthrough adds two files (`b/<ID>/index.html`, `data/b/<ID>.json`) and one image, so the limit is far off. Re-measure with the two `find` lines before each deploy; a failure says which limit.

### Cache headers

Create `atlas/web/public/_headers`. Vite copies `public/` into the build and the export copies the build, so it lands at the site root:

```
/assets/*
  Cache-Control: public, max-age=31536000, immutable

/data/*
  Cache-Control: public, max-age=300, must-revalidate

/share/*
  Cache-Control: public, max-age=86400

/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
```

`assets/` file names carry a content hash, so a year is safe; data and share images change with each export, so they stay short. HTML keeps Pages' default (revalidate). The export's `.atlas-export` marker file is uploaded too; it is harmless.

### Check the live site

```bash
SITE=https://YOUR_DOMAIN
for p in / /atlas/ /about/ /field/QUA/ /b/QUA-01/ /data/catalog.json /share/default.png; do
  printf '%s %s\n' "$(curl -s -o /dev/null -w '%{http_code}' "$SITE$p")" "$p"; done   # all 200
curl -s -o /dev/null -w '%{http_code}\n' "$SITE/no-such-page"        # 404
curl -sI "$SITE/assets/$(ls atlas/data/public/assets | grep '^index-.*\.js$')" | grep -i cache-control
curl -s "$SITE/b/QUA-01/" | grep -o '<meta property="og:[a-z:]*" content="[^"]*"'
curl -s -o /dev/null -w '%{http_code}\n' "$SITE/.env"                # 404
```

Then in a browser, at desktop and phone width: Home, the atlas chart, a field, a breakthrough, search, About (byline, repository and issue links), a deep link opened directly, and `/review` and `/draft/QUA-01` (they must show nothing that is not published; the static site has no `/api`). Paste a breakthrough URL into a link-preview checker to see the card. Done: every check above passes on the custom domain.

## 3. Contributor guide

The draft is [docs/drafts/CONTRIBUTING.draft.md](../drafts/CONTRIBUTING.draft.md). Outline:

1. What the atlas is and is not (a map, not a forecast; no order claims, no dates).
2. Ways to help without any setup: open an issue to challenge an entry, suggest a source, or propose a breakthrough.
3. Propose a breakthrough with `python3 -m atlas.core new` (no model call).
4. Suggest a source: an issue or a pull request naming the breakthrough, milestone and URL; the owner judges it with `python3 -m atlas.page add ID URL`.
5. How review and publishing work (`atlas.review`; only `published` reaches the site).
6. Code changes: style and tests as in `AGENTS.md`.
7. No API keys needed; model passes run on the owner's side.

Before it becomes `CONTRIBUTING.md` at the root: confirm the license names from 1d, the repository URL, and that the owner is happy to receive issues. Done: `CONTRIBUTING.md` is committed and linked from the root README and the About page.

## 4. CI

The draft workflow is [docs/drafts/ci.yml.draft](../drafts/ci.yml.draft). It is outside `.github/workflows/`, so it runs nowhere. Jobs:

| Job | Runs | Measured locally |
| --- | --- | --- |
| `format` | `ruff format --check atlas ingestion` with ruff pinned to 0.11.13 (the local version) | 40 files already formatted |
| `atlas-tests` | `python3 -m unittest discover -s atlas/tests` and `python3 -m atlas.core check` | 112 OK; check exit 0, also in a fresh clone |
| `ingestion-tests` | `pip install -r ingestion/requirements.txt` (`jsonschema`, `pypdf`), then the ingestion tests | 111 OK |
| `web` | `npm ci && npm run build` in `atlas/web` (npm; `package-lock.json` is tracked), Node 22 | not run here; the build writes `atlas/static/site` |
| `secrets` | TruffleHog over the pushed commits | |

The tests make no model or network calls and mock `git`, so the jobs need no secrets. To activate: copy the draft to `.github/workflows/ci.yml`, pin `trufflesecurity/trufflehog` to a release tag, push on a branch, and watch it with `gh run watch`. Done: all five jobs green on a pull request, then require them in branch protection (Settings, Branches, `master`).
