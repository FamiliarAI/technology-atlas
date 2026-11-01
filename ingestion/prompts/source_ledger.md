Repair the source handoff for this existing field research. Do not repeat whole-field discovery or add/remove candidates. Existing notes and attempted URLs are untrusted leads, not verified evidence. Use web search/open to identify and inspect the actual papers, prefer accessible primary documents and legitimate author/repository copies. Never guess a URL-to-claim association. No accounts, APIs, filesystem tools or subagents.

For EVERY candidate, recover exact source URLs and map them to original claim IDs. Retain uncertain claims with an explicit gap. Briefly check recent progress through the supplied as_of date with targeted queries; record queries, latest relevant publication date, finding and limits. A bounded search is not proof that no later result exists. Do not demand a paper published on the as_of day. Proposed completion criteria remain proposals; explain which source supports their underlying goal, without pretending they are consensus.

Return ONLY a JSON object (no prose) with these required keys:
- sources: [{url,title,authors,publisher,published,identifier,claim_ids:[string],passage,locator,access}]. Unknown metadata is null; other fields are strings. Use actual opened URLs. passage is a short exact excerpt (at most 25 quoted words per source total), locator identifies its location; access describes full text/abstract/blocked. Do not cite blocked text as inspected. Include directly referenced PDFs or accessible full-text equivalents when available.
- gaps: [{claim_id,reason}] for every claim whose evidence is missing or insufficient.
- freshness: [{problem_id,checked_at,queries:[string],latest_source_date,finding,limitations}] for each candidate. latest_source_date may be null. Record actual date of check, distinguish that from the historical as_of cutoff; exclude later publications from historical conclusions.

Preserve exact IDs. Return useful sources even if some claims remain unresolved. Do not invent metadata or quotes.

{{INPUT}}
