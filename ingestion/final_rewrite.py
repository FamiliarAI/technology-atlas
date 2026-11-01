"""Rewrite validated concept reviews individually, then merge without an LLM."""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import re
import uuid

import jsonschema
from . import schemas
from .field_workflow import concept_headings
from .pipeline import Models, fingerprint, locked, prompt, validate_candidates
from .sources import digest, now, read_json, write_json

SECTIONS = ('concept', 'significance', 'missing_breakthrough', 'current_state', 'completion_criteria', 'related_concepts')
PARAGRAPH = schemas.obj(text=schemas.S, source_urls=schemas.arr(schemas.S))
FINAL_SCHEMA = schemas.obj(id=schemas.S, title=schemas.S,
    **{s: schemas.arr(PARAGRAPH) for s in SECTIONS},
    change_log=schemas.arr(schemas.obj(change=schemas.S, reason=schemas.S)),
    unresolved_issues=schemas.arr(schemas.S))


def make_input(root, candidate, roster, research, reviews, index):
    identifier = candidate['id']
    entry = reviews[identifier]
    if entry['status'] != 'complete':
        raise ValueError(f'{identifier}: validated review required')
    review_path = Path(entry['path']) / 'validated.json'
    review = read_json(review_path)
    if review != entry['review']:
        raise ValueError(f'{identifier}: review receipt and validated file disagree')
    headings = concept_headings(research)
    matches = [(start, end) for found_id, start, end in headings if found_id == identifier]
    if len(matches) != 1:
        raise ValueError(f'{identifier}: research section missing or duplicated')
    start, heading_end = matches[0]
    boundaries = [next_start for _, next_start, _ in headings if next_start > start]
    change_log = re.search(r'^(?:\*\*Change log\*\*|[ ]{0,3}#{1,6}[ \t]+(?:\*\*)?Change log(?:\*\*)?)[ \t]*(?:#+[ \t]*)?$',
                           research[heading_end:], re.M | re.I)
    if change_log:
        boundaries.append(heading_end + change_log.start())
    section = research[start:min(boundaries, default=len(research))]
    urls = {c['url'] for claim in candidate['claims'] for c in claim['citations']}
    urls.update(e['url'] for c in review['evidence_review']['claims'] for e in c['evidence'])
    # Only metadata enters synthesis. Never load review input.json or extracted source bodies.
    sources = [{k: x[k] for k in ('url', 'title', 'status', 'artifacts')} for x in index if x['url'] in urls]
    if {x['url'] for x in sources} != urls:
        raise ValueError(f'{identifier}: source index is incomplete')
    return {'candidate': candidate, 'research': section, 'validated_review': review,
            'source_index': sources, 'concept_roster': roster,
            'provenance': {'research': str(root / 'reconciled-research.md'),
                           'structured_record': str(root / 'reconciled-structured.json'),
                           'review': str(review_path)}}


def normalize_source_aliases(record, payload):
    """Map known retained-artifact URLs to their unambiguous source record."""
    result = copy.deepcopy(record)
    allowed = {s['url'] for s in payload['source_index']}
    aliases = {}
    for source in payload['source_index']:
        for artifact in source['artifacts']:
            url = artifact.get('resolved_url')
            if url:
                aliases.setdefault(url, set()).add(source['url'])
    for section in SECTIONS:
        for paragraph in result[section]:
            paragraph['source_urls'] = list(dict.fromkeys(
                next(iter(aliases[url])) if url not in allowed and len(aliases.get(url, set())) == 1 else url
                for url in paragraph['source_urls']))
    return result


def validate_record(record, payload):
    jsonschema.validate(record, FINAL_SCHEMA)
    if record['id'] != payload['candidate']['id']:
        raise ValueError('Concept identity changed')
    allowed = {s['url'] for s in payload['source_index']}
    if not record['title'].strip():
        raise ValueError('Empty title')
    for section in SECTIONS:
        if not record[section] or any(not p['text'].strip() for p in record[section]):
            raise ValueError(f'Empty section: {section}')
        if any(set(p['source_urls']) - allowed for p in record[section]):
            raise ValueError('Invented source reference')
    return record


