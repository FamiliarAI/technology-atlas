"""The static v1 site: python3 -m atlas.export OUT.

Writes the built site (atlas/static/site), the data files of the site's data contract and one
HTML file per route, each with its own title, description and share tags. Share images are
made separately by python3 -m atlas.share and copied in with --share. Saved source copies and
working documents are not exported. The result is served from a site root by any static host:
/atlas loads atlas/index.html, /b/QUA-01 loads b/QUA-01/index.html.
"""

import argparse
import html
import re
import shutil
from pathlib import Path

from .server import SITE
from .store import DB, connect, cut, encode, site_files

MARKER = '.atlas-export'
NAME = 'Technology Atlas'
HOME_TITLE = 'Technology Atlas · A map of the breakthroughs worth working towards'
HOME_TEXT = (
    'A map of the breakthroughs worth working towards, and the milestones that tell us how '
    'close we are.'
)
PAGES = {
    'about': (
        'Method',
        'How breakthroughs are researched, what a milestone means, how sources are saved and '
        'quotes checked, which models did what, and how to challenge an entry.',
    ),
}
# Tags a route sets for itself; the built index.html's own copies are removed first.
OWN_TAGS = re.compile(
    r'\s*<meta\s+(?:name="description"|property="og:[^"]*"|name="twitter:[^"]*")[^>]*>',
    re.DOTALL,
)
TITLE = re.compile(r'<title>.*?</title>', re.DOTALL)


def routes(files):
    """(route, title, description, share image name) for every page.

    The share cards (/share/...) are not pages: they exist to be screenshotted by atlas.share,
    so they get no HTML file here and mark themselves noindex in the browser.
    """
    catalog = files['catalog.json']
    total = len(catalog['breakthroughs'])
    yield '/', HOME_TITLE, HOME_TEXT, 'default'
    yield (
        '/atlas',
        'The atlas · ' + NAME,
        f'A star chart of {total} proposed breakthroughs in {len(catalog["fields"])} fields, '
        'each with milestones that say how we will know it has happened.',
        'default',
    )
    for route, (eyebrow, text) in PAGES.items():
        yield '/' + route, f'{eyebrow} · {NAME}', text, 'default'
    for field in catalog['fields']:
        count = field['breakthroughs']
        noun = 'breakthrough' if count == 1 else 'breakthroughs'
        yield (
            '/field/' + field['id'],
            f'{field["name"]} · {NAME}',
            f'{count} proposed {noun} in {field["name"]}, each with milestones that say how we '
            'will know it has happened.',
            'field-' + field['id'],
        )
    for item in catalog['breakthroughs']:
        record = files[f'b/{item["id"]}.json']
        brief = record.get('brief') or {}
        summary = record['concept'][0]['text'] if record['concept'] else record['title']
        if brief.get('possible'):
            summary = brief['possible'][0]
        yield (
            '/b/' + item['id'],
            f'{brief.get("title") or item["title"]} · {item["id"]} · {NAME}',
            cut(summary, 200),
            item['id'],
        )


def page(index, route, title, description, image, base_url=''):
    """The built index.html with the route's own head tags."""
    base = base_url.rstrip('/')
    tags = {
        'description': description,
        'og:type': 'article' if route.startswith('/b/') else 'website',
        'og:site_name': NAME,
        'og:title': title,
        'og:description': description,
        'og:image': f'{base}/share/{image}.png',
        'twitter:card': 'summary_large_image',
    }
    if base:
        tags['og:url'] = base + route
    lines = []
    for key, value in tags.items():
        attribute = 'property' if key.startswith('og:') else 'name'
        lines.append(f'<meta {attribute}="{key}" content="{html.escape(value)}" />')
    head = OWN_TAGS.sub('', index)
    head = TITLE.sub(lambda match: f'<title>{html.escape(title)}</title>', head, count=1)
    block = '\n    '.join(lines)
    return head.replace('</head>', f'  {block}\n  </head>', 1)


