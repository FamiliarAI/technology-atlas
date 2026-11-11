"""Share images: python3 -m atlas.share OUT_DIR [--only ID ...] [--base URL] [--force].

Screenshots the site's own share cards (atlas/web/src/Share.jsx, routes /share/...) at
1200x630 into OUT_DIR/share/: <ID>.png for each breakthrough, field-<ID>.png for each field
and default.png. Needs a running server with the built site (python3 -m atlas.server) and
Playwright with Chromium; this is a build-time tool and the only part of atlas that needs
packages outside the standard library. Pillow, when installed, makes the files smaller.

A card is skipped when its file is newer than both the database and the built site, unless
--force. Pass OUT_DIR to python3 -m atlas.export --share.
"""

import argparse
import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from .server import SITE
from .store import DB

BASE = 'http://127.0.0.1:8765'
WIDTH = 1200
HEIGHT = 630
TIMEOUT = 30_000  # ms for one card to load, fit and signal


def cards(catalog, only=()):
    """(route, file name) for every card, or for the IDs in only ('default', QUA, QUA-01)."""
    items = [('/share/default', 'default.png')]
    items += [(f'/share/field/{f["id"]}', f'field-{f["id"]}.png') for f in catalog['fields']]
    items += [(f'/share/b/{b["id"]}', f'{b["id"]}.png') for b in catalog['breakthroughs']]
    if not only:
        return items
    wanted = {
        f'{key}.png' if key == 'default' or '-' in key else f'field-{key}.png' for key in only
    }
    known = {name for _, name in items}
    unknown = sorted(wanted - known)
    if unknown:
        raise SystemExit('Unknown ID: ' + ', '.join(name[:-4] for name in unknown))
    return [item for item in items if item[1] in wanted]


def compress(png):
    """A smaller PNG: a 256-colour palette when Pillow is installed, else the bytes unchanged."""
    try:
        from PIL import Image
    except ImportError:
        return png
    image = Image.open(io.BytesIO(png)).convert('RGB')
    # Octree keeps the plate's faint stars and gradients in a third of median cut's bytes.
    small = image.quantize(colors=256, method=Image.Quantize.FASTOCTREE)
    out = io.BytesIO()
    small.save(out, 'PNG', optimize=True)
    data = out.getvalue()
    return data if len(data) < len(png) else png


def write(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(data)
    os.replace(temporary, path)


async def shoot(base, jobs, folder, workers):
    from playwright.async_api import async_playwright

    queue = asyncio.Queue()
    for job in jobs:
        queue.put_nowait(job)
    failures = []
    sizes = []

    async def worker(browser):
        page = await browser.new_page(
            viewport={'width': WIDTH, 'height': HEIGHT}, device_scale_factor=1
        )
        while not queue.empty():
            route, name = queue.get_nowait()
            try:
                await page.goto(base + route, wait_until='load')
                await page.wait_for_selector(
                    'html[data-share-ready], html[data-share-error]', timeout=TIMEOUT
                )
                error = await page.evaluate('document.documentElement.dataset.shareError || ""')
                if error:
                    failures.append((name, error))
                    continue
                png = await page.screenshot(
                    type='png', clip=dict(x=0, y=0, width=WIDTH, height=HEIGHT)
                )
                data = compress(png)
                write(folder / name, data)
                sizes.append((len(data), name))
            except Exception as error:  # one card failing must not stop the others
                failures.append((name, str(error).splitlines()[0]))
        await page.close()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            await asyncio.gather(*(worker(browser) for _ in range(workers)))
        finally:
            await browser.close()
    return sizes, failures


def main(argv=None):
    parser = argparse.ArgumentParser(description='Screenshot the share cards.')
    parser.add_argument('out', type=Path, help='folder; images go to OUT/share/')
    parser.add_argument(
        '--only', nargs='+', default=[], help='default, field IDs or breakthrough IDs'
    )
    parser.add_argument('--base', default=BASE, help=f'running atlas.server (default {BASE})')
    parser.add_argument('--force', action='store_true', help='redo cards that are up to date')
    parser.add_argument('--workers', type=int, default=4, help='pages at once (default 4)')
    parser.add_argument('--db', type=Path, default=DB, help='database the server reads')
    args = parser.parse_args(argv)
    try:
        import playwright.async_api  # noqa: F401
    except ImportError:
        raise SystemExit(
            'atlas.share needs Playwright: pip install playwright && playwright install chromium'
        )
    base = args.base.rstrip('/')
    try:
        with urlopen(base + '/data/catalog.json', timeout=10) as res:
            catalog = json.load(res)
    except OSError as error:
        raise SystemExit(f'No atlas server at {base} ({error}); run python3 -m atlas.server')
    folder = args.out / 'share'
    folder.mkdir(parents=True, exist_ok=True)
    stamps = [
        path.stat().st_mtime for path in [Path(args.db), SITE / 'index.html'] if path.exists()
    ]
    newest = max(stamps, default=time.time())
    jobs = []
    current = 0
    for route, name in cards(catalog, args.only):
        path = folder / name
        if not args.force and path.exists() and path.stat().st_mtime > newest:
            current += 1
            continue
        jobs.append((route, name))
    started = time.time()
    sizes, failures = (
        asyncio.run(shoot(base, jobs, folder, max(1, args.workers))) if jobs else ([], [])
    )
    took = time.time() - started
    total = sum(size for size, _ in sizes)
    print(f'{len(sizes)} cards written to {folder} in {took:.0f} s, {current} up to date')
    if sizes:
        largest = ', '.join(f'{name} {size // 1024} KB' for size, name in sorted(sizes)[-3:][::-1])
        print(
            f'{total // 1024} KB in all, {total // len(sizes) // 1024} KB each on average; largest {largest}'
        )
    for name, error in failures:
        print(f'failed {name}: {error}', file=sys.stderr)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