def recover_previous(root, payload, key):
    """Reuse only a prior result that passes today's normalization and validation."""
    last_error = None
    for prior in sorted(root.glob('attempts/final-rewrite-*/'+payload['candidate']['id']+'/receipt.json')):
        saved = prior.parent/'result.json'
        if not saved.exists() or read_json(prior).get('input_hash') != key:
            continue
        try:
            raw = read_json(saved)
            validate_record(normalize_source_aliases(raw, payload), payload)
        except (ValueError, KeyError, TypeError, AttributeError, jsonschema.ValidationError) as error:
            last_error = str(error).splitlines()[0][:300]
            continue
        return raw, str(saved), None
    return None, None, last_error


def merge_records(records, expected_ids):
    ids = [r['id'] for r in records]
    if len(ids) != len(set(ids)) or set(ids) != set(expected_ids):
        raise ValueError('Missing, duplicate, or unexpected concept in final merge')
    by_id = {r['id']: r for r in records}
    return [by_id[i] for i in expected_ids]


def render(document):
    lines = ['# '+document['field']['field']+': revolutionary innovations', '',
             'Research agenda: these are proposed breakthroughs, not claims that they have been achieved.', '',
             'Each entry integrates research and review. Remaining evidence gaps are retained.', '', '## Contents', '']
    for item in document['innovations']:
        lines.append(f"- {item['id']}: {item['title']}")
    for item in document['innovations']:
        lines += ['', f"## {item['id']}: {item['title']}", '']
        sources = {s['url']: s for s in item['sources']}
        for section in SECTIONS:
            lines += ['### ' + section.replace('_', ' ').capitalize(), '']
            for paragraph in item[section]:
                citations = ' '.join(f"[{sources[u]['title']}]({u})" for u in paragraph['source_urls'])
                lines += [paragraph['text'] + (' ' + citations if citations else ''), '']
        lines += ['<details>', '<summary>Sources, remaining issues, and revision history</summary>', '']
        for source in item['sources']:
            lines += [f"- [{source['title']}]({source['url']}) — {source['status']}"]
            for artifact in source['artifacts']:
                lines += [f"  - [Saved {artifact['format']}]({artifact['absolute_path']}) — SHA-256 `{artifact['sha256']}`"]
        lines += ['', '**Remaining issues**', ''] + ['- '+s for s in item['unresolved_issues']]
        if not item['unresolved_issues']:
            lines += ['None identified in this synthesis; this does not establish exhaustive evidence coverage.']
        lines += ['', '**Changes**', ''] + ['- '+c['change']+' '+c['reason'] for c in item['change_log']]
        lines += ['', f"[Full validated review]({item['provenance']['review']}) · [Research]({item['provenance']['research']})", '', '</details>', '']
    return '\n'.join(lines)


