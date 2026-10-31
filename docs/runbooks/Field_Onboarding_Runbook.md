# Field Onboarding Runbook

Instructions for an agent onboarding fields into the Atlas, one field at a time. Pipeline version: `fields_v5`. Updated October 31, 2026.

All paths are relative to the repository root, `/Users/prakashnarayanan/Documents/2026_Takeoff`.

## Your job

For each field you are given (or each field not yet done):

1. Run the research pipeline, producing the field's final list of open problems.
2. Archive every cited source and run machine acceptance.
3. Check the outputs against the checklist below.
4. Commit the field.
5. Report the result in the format at the end of this document.

You run commands and read their output. You do not write or edit research content.

## Ground rules

**Do**

- Run the commands exactly as given, from the directory given.
- Run long steps in the background and wait for them to finish; do not start a second run of the same field while one is running.
- Record every failure. A failed or stopped run stays on disk with its `.FAILED.md` or `.STOPPED.md` note.
- Re-run a failed step rather than fixing its output.

**Do not**

- Edit any file the pipeline produces (`*.json`, `*.notes.md`, `*.jsonl`, logs). There is no hand repair.
- Edit prompts, schemas or scripts. If something seems wrong with them, stop and report it.
- Use any API key, change CLI login, or switch a step to a different model.
- Obtain papers from unauthorised sources (for example Sci-Hub) or get around a site's bot protection. A blocked source is an exception to record, not a problem to work around.
- Commit `Atlas/archive/sources/` (it is git-ignored and must stay so) or push to any remote.

## Before you start

Run these checks once per session. Stop and report if any fails.

```bash
~/.grok/bin/grok models                    # must list grok-4.7; says "logged in with grok.com"
/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex --version
test -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" && echo chrome ok
python3 -c "import jsonschema, pypdf; print('python ok')"
git status --short                         # note anything already uncommitted
```

Use the Codex CLI inside ChatGPT.app, never the `codex` on PATH: the PATH copy cannot reach the GPT-6.x models with a ChatGPT login.

## Step 0. Pick the field

List every field, its abbreviation and whether it is done:

```bash
python3 - <<'EOF'
import json, glob
m = json.load(open('web/data/milestones.json')); m = m['milestones'] if isinstance(m, dict) else m
fields = {}
for x in m: fields.setdefault(x['field'], x['id'].rsplit('-', 1)[0])
for f, ab in fields.items():
    finals = sorted(p for p in glob.glob(f'Atlas/research/fields_v5/{ab}/02_merge__*.json')
                    if not p.endswith(('.schema.json', '.acceptance.json', '.review_process.json')))
    current = finals and 'identified_dependencies' in open(finals[-1]).read()
    accepted = current and glob.glob(finals[-1][:-5] + '.acceptance.json')
    print(f"{ab:5} {'DONE' if accepted else 'merge done, not accepted' if current else 'TODO':26} {f}")
EOF
```

Use the field name **exactly** as printed (it must match `web/data/milestones.json`) and its abbreviation. A field is done only when its newest final list uses `identified_dependencies` and has an `.acceptance.json`. Older final lists in the earlier `related_problems` format count as TODO.

## Step 1. Run the pipeline (research, format, merge)

```bash
cd Atlas/research/fields_v5/tools
python3 -B run_pipeline.py "<Field Name>" <ABBR> --as-of <today, YYYY-MM-DD>
```

Takes 15–25 minutes. Run it in the background. Progress is in `Atlas/research/fields_v5/<ABBR>/pipeline.log`:

| Log line | Meaning |
|---|---|
| `01a_research__… started` / `done` | Grok 4.7 (high) researching the field with web tools, 10–12 min |
| `01b_format__… started` / `done` | GPT-6.1 Terra (high) converting notes to JSON, about 2 min |
| `02_merge__… started` / `done` | GPT-6.1 Sol (medium) deciding each original entry and adding missed problems, 4–6 min |
| `pipeline complete: <path>.json` | Success. `<path>.json` is the field's final list |
| `… FAILED: <reason>` | The step returned nothing usable; see below |

If a step fails:

