# Brief: apply the completed-breakthrough standard to one page

The owner's standard (memory note `completed-breakthrough-standard`, 15 November 2026): a page whose completion test is judged met is reviewed by the top Claude model, then re-judged and dated by the top Codex model (`gpt-6-astra`). Give this file to the reviewing agent with the page ID and its context.

Be economical: Fable quota is limited. Read only what you need, and keep your report short.

## Read first

- AGENTS.md: code style and tests.
- docs/data-reference.md, section 7 ("How to change data").
- The memory notes in /Users/prakashnarayanan/.claude/projects/-Users-prakashnarayanan-Documents-2026-Takeoff/memory/: breakthrough-page-principles.md, atlas-audience.md, completed-breakthrough-standard.md. These are the owner's rules; follow them.
- A good result to copy: `git show --stat 9902de6` and its commit message.
- The proposal format that worked: any atlas/data/page/*-revise-fable-*/proposal.json.
- The page itself: the `page` key of atlas/core/<FIELD>/<ID>.json.

## The standard

The page is judged complete. Check two things:
- The completion test is the real, recognised bar for the breakthrough, stated precisely.
- It has not been narrowed to fit one existing result.

When no outside body sets the bar, set the one the breakthrough's own words imply, with explicit scale.

Rules that apply to every page:
- For mathematics, a proof checked in a proof assistant counts as confirmed.
- When a prize body's ruling or community acceptance is still pending, the result is a claim (shown with †).
- A milestone that needs time to pass, such as "survives two years of examination", must not be met by a fresh claim.

If the test is already right, make no revision and say so; that is a valid outcome. Otherwise revise only what is wrong. Milestone ids are permanent: edit, retire or add, never renumber.

## Steps

1. **Revise, if needed.** Write atlas/data/page/<ID>-revise-fable-<UTC stamp>/proposal.json. The note reads "Rewritten by Claude Fable 5.2 at the owner's request, <date>, under the completed-breakthrough standard", followed by why. Apply it with `python3 -m atlas.page revise <ID> --apply <path>`.
2. **Add new primary sources.** Judge them with Astra:
   `python3 -c "from atlas import page; page.JUDGE['model']='gpt-6-astra'; print(page.add('<ID>', ['URL']))"`
3. **Re-judge, in every case.** Run it once, in the background, and wait for it:
   `python3 -m atlas.page results <ID> --rejudge --model gpt-6-astra --effort high --judge gpt-6-astra --no-commit`
   The judge reads up to 150,000 characters of each source.
4. **Date or undate.**
   - Still complete: `python3 -m atlas.page dates <ID> --model gpt-6-astra --no-commit`
   - No longer complete: delete `page['completed']`. Load the record, delete the key and write it back with atlas.core.write_breakthrough.
5. **Check.** `python3 -m atlas.core check` must pass.
6. **Commit only that record.** `git add <path>`, then `git commit -m ... -- <path>`. End the message with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Do not push and do not deploy. Touch nothing else.

## Report

In under 200 words, cover:
- The old and new completion test, or "unchanged" and why.
- Whether it is complete, with the date.
- Milestone changes.
- Anything not verified.