def run(root, workers=3, prepare_only=False):
    root = Path(root).resolve()
    with locked(root):
        doc = validate_candidates(read_json(root / 'reconciled-candidates.json'))
        research = (root / 'reconciled-research.md').read_text()
        reviews = read_json(root / 'reconciled-reviews.json')
        index = read_json(root / 'source-file-index.json')
        config = read_json(Path(__file__).parent / 'config.json')
        roster = [{'id': p['id'], 'title': p['title']} for p in doc['problems']]
        prepared = []
        for candidate in doc['problems']:
            payload = make_input(root, candidate, roster, research, reviews, index)
            text = prompt('final_rewrite', INPUT=json.dumps(payload, ensure_ascii=False))
            prepared.append((payload, text))
        sizes = [{'id': p['candidate']['id'], 'input_characters': len(t),
                  'estimated_input_tokens': (len(t)+3)//4} for p,t in prepared]
        write_json(root / 'final-rewrite-input-sizes.json', {'estimate_method': 'characters / 4; approximate, not billed usage', 'items': sizes})
        print(json.dumps({'prepared': len(sizes), 'estimated_tokens_total': sum(s['estimated_input_tokens'] for s in sizes),
                          'estimated_tokens_min': min(s['estimated_input_tokens'] for s in sizes),
                          'estimated_tokens_max': max(s['estimated_input_tokens'] for s in sizes)}), flush=True)
        if prepare_only:
            return
        batch = root / 'attempts' / ('final-rewrite-' + uuid.uuid4().hex)
        batch.mkdir()
        write_json(batch/'receipt.json', {'started_at': now(), 'status': 'running', 'workers': workers})
        (root/'current-final-rewrite.txt').write_text(str(batch))
        cache = root/'final-rewrite-cache'; cache.mkdir(exist_ok=True)

        def rewrite(payload, text):
            key = fingerprint({'prompt': text, 'schema': FINAL_SCHEMA, 'model': config['review']})
            path = cache/(key+'.json')
            folder = batch/payload['candidate']['id'];folder.mkdir()
            write_json(folder/'input.json',payload)
            receipt={'status':'running','started_at':now(),'input_hash':key,'model':config['review']}
            write_json(folder/'receipt.json',receipt)
            try:
                if path.exists():
                    cached=read_json(path)
                    if fingerprint(cached['record']) != cached['record_hash']:
                        raise ValueError('Cached rewrite changed')
                    record=cached['record'];receipt['reused']=True
                else:
                    record, recovered_from, prior_error = recover_previous(root, payload, key)
                    if recovered_from:
                        receipt['recovered_from'] = recovered_from
                    if record is None:
                        retry_text = text
                        if prior_error:
                            receipt['prior_validation_error'] = prior_error
                            retry_text += ('\n\nA prior attempt failed output validation: ' + prior_error +
                                           '\nReturn a fresh complete record satisfying the schema and supplied source references.')
                        record=Models(config).call('review',retry_text,FINAL_SCHEMA,folder)
                    write_json(folder/'result.json',record)
                record=normalize_source_aliases(record,payload)
                validate_record(record,payload)
                write_json(path,{'record':record,'record_hash':fingerprint(record)})
                receipt.update(status='complete',finished_at=now());write_json(folder/'receipt.json',receipt)
                print(record['id']+' complete',flush=True)
                return {**record,'sources':payload['source_index'],'provenance':payload['provenance']}
            except BaseException as error:
                receipt.update(status='failed',finished_at=now(),error=str(error));write_json(folder/'receipt.json',receipt)
                raise

        records=[];failures=[]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures={pool.submit(rewrite,p,t):p['candidate']['id'] for p,t in prepared}
            for future in as_completed(futures):
                try: records.append(future.result())
                except Exception as error: failures.append({'id':futures[future],'error':str(error)})
        if failures:
            write_json(batch/'receipt.json',{'status':'failed','finished_at':now(),'failures':failures})
            raise ValueError(f'Final merge withheld: {failures}')
        records=merge_records(records,[p['id'] for p in doc['problems']])
        result={'field':read_json(root/'field.json'), 'created_at':now(), 'innovations':records,
                'original_dispositions':read_json(root/'reconciled-structured.json')['original_dispositions'],
                'reconciliation_change_log':read_json(root/'reconciled-structured.json')['change_log']}
        write_json(batch/'final-innovations.json',result)
        (batch/'final-innovations.md').write_text(render(result))
        write_json(root/'final-innovations.json',result)
        (root/'final-innovations.md').write_text(render(result))
        write_json(batch/'receipt.json',{'status':'complete','finished_at':now(),'count':len(records),
            'output_sha256':digest((root/'final-innovations.json').read_bytes())})
        print('MERGED '+str(len(records))+' innovations: '+str(root/'final-innovations.md'),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory');parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    if not 1 <= args.workers <= 13:parser.error('--workers must be between 1 and 13')
    run(args.directory,args.workers,args.prepare_only)
