"""Prepare and audit every catalog skin in an isolated cache. Never apply to Dota."""
import argparse
import json
from pathlib import Path
import shutil
import time

from cosmetic_schema import wearable_aliases
from manager import PORTRAIT_MODELS
from skin_builder import SkinBuilder
from steam_discovery import normalize_game_path
from tide_trial import sha
from vpk_lab import read_single


def audit(game, cache, output, seed_zips=None):
    builder = SkinBuilder(normalize_game_path(game), cache)
    jobs = [(hero, row['id'], row) for hero, row in builder.manifest['heroes'].items()]
    jobs += [('tidehunter', skin, row) for skin, row in builder.manifest['styles'].items()]
    results = []
    for hero, skin, recipe in jobs:
        started = time.monotonic()
        try:
            if seed_zips:
                name = Path(recipe['source_zip']).name
                candidate = next((p for p in (seed_zips/name, seed_zips/'heroes'/name) if p.is_file()), None)
                if candidate:
                    if sha(candidate.read_bytes()) != recipe['source_sha256']:
                        raise ValueError('Seed ZIP differs from the pinned source hash.')
                    target = builder.cache/(recipe['source_sha256']+'.zip')
                    if not target.exists(): shutil.copyfile(candidate, target)
            report = builder.prepare(hero, skin)
            resources = read_single(report['package_path'])
            if 'scripts/items/items_game.txt' in resources:
                raise ValueError('The read-only item schema was incorrectly included in the package.')
            available = set(resources)
            for _path, (_base, indexed) in builder._official_context(): available.update(indexed)
            body = PORTRAIT_MODELS.get(hero)
            aliases, _ = wearable_aliases(builder._schema_cache[1], hero, available,
                                         body+'_c' if body else None, builder._schema_cache[2])
            compatibility = report['loadout_compatibility']
            verified = 0
            for source, target in aliases.items():
                if source in compatibility['missing_item_models']: continue
                if resources[source] != resources[target]:
                    raise ValueError('Wearable does not match its canonical slot: '+source)
                verified += 1
            result = {'hero': hero, 'skin': skin, 'ok': True, 'resources': len(resources),
                      'bytes': Path(report['package_path']).stat().st_size, 'sha256': report['sha256'],
                      'verified_model_aliases': verified, 'compatibility': compatibility,
                      'visual_validation': 'not_verified_in_game'}
            print(f'PASS {hero}:{skin}: {verified} model aliases; {result["bytes"]:,} bytes; {time.monotonic()-started:.1f}s', flush=True)
        except Exception as exc:
            result = {'hero': hero, 'skin': skin, 'ok': False, 'error': str(exc)}
            print(f'FAIL {hero}:{skin}: {exc}', flush=True)
        results.append(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2, ensure_ascii=False), 'utf-8')
    print(f'TOTAL {len(results)}; PASS {sum(r["ok"] for r in results)}', flush=True)
    return all(row['ok'] for row in results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--cache', type=Path, default=Path('build/audit-cache'))
    parser.add_argument('--output', type=Path, default=Path('build/catalog-audit.json'))
    parser.add_argument('--seed-zips', type=Path)
    args = parser.parse_args()
    raise SystemExit(0 if audit(args.game, args.cache, args.output, args.seed_zips) else 1)