| Failed step | Do |
|---|---|
| `01a_research` | Re-run the whole command once. If it fails again, stop and report. |
| `01b_format` or `02_merge` | Re-run once. If research succeeded and only the merge failed, use `--merge-only` (below). If it fails again, stop and report. |

```bash
python3 -B run_pipeline.py "<Field Name>" <ABBR> --merge-only
```

If the process is still running after 60 minutes with no new `pipeline.log` line, stop it, write a one-line `<run>.STOPPED.md` explaining why, and re-run once.

## Step 2. Archive sources and run machine acceptance

```bash
cd Atlas/research/fields_v5/tools
python3 -B archive_and_accept.py ../<ABBR>/02_merge__gpt-6.1-sol-medium__<time>.json
python3 -B archive_and_accept.py --report
```

Use the exact path from the `pipeline complete` line. Takes 20–40 minutes (the Internet Archive rate-limits saves). Run it in the background. It prints one line per source, then a summary.

For every cited URL it saves under `Atlas/archive/` (private research copies, not for redistribution): the page as served, a local PDF snapshot, the paper's PDF when the page offers one, a legal open copy from Europe PMC (record, abstract, and for open-access papers the full text rendered locally to PDF) when the publisher page fails or no PDF could be made, and a fresh Internet Archive snapshot. The script identifies itself honestly as an archiving tool; sources that block it are queued, not worked around. Every failure is classified and queued in `Atlas/archive/exceptions.json`.

## Step 3. Check the outputs

All of these must be true. If one is not, stop and report it; do not fix it.

- [ ] `pipeline.log` ends with `pipeline complete`.
- [ ] The final list `02_merge__…json` exists, with `….review_process.json` and `….acceptance.json` beside it.
- [ ] `review_process.json` shows `accepted_by.status` = `run`.
- [ ] The acceptance summary has no problem in `rejected` for a reason starting `final list fails its schema`, `identified dependencies point to missing ids` or `placeholder text`. (These mean a pipeline fault, not a source problem.)
- [ ] Every original entry of the field appears once in the final list's `decisions`.

Rejections for content problems and `pending` problems are normal results, not faults. Report them.

## Step 4. Commit

```bash
cd /Users/prakashnarayanan/Documents/2026_Takeoff
git add Atlas/research/fields_v5/<ABBR> Atlas/archive/captures.jsonl Atlas/archive/exceptions.json
git add Atlas/archive/manual_copies.json 2>/dev/null
git status --short Atlas/archive/sources   # must print nothing
git commit -m "atlas: onboard <Field Name> (<ABBR>)

<accepted> accepted, <accepted_with_exceptions> accepted with exceptions,
<pending> pending, <rejected> rejected; <open_exceptions> open exceptions.

Co-Authored-By: <your model name> <noreply@anthropic.com>"
```

Fill the counts from the acceptance summary. Do not push.

## Step 5. Report

Report each field in this form:

```
<ABBR> <Field Name>: <n> problems — <a> accepted, <b> accepted with exceptions, <c> pending, <d> rejected
Originals: <x> covered, <y> added, <z> not added
Open exceptions: <n> (<by queue>); blocking: <n>
Runs: research <run id>, format <run id>, merge <run id>; Grok CLI cost estimate $<n>
Problems found: <anything that failed a check, or "none">
Commit: <hash>
```

## Reference

### Acceptance statuses

| Status | Meaning |
|---|---|
| `accepted` | Every claim has at least one citation whose quote was found in a local copy, and a recognized-as-goal citation has a local PDF and an Internet Archive link. |
| `accepted_with_exceptions` | The recognized-as-goal claim is verified with an Internet Archive link, but either it has only a saved HTML copy (no PDF snapshot yet), or another claim (current state, significance) is only `registered` (DOI or PMID confirms the paper exists, no copy) or `unverified`. |
| `pending` | The recognized-as-goal claim is not yet verified, but its failures are in an access queue that may resolve. |
| `rejected` | Schema failure, unresolved dependency, placeholder text, a content problem, or a recognized-as-goal claim that nothing can fix. |

The recognized-as-goal claim answers "why is this a major item in this field?". Its citation must have a local PDF, an Internet Archive link and a quote verified in a local copy.

