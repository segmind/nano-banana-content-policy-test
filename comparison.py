#!/usr/bin/env python3
"""Compare saved model runs with the same image-return rule for both providers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import benchmark as b


REPORT_PROVIDERS = ('fal', 'segmind')
PASS_DEFINITION = 'A case passes when every planned repetition returns a saved, valid image without an output-fetch error. Visual edit-quality scores do not affect this count.'


def read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise b.BenchmarkError(f'{path.name} must contain JSON objects')
    return rows


def measure_run(directory: Path) -> dict:
    """Validate the planned trial matrix and count cases, never visual judgments."""
    run = b.read_json(directory/'run.json')
    snapshots = run.get('cases_snapshot')
    repeats = run.get('repeats')
    providers = run.get('providers')
    if not isinstance(snapshots, list) or not snapshots or type(repeats) is not int or repeats < 1:
        raise b.BenchmarkError('A run needs case snapshots and a positive repetition count')
    if not isinstance(providers, list) or len(set(providers)) != len(providers) or any(p not in b.PROVIDERS for p in providers):
        raise b.BenchmarkError('Run providers must be unique supported provider IDs')
    cases = {}
    for case in snapshots:
        if not isinstance(case, dict) or not isinstance(case.get('id'), str) or case['id'] in cases:
            raise b.BenchmarkError('Case snapshots must have unique IDs')
        if not isinstance(case.get('prompt'), str) or not isinstance(case.get('reference_asset_ids'), list):
            raise b.BenchmarkError('Case snapshots need prompts and reference IDs')
        cases[case['id']] = case
    planned = len(cases)*repeats*len(providers)
    if run.get('case_ids') != list(cases) or run.get('cases') != len(cases) or run.get('planned_inference_requests') != planned:
        raise b.BenchmarkError('Case snapshots must match the declared case and attempt plan')
    profile = run.get('profile')
    if not isinstance(profile, dict) or not isinstance(profile.get('id'), str) or not isinstance(profile.get('family'), str) or profile.get('id') != run.get('profile_id') or profile.get('family') != run.get('model_family'):
        raise b.BenchmarkError('Run model identity must match its saved profile')
    if not isinstance(profile.get('providers'), dict) or any(not isinstance(profile['providers'].get(p), dict) for p in providers):
        raise b.BenchmarkError('Saved model profile must define each active provider')
    for field in ('dataset_sha256', 'assets_manifest_sha256', 'profile_sha256'):
        if not b.SHA_PATTERN.fullmatch(str(run.get(field, ''))):
            raise b.BenchmarkError(f'Run needs a valid {field}')
    if b.digest(b.canonical_bytes(profile)) != run['profile_sha256']:
        raise b.BenchmarkError('Saved model profile checksum changed')
    observed = {}
    reference_hashes = {}
    for row in read_records(directory/'results.jsonl'):
        key = row.get('case_id'), row.get('provider'), row.get('repeat')
        if key[0] not in cases or key[1] not in providers or type(key[2]) is not int or not 1 <= key[2] <= repeats or key in observed:
            raise b.BenchmarkError('Unexpected or duplicate attempt in results')
        case = cases[key[0]]
        config = profile['providers'][key[1]]
        expected_model = config['edit_model' if case['reference_asset_ids'] else 'text_model'] if key[1] == 'fal' else config['model']
        if row.get('run_id') != run.get('run_id') or row.get('profile_id') != profile['id'] or row.get('model_family') != profile['family'] or row.get('requested_model') != expected_model:
            raise b.BenchmarkError('Attempt model does not match its saved profile')
        if row.get('prompt_sha256') != b.digest(case['prompt'].encode('utf-8')):
            raise b.BenchmarkError('Attempt prompt does not match its case snapshot')
        refs = row.get('reference_assets')
        if not isinstance(refs, list) or any(not isinstance(ref, dict) for ref in refs) or [ref.get('id') for ref in refs] != case['reference_asset_ids']:
            raise b.BenchmarkError('Attempt references do not match its case snapshot')
        for ref in refs:
            sha = ref.get('sha256')
            valid_hash = b.SHA_PATTERN.fullmatch(str(sha))
            changed_hash = ref['id'] in reference_hashes and reference_hashes[ref['id']] != sha
            if not valid_hash or changed_hash:
                raise b.BenchmarkError('Reference bytes differ between attempts')
            reference_hashes[ref['id']] = sha
        outputs = row.get('outputs')
        if not isinstance(outputs, list) or row.get('image_count') != len(outputs):
            raise b.BenchmarkError('Saved output count does not match the attempt')
        for output in outputs:
            if not isinstance(output, dict):
                raise b.BenchmarkError('Saved output must name a path and checksum')
            path = b.asset_path(directory, output['path'])
            if path.stat().st_size > b.MAX_BYTES:
                raise b.BenchmarkError('Saved output exceeds the image size limit')
            data = path.read_bytes()
            if b.digest(data) != output['sha256']:
                raise b.BenchmarkError('Output checksum changed after generation')
            b.image_type(data)
        outcome = row.get('outcome')
        if outcome == 'image_returned' and not outputs:
            raise b.BenchmarkError('Image-returned attempt has no saved image')
        if outcome == 'image_returned' and (type(row.get('http_status')) is not int or not 200 <= row['http_status'] < 300):
            raise b.BenchmarkError('Image-returned attempt needs a successful HTTP response')
        if outcome == 'policy_refusal':
            if outputs or b.classify_response(row.get('http_status', 422), row.get('response'), 0) != 'policy_refusal':
                raise b.BenchmarkError('Policy refusal needs structured native policy evidence and no returned image')
        observed[key] = {'outcome': outcome, 'image_returned': outcome == 'image_returned' and not row.get('output_errors'),
                         'other': outcome not in ('image_returned', 'policy_refusal') or bool(row.get('output_errors'))}
    metrics = {}
    for provider in REPORT_PROVIDERS:
        case_results = []
        for case_id, case in cases.items():
            trials = [observed[(case_id, provider, repeat)] for repeat in range(1, repeats+1) if (case_id, provider, repeat) in observed]
            returned = sum(trial['image_returned'] for trial in trials)
            blocked = sum(trial['outcome'] == 'policy_refusal' for trial in trials)
            other = sum(trial['other'] for trial in trials)
            passed = len(trials) == repeats and returned == repeats
            state = 'passed' if passed else 'blocked' if blocked else 'incomplete' if trials else 'not_run'
            case_results.append({'id': case_id, 'title': case.get('title', case_id), 'status': state,
                                 'images_returned': returned, 'policy_blocks': blocked, 'other_outcomes': other,
                                 'recorded_attempts': len(trials), 'planned_attempts': repeats})
        trials = [value for (case_id, p, repeat), value in observed.items() if p == provider]
        active = provider in providers
        complete = active and run.get('status') == 'complete' and len(trials) == len(cases)*repeats and not any(trial['other'] for trial in trials)
        passed = sum(case['status'] == 'passed' for case in case_results) if active else None
        metrics[provider] = {'status': 'complete' if complete else 'incomplete' if active else 'not_run',
                             'cases_passed': passed, 'total_cases': len(cases), 'pass_rate': passed/len(cases) if complete else None,
                             'images_returned': sum(trial['image_returned'] for trial in trials),
                             'policy_blocks': sum(trial['outcome'] == 'policy_refusal' for trial in trials),
                             'other_outcomes': sum(trial['other'] for trial in trials),
                             'recorded_attempts': len(trials), 'planned_attempts': len(cases)*repeats if active else 0,
                             'account_mode': run.get('account_modes', {}).get(provider, 'unknown'),
                             'cases': case_results}
    selection = run.get('dataset_selection')
    if selection is None:
        # Older runs store case snapshots but no selection metadata. Attribute
        # bundled cases only when their full snapshots match the current set.
        current = b.read_json(b.ROOT/'datasets/violence/cases.json')
        bundled = {case['id']: case for case in current['cases']}
        if all(bundled.get(case_id) == case for case_id, case in cases.items()):
            selection = current.get('selection')
    return {'run_id': run['run_id'], 'model_id': profile['id'], 'model_label': profile.get('label', profile['id']),
            'model_family': profile['family'], 'profile_sha256': run['profile_sha256'],
            'dataset_id': run['dataset_id'], 'dataset_version': run.get('dataset_version', 'unknown'),
            'dataset_sha256': run['dataset_sha256'], 'assets_manifest_sha256': run['assets_manifest_sha256'],
            'cases_sha256': b.digest(b.canonical_bytes(sorted(snapshots, key=lambda case: case['id']))),
            'reference_hashes': reference_hashes, 'total_cases': len(cases), 'repeats': repeats,
            'outcome_selected_dataset': selection.get('outcome_selected') if isinstance(selection, dict) else None,
            'started_at': run.get('started_at'), 'finished_at': run.get('finished_at'), 'providers': metrics}


def compare_runs(directories: list[Path]) -> dict:
    """Combine model/provider rows only when the dataset and repetition plan match."""
    if not directories:
        raise b.BenchmarkError('Supply at least one saved run directory')
    reports = [measure_run(directory) for directory in directories]
    first = reports[0]
    identity = ('dataset_sha256', 'assets_manifest_sha256', 'cases_sha256', 'repeats')
    rows, profiles, references, models = {}, {}, {}, {}
    for report in reports:
        if any(report[field] != first[field] for field in identity):
            raise b.BenchmarkError('Comparison runs must use the same dataset, case set and planned repetitions; report different sets separately')
        model = report['model_id']
        if model in profiles and profiles[model] != report['profile_sha256']:
            raise b.BenchmarkError('The same model must use the same profile settings across providers')
        profiles[model] = report['profile_sha256']
        models[model] = report
        for ref, sha in report['reference_hashes'].items():
            if ref in references and references[ref] != sha:
                raise b.BenchmarkError('Comparison runs used different reference bytes')
            references[ref] = sha
        for provider, metrics in report['providers'].items():
            if metrics['status'] == 'not_run':
                continue
            key = model, provider
            if key in rows:
                raise b.BenchmarkError('More than one run supplies the same model/provider; choose one explicit comparison run')
            rows[key] = {**metrics, 'model_id': model, 'model': report['model_label'], 'provider': provider,
                         'run_id': report['run_id'], 'profile_sha256': report['profile_sha256'],
                         'run_started_at': report['started_at'], 'run_finished_at': report['finished_at']}
    for model, report in models.items():
        for provider in REPORT_PROVIDERS:
            rows.setdefault((model, provider), {**report['providers'][provider], 'model_id': model,
                            'model': report['model_label'], 'provider': provider, 'run_id': None,
                            'profile_sha256': report['profile_sha256'], 'run_started_at': None, 'run_finished_at': None})
    selected = [report['outcome_selected_dataset'] for report in reports]
    scope = 'These curated cases were selected using earlier provider outcomes. Equal scoring does not make this dataset a representative or independently selected sample.' if any(value is True for value in selected) else 'Dataset selection was not independently verified. Results describe these cases, not overall provider performance.'
    return {'schema_version': '1.0', 'generated_at': b.utc_now(), 'dataset_id': first['dataset_id'],
            'dataset_version': first['dataset_version'], 'dataset_sha256': first['dataset_sha256'],
            'assets_manifest_sha256': first['assets_manifest_sha256'], 'cases_sha256': first['cases_sha256'],
            'reference_hashes': references, 'total_cases': first['total_cases'],
            'repeats': first['repeats'], 'pass_definition': PASS_DEFINITION, 'dataset_scope': scope,
            'rows': [rows[key] for key in sorted(rows)]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('summarize', 'report'))
    parser.add_argument('runs', nargs='+', type=Path, help='One explicit saved run per model/provider; all runs must use the same cases')
    parser.add_argument('--output', type=Path, help='HTML report path, e.g. runs/comparison/index.html')
    args = parser.parse_args(argv)
    try:
        report = compare_runs(args.runs)
        if args.command == 'report':
            if args.output is None or args.output.suffix.lower() != '.html':
                raise b.BenchmarkError('report requires --output with an .html filename')
            from comparison_report import write_report
            write_report(report, args.output)
            print(json.dumps({'report': str(args.output), 'data': str(args.output.with_suffix('.data.json'))}, indent=2))
        else:
            print(json.dumps(report, indent=2))
        return 0
    except (b.BenchmarkError, ValueError, OSError, KeyError, TypeError) as error:
        print(f'Error: {error}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
