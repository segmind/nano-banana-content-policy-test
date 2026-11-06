#!/usr/bin/env python3
"""Measure strict paired edit success and disclose outcome-based case selection."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path

import benchmark as b


def read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise b.BenchmarkError(f'{path.name} must contain JSON objects')
    return rows


def measure_run(directory: Path) -> dict:
    """Count a pass only when every returned image has both required visual scores."""
    run = b.read_json(directory / 'run.json')
    if run.get('review_schema') not in b.INDEPENDENT_REVIEW_SCHEMAS:
        raise b.BenchmarkError('Strict edit comparison requires independent visual axes')
    cases = {case['id']: case for case in run['cases_snapshot']}
    if any(case['mode'] != 'image_edit' or len(case['reference_asset_ids']) != 1 for case in cases.values()):
        raise b.BenchmarkError('Paired selection requires single-reference image edits')
    providers = run['providers']
    expected = {(case, provider, repeat) for case in cases for provider in providers for repeat in range(1, run['repeats'] + 1)}
    reviews = {(row['path'], row['sha256']): row for row in read_records(directory / 'reviews.jsonl')}
    observed = set()
    attempts = []
    for row in read_records(directory / 'results.jsonl'):
        key = row['case_id'], row['provider'], row['repeat']
        if key not in expected or key in observed:
            raise b.BenchmarkError('Unexpected or duplicate attempt in results')
        observed.add(key)
        outputs = row.get('outputs', [])
        if row['outcome'] == 'image_returned' and not outputs:
            raise b.BenchmarkError('Image-returned attempt has no saved image')
        passed = row['outcome'] == 'image_returned' and not row.get('output_errors')
        pending = False
        for output in outputs:
            data = b.asset_path(directory, output['path']).read_bytes()
            if b.digest(data) != output['sha256']:
                raise b.BenchmarkError('Output checksum changed after generation')
            b.image_type(data)
            review = reviews.get((output['path'], output['sha256']), {})
            edit, preservation = review.get('edit_success'), review.get('preservation')
            if edit not in ('success', 'partial', 'failed') or preservation not in ('preserved', 'partial', 'not_preserved'):
                pending = True
            passed = passed and edit == 'success' and preservation == 'preserved'
        attempts.append({'case_id': key[0], 'provider': key[1], 'repeat': key[2],
                         'outcome': row['outcome'], 'pass': None if pending else bool(passed),
                         'output_fetch_error': bool(row.get('output_errors')),
                         'image_returned': row['outcome'] == 'image_returned'})
    metrics = {}
    for provider in providers:
        rows = [row for row in attempts if row['provider'] == provider]
        pending = sum(row['pass'] is None for row in rows)
        counts = Counter(row['outcome'] for row in rows)
        passes = sum(row['pass'] is True for row in rows)
        operational = sum(count for outcome, count in counts.items() if outcome not in ('image_returned', 'policy_refusal', 'recitation_refusal'))
        operational += sum(row['outcome'] == 'image_returned' and row['output_fetch_error'] for row in rows)
        metrics[provider] = {'attempts': len(rows), 'passes': passes, 'unreviewed_attempts': pending,
                             'image_returns': counts['image_returned'], 'policy_refusals': counts['policy_refusal'],
                             'operational_or_unresolved': operational, 'outcomes': dict(counts),
                             'strict_pass_rate': passes / len(rows) if rows and not pending else None,
                             'image_return_rate': counts['image_returned'] / len(rows) if rows else None}
    rows = []
    for case_id, case in cases.items():
        counts = {'case_id': case_id, 'reference_id': case['reference_asset_ids'][0], 'repeats': run['repeats']}
        for provider in ('segmind', 'fal'):
            trials = [row for row in attempts if row['case_id'] == case_id and row['provider'] == provider]
            counts[provider + '_passes'] = sum(row['pass'] is True for row in trials) if len(trials) == run['repeats'] and all(row['pass'] is not None for row in trials) else None
        rows.append(counts)
    paired = all(provider in providers for provider in ('segmind', 'fal'))
    complete = run['status'] == 'complete' and observed == expected and bool(providers)
    reviewed = complete and all(row['pass'] is not None for row in attempts)
    gap = metrics['segmind']['strict_pass_rate'] - metrics['fal']['strict_pass_rate'] if paired and reviewed else None
    return {'run_id': run['run_id'], 'dataset_id': run['dataset_id'], 'dataset_sha256': run['dataset_sha256'],
            'profile_sha256': run['profile_sha256'], 'complete': complete, 'visual_review_complete': reviewed,
            'skipped_providers': run.get('skipped_providers', {}), 'providers': metrics,
            'segmind_minus_fal': gap, 'cases': rows,
            'selection_ready': paired and reviewed and all(metrics[p]['operational_or_unresolved'] == 0 for p in ('segmind', 'fal')),
            'pass_definition': 'Image returned; every returned image has edit_success=success and preservation=preserved. All recorded attempts form the denominator; availability and policy outcomes remain separate.'}


def select_cases(rows: list[dict], size: int = 15, max_fal_rate: float = 0.5) -> dict:
    """Maximize the pilot gap under a cap, with one case per reference."""
    if type(size) is not int or size <= 0:
        raise ValueError('size must be a positive integer')
    if type(max_fal_rate) not in (int, float) or not math.isfinite(max_fal_rate) or not 0 <= max_fal_rate <= 1:
        raise ValueError('max_fal_rate must be finite and between zero and one')
    if not isinstance(rows, list) or not rows:
        raise ValueError('rows must be a nonempty list')
    grouped = defaultdict(list)
    ids = set()
    repeats = None
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('each row must be an object')
        for field in ('case_id', 'reference_id'):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f'{field} must be nonempty text')
        if row['case_id'] in ids:
            raise ValueError('duplicate case ID')
        ids.add(row['case_id'])
        count = row.get('repeats')
        if type(count) is not int or count <= 0 or repeats is not None and count != repeats:
            raise ValueError('all rows need the same positive repeat count')
        repeats = count
        for field in ('segmind_passes', 'fal_passes'):
            if type(row.get(field)) is not int or not 0 <= row[field] <= count:
                raise ValueError(f'invalid or unreviewed {field}')
        grouped[row['reference_id']].append(row)
    if len(grouped) < size:
        raise ValueError('not enough distinct references')
    # For a fixed count and fal total, retain the greatest Segmind total and
    # smallest ID tuple. Processing whole reference groups prevents duplicates.
    states = {(0, 0): (0, ())}
    for options in grouped.values():
        updated = dict(states)
        for (count, fal), (segmind, chosen) in states.items():
            if count >= size:
                continue
            for row in options:
                key = count + 1, fal + row['fal_passes']
                value = segmind + row['segmind_passes'], tuple(sorted((*chosen, row['case_id'])))
                old = updated.get(key)
                if old is None or (-value[0], value[1]) < (-old[0], old[1]):
                    updated[key] = value
        states = updated
    denominator = size * repeats
    feasible = [(segmind - fal, segmind, chosen, fal) for (count, fal), (segmind, chosen) in states.items()
                if count == size and fal / denominator <= max_fal_rate]
    if not feasible:
        raise ValueError('No selection satisfies the fal cap; do not relax it silently')
    delta, segmind, chosen, fal = min(feasible, key=lambda item: (-item[0], -item[1], item[2]))
    return {'case_ids': list(chosen), 'segmind_passes': segmind, 'fal_passes': fal, 'attempts_per_provider': denominator,
            'segmind_rate': segmind / denominator, 'fal_rate': fal / denominator, 'gap': delta / denominator,
            'selection_basis': 'Outcome-selected exploratory pilot; confirm with fresh repetitions. Not a general provider ranking.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('summarize', 'select'))
    parser.add_argument('run', type=Path)
    parser.add_argument('--size', type=int, default=15)
    parser.add_argument('--max-fal-rate', type=float, default=0.5)
    args = parser.parse_args(argv)
    try:
        report = measure_run(args.run)
        if args.command == 'select':
            if not report['selection_ready']:
                raise b.BenchmarkError('Selection requires complete, reviewed paired outcomes without operational or unresolved failures')
            report['selection'] = select_cases(report['cases'], args.size, args.max_fal_rate)
        print(json.dumps(report, indent=2))
        return 0
    except (b.BenchmarkError, ValueError, OSError, KeyError) as error:
        print(f'Error: {error}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