### Exception categories and queues

| Category | Detected by | Queue | What happens next |
|---|---|---|---|
| `rate_limited` | HTTP 429 | retry | `--retry` re-attempts |
| `transient` | 5xx, timeout, connection error | retry | `--retry` re-attempts |
| `render_failed` | no PDF of the source: Chrome could not render it (often a bot check) and no paper PDF was found | retry, then manual_copy | Europe PMC is checked by DOI/PMID; for open-access papers its official API supplies the full text, rendered locally to PDF. If nothing is found, it moves to manual_copy. Recorded even when the quote is verified. |
| `archive_failed` | Internet Archive save failed | retry | `--retry` re-attempts |
| `paywalled` | 401, 402, or 403 with a login/subscription page | find_legal_copy | Europe PMC is checked automatically; if that finds nothing usable it moves to manual_copy |
| `bot_blocked` | 403 or a robot-check page | find_legal_copy | as above |
| `archive_refused` | Internet Archive will not save the site | find_legal_copy | as above |
| `dead_link` | 404 or 410 with no Internet Archive copy | dead | Needs a different source; reported only |
| `quote_mismatch` | readable copy, quote not in it | content_problem | Suspect citation; the problem is rejected |
| `unregistered_id` | DOI not at Crossref or PMID not in PubMed | content_problem | Likely fabricated; the problem is rejected |

An exception **blocks acceptance** when it is on the recognized-as-goal claim or is a content problem.

### Working the queues later (operator, not routine)

```bash
cd Atlas/research/fields_v5/tools
python3 -B archive_and_accept.py --report                                  # open exceptions, blocking first
python3 -B archive_and_accept.py ../<ABBR>/02_merge__…json --retry          # re-capture sources in the retry, find_legal_copy and manual_copy queues
python3 -B archive_and_accept.py --attach-pdf <DOI> /path/to/paper.pdf      # attach a copy obtained through legitimate access
python3 -B archive_and_accept.py ../<ABBR>/02_merge__…json                 # re-check after attaching
```

Exceptions that no longer occur on a re-check are marked `resolved` with how they were resolved. Re-checks move problems from `pending` to `accepted` automatically.

### Files per field

`Atlas/research/fields_v5/<ABBR>/` holds every run, named `<step>__<model>-<effort>__<UTC time>.<kind>`; re-runs never overwrite. The newest `02_merge__…json` is the field's current final list.

| File | Contents |
|---|---|
| `01a_research__….prompt.txt`, `.raw.json`, `.notes.md`, `.finished_at` | Research prompt, Grok's full response, its notes, finish time |
| `01b_format__….prompt.txt`, `.schema.json`, `.json`, `.events.jsonl` | Format prompt, schema sent, structured notes, Codex event log |
| `02_merge__….json` | **Final list** |
| `02_merge__….review_process.json` | Model and effort behind each step, and the acceptance summary |
| `02_merge__….acceptance.json` | Per-problem status, reasons, warnings, `selection_evidence`, per-citation results |
| `pipeline.log` | One line per step started, finished, failed or stopped |

### Pipeline files

| Path | Purpose |
|---|---|
| `prompts/01a_research.md`, `01b_format.md`, `02_reconcile_merge.md` | Templated prompts |
| `prompts/*.schema.json` | OpenAI strict schemas; regenerate with `tools/build_schemas.py`, never edit the JSON |
| `tools/run_pipeline.py` | Steps 1a, 1b, 2 |
| `tools/archive_and_accept.py` | Archive, exception queues, machine acceptance |
| `Atlas/archive/captures.jsonl`, `exceptions.json`, `manual_copies.json` | Capture log, exception queue, attached copies (tracked in git) |
| `Atlas/archive/sources/` | Saved copies (private, git-ignored; back up separately) |

### Known behaviour

- Research varies between runs; the same field can produce substantially different lists. Merge decisions on borderline originals can also change between runs.
- Grok CLI cost estimate is about $2.00–2.60 per field. Codex steps run on the ChatGPT plan.
- Grok is used only for unstructured research: its `--json-schema` constrains every intermediate message and produced placeholder drafts. Codex does every schema-bound step.
