"""Small strict output schemas; semantic checks live in pipeline.py."""

S = {'type': 'string'}
N = {'type': ['string', 'null']}
B = {'type': 'boolean'}


def obj(**props):
    return {
        'type': 'object',
        'properties': props,
        'required': list(props),
        'additionalProperties': False,
    }


def arr(item):
    return {'type': 'array', 'items': item}


def enum(*values):
    return {'type': 'string', 'enum': list(values)}


STATUS = enum('supported', 'contradicted', 'unresolved')
CANDIDATES = obj(
    problems=arr(
        obj(
            id=S,
            title=S,
            claims=arr(
                obj(
                    id=S,
                    kind=enum('problem', 'completion', 'current_state', 'significance'),
                    text=S,
                    citations=arr(obj(url=S, quote=S, locator=S)),
                )
            ),
        )
    ),
    sources=arr(obj(url=S, title=S, authors=N, publisher=N, published=N, identifier=N)),
    excluded=arr(obj(title=S, reason=S)),
    coverage_note=S,
)
REVIEW = obj(
    claims=arr(
        obj(
            id=S,
            status=STATUS,
            reason=S,
            evidence=arr(
                obj(
                    url=S,
                    artifact=S,
                    identity_verified=B,
                    completeness=enum('full', 'partial', 'unknown'),
                    relation=STATUS,
                    passage=S,
                    locator=S,
                    reason=S,
                )
            ),
        )
    )
)
FIELD_REVIEW = obj(assessment=S, duplicates=arr(S), gaps=arr(S), next_actions=arr(S))

# Explicit URL handoff and a bounded recent-literature check, not a completeness guarantee.
LEDGER = obj(
    sources=arr(
        obj(
            url=S,
            title=S,
            authors=N,
            publisher=N,
            published=N,
            identifier=N,
            claim_ids=arr(S),
            passage=S,
            locator=S,
            access=S,
        )
    ),
    gaps=arr(obj(claim_id=S, reason=S)),
    freshness=arr(
        obj(
            problem_id=S,
            checked_at=S,
            queries=arr(S),
            latest_source_date=N,
            finding=S,
            limitations=S,
        )
    ),
)
