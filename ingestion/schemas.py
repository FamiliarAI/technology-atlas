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