def target(out, route):
    if route == '/':
        return out / 'index.html'
    return out / route.strip('/') / 'index.html'


def prepare(out):
    """An empty folder, or one a previous export wrote; anything else is refused."""
    if out.exists():
        if not out.is_dir():
            raise SystemExit(f'{out} is not a folder')
        if any(out.iterdir()) and not (out / MARKER).is_file():
            raise SystemExit(f'{out} is not empty and was not written by atlas.export')
        shutil.rmtree(out)
    out.mkdir(parents=True)


def share_images(source):
    """The PNG files in source/share (as atlas.share writes them), or in source itself."""
    source = Path(source)
    folder = source / 'share' if (source / 'share').is_dir() else source
    if not folder.is_dir():
        raise SystemExit(f'{source} is not a folder of share images')
    return sorted(folder.glob('*.png'))


def export(out, db_path=DB, site=SITE, base_url='', share=None):
    """Write the static site to out, with share images from share (an atlas.share folder).

    Returns {'pages': n, 'data': n, 'bytes': {...}, 'images': n, 'without_image': [route, ...]}.
    """
    out = Path(out)
    site = Path(site)
    index_path = site / 'index.html'
    if not index_path.is_file():
        raise SystemExit('Site not built; run npm run build in atlas/web')
    if not Path(db_path).exists():
        raise SystemExit('Run python3 -m atlas.store first')
    images = share_images(share) if share else []
    prepare(out)
    shutil.copytree(site, out, dirs_exist_ok=True)
    if images:
        (out / 'share').mkdir(exist_ok=True)
        for path in images:
            shutil.copyfile(path, out / 'share' / path.name)
    db = connect(db_path)
    try:
        files = dict(site_files(db))
    finally:
        db.close()
    sizes = {}
    for name, value in files.items():
        path = out / 'data' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        data = encode(value)
        path.write_bytes(data)
        sizes[name] = len(data)
    index = index_path.read_text()
    pages = 0
    without = []
    for route, title, description, image in routes(files):
        if not (out / 'share' / f'{image}.png').is_file():
            without.append(route)
        path = target(out, route)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(page(index, route, title, description, image, base_url))
        pages += 1
    missing = page(index, '/404', 'Off the chart · ' + NAME, HOME_TEXT, 'default', base_url)
    (out / '404.html').write_text(missing)
    (out / MARKER).write_text('Written by python3 -m atlas.export; safe to replace.\n')
    return {
        'pages': pages,
        'data': len(files),
        'bytes': sizes,
        'images': len(images),
        'without_image': without,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Export the static v1 site.')
    parser.add_argument('out', type=Path, help='output folder (empty, or an earlier export)')
    parser.add_argument('--db', type=Path, default=DB)
    parser.add_argument(
        '--base-url',
        default='',
        help='public origin such as https://example.org, for absolute share URLs',
    )
    parser.add_argument(
        '--share',
        type=Path,
        help='folder written by python3 -m atlas.share; its share/*.png are copied in',
    )
    args = parser.parse_args(argv)
    result = export(args.out, args.db, base_url=args.base_url, share=args.share)
    sizes = result['bytes']
    largest = {
        kind: max((size, name) for name, size in sizes.items() if name.startswith(kind))
        for kind in ['field/', 'b/']
    }
    print(
        f'{result["pages"]} pages, {result["data"]} data files in {args.out}; '
        f'catalog {sizes["catalog.json"]} B, search {sizes["search.json"]} B, '
        f'largest field {largest["field/"][1]} {largest["field/"][0]} B, '
        f'largest breakthrough {largest["b/"][1]} {largest["b/"][0]} B'
    )
    without = result['without_image']
    line = f'{result["images"]} share images; {len(without)} pages have none'
    if without:
        line += ': ' + ', '.join(without[:8]) + (' …' if len(without) > 8 else '')
    print(line)


if __name__ == '__main__':
    main()
