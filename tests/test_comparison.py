"""Protect strict scoring and case selection against missing or biased evidence."""
import argparse
import copy
import itertools
import json
from pathlib import Path
import random
import tempfile
import threading
import unittest
from unittest.mock import patch

import benchmark as b
import comparison as c
from test_benchmark import PNG, FakeClient, sample_assets


class SelectionTests(unittest.TestCase):
    def test_optimizer_matches_exhaustive_selection(self):
        rng = random.Random(12)
        for _ in range(25):
            rows = [{'case_id': f'C{i}{variant}', 'reference_id': str(i), 'repeats': 3,
                     'segmind_passes': rng.randrange(4), 'fal_passes': rng.randrange(4)}
                    for i in range(4) for variant in 'NP']
            options = []
            for selected in itertools.combinations(rows, 3):
                fal = sum(row['fal_passes'] for row in selected)
                if len({row['reference_id'] for row in selected}) != 3 or fal / 9 > .5:
                    continue
                segmind = sum(row['segmind_passes'] for row in selected)
                options.append((segmind - fal, segmind, tuple(sorted(row['case_id'] for row in selected)), fal))
            if not options:
                with self.assertRaises(ValueError):
                    c.select_cases(rows, 3, .5)
                continue
            best = min(options, key=lambda row: (-row[0], -row[1], row[2]))
            actual = c.select_cases(rows, 3, .5)
            self.assertEqual((actual['segmind_passes'] - actual['fal_passes'], actual['segmind_passes'], tuple(actual['case_ids']), actual['fal_passes']), best)
            self.assertEqual(c.select_cases(list(reversed(rows)), 3, .5), actual)

    def test_ties_and_cap_are_not_silently_relaxed(self):
        rows = [{'case_id': name, 'reference_id': name, 'segmind_passes': s, 'fal_passes': f, 'repeats': 3}
                for name, s, f in [('a', 2, 1), ('b', 3, 2), ('c', 2, 1)]]
        self.assertEqual(c.select_cases(rows, 1, 1)['case_ids'], ['b'])
        self.assertEqual(c.select_cases(rows, 1, .5)['case_ids'], ['a'])
        with self.assertRaises(ValueError):
            c.select_cases(rows, 3, 0)

    def test_invalid_and_unreviewed_counts_are_rejected(self):
        row = {'case_id': 'a', 'reference_id': 'r', 'segmind_passes': 1, 'fal_passes': 0, 'repeats': 1}
        for rows, size, cap in [([], 1, .5), ([row], True, .5), ([row], 1, float('nan')),
                                ([row], 1, True), ([row, row], 1, .5), ([row], 2, .5),
                                ([{**row, 'fal_passes': None}], 1, .5),
                                ([{**row, 'segmind_passes': 2}], 1, .5),
                                ([row, {**row, 'case_id': 'b', 'repeats': 2}], 1, .5)]:
            with self.subTest(rows=rows, size=size, cap=cap), self.assertRaises(ValueError):
                c.select_cases(rows, size, cap)


class MeasurementTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'outputs').mkdir()
        self.run = {'run_id': 'test', 'dataset_id': 'test', 'dataset_sha256': 'd'*64, 'profile_sha256': 'e'*64,
                    'review_schema': 'independent_axes_v2', 'repeats': 1, 'providers': ['segmind', 'fal'],
                    'status': 'complete', 'cases_snapshot': [{'id': 'C01', 'mode': 'image_edit', 'reference_asset_ids': ['A01']}]}
        (self.root / 'run.json').write_text(json.dumps(self.run))
        self.rows = []
        for provider in self.run['providers']:
            output = {'path': f'outputs/{provider}.png', 'sha256': b.digest(PNG)}
            (self.root / output['path']).write_bytes(PNG)
            self.rows.append({'case_id': 'C01', 'provider': provider, 'repeat': 1, 'outcome': 'image_returned', 'outputs': [output]})
        self.save()

    def save(self):
        (self.root / 'results.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in self.rows))

    def review(self, provider, edit='success', preservation='preserved'):
        output = next(row['outputs'][0] for row in self.rows if row['provider'] == provider)
        b.append_jsonl(self.root / 'reviews.jsonl', {**output, 'edit_success': edit, 'preservation': preservation})

    def test_returned_images_are_not_automatic_passes_and_axes_are_separate(self):
        self.review('segmind')
        report = c.measure_run(self.root)
        self.assertIsNone(report['segmind_minus_fal'])
        self.assertFalse(report['selection_ready'])
        self.assertEqual(report['providers']['fal']['unreviewed_attempts'], 1)
        self.review('fal', edit='failed')
        report = c.measure_run(self.root)
        self.assertEqual(report['providers']['fal']['image_return_rate'], 1)
        self.assertEqual(report['providers']['fal']['strict_pass_rate'], 0)
        self.assertEqual(report['segmind_minus_fal'], 1)
        self.assertTrue(report['selection_ready'])
        self.review('fal', preservation='partial')
        self.assertEqual(c.measure_run(self.root)['providers']['fal']['strict_pass_rate'], 0)
        self.review('fal')
        self.assertEqual(c.measure_run(self.root)['segmind_minus_fal'], 0)

    def test_missing_attempts_and_operational_errors_block_selection(self):
        self.review('segmind')
        self.rows[1].update(outcome='authentication_error', outputs=[])
        self.save()
        report = c.measure_run(self.root)
        self.assertEqual(report['providers']['fal']['operational_or_unresolved'], 1)
        self.assertFalse(report['selection_ready'])
        self.rows.pop()
        self.save()
        self.assertFalse(c.measure_run(self.root)['complete'])

    def test_policy_failure_is_counted_without_a_fake_visual_review(self):
        self.review('segmind')
        self.rows[1].update(outcome='policy_refusal', outputs=[])
        self.save()
        report = c.measure_run(self.root)
        self.assertTrue(report['selection_ready'])
        self.assertEqual(report['providers']['fal']['policy_refusals'], 1)
        self.assertEqual(report['providers']['fal']['strict_pass_rate'], 0)

    def test_partial_download_failure_cannot_be_used_for_selection(self):
        self.review('segmind');self.review('fal')
        self.rows[1]['output_errors'] = ['Second output could not be downloaded']
        self.save()
        report = c.measure_run(self.root)
        self.assertEqual(report['providers']['fal']['strict_pass_rate'], 0)
        self.assertEqual(report['providers']['fal']['operational_or_unresolved'], 1)
        self.assertFalse(report['selection_ready'])

    def test_duplicate_attempt_or_changed_bytes_are_rejected(self):
        self.rows.append(copy.deepcopy(self.rows[0]))
        self.save()
        with self.assertRaises(b.BenchmarkError):
            c.measure_run(self.root)
        self.rows.pop();self.save()
        (self.root / 'outputs/fal.png').write_bytes(b'changed')
        with self.assertRaises(b.BenchmarkError):
            c.measure_run(self.root)


class PhotoDesignAndConcurrencyTests(unittest.TestCase):
    def test_single_builtin_dataset_is_ready_frozen_and_used_by_default(self):
        directories = [path.name for path in (b.ROOT/'datasets').iterdir() if path.is_dir()]
        self.assertEqual(directories, ['violence'])
        directory = b.ROOT/'datasets/violence'
        dataset, assets = b.load_dataset(directory)
        self.assertEqual(dataset['dataset_id'], 'violence')
        self.assertEqual(len(dataset['cases']), 15)
        self.assertEqual(len({case['reference_asset_ids'][0] for case in dataset['cases']}), 15)
        b.verify_freeze(directory, dataset, assets)
        commands = {'validate': [], 'freeze': ['--reviewer', 'Test'],
                    'plan': ['--model', 'nano-banana-2'], 'run': ['--model', 'nano-banana-2']}
        for command, options in commands.items():
            self.assertEqual(b.parser().parse_args([command, *options]).dataset, directory)

    def test_design_counts_are_explicit_and_legacy_schema_stays_strict(self):
        dataset, assets = b.load_dataset(b.ROOT / 'datasets/violence')
        self.assertEqual(len(dataset['cases']), 15)
        self.assertEqual(len(assets['assets']), 15)
        changed = copy.deepcopy(dataset)
        changed['design']['cases'] = 14
        with self.assertRaises(b.BenchmarkError):
            b.validate_reference_design(changed, assets)
        changed = copy.deepcopy(dataset)
        changed['review_schema'] = 'independent_axes_v1'
        with self.assertRaises(b.BenchmarkError):
            b.validate_reference_design(changed, assets)

    def test_concurrent_attempts_are_bounded_and_recorded_exactly_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); assets = sample_assets(root)
            cases = [{'id': f'C{i}', 'mode': 'image_edit', 'reference_asset_ids': ['R01'], 'prompt': 'Relight'} for i in range(4)]
            dataset = {'dataset_id': 'test', 'version': '1', 'cases': cases}
            args = argparse.Namespace(dataset=root, output=root/'run', repeats=1, timeout=5, account_mode=None, concurrency=2)
            barrier = threading.Barrier(2)
            def attempt(client, provider, profile, case, *unused):
                barrier.wait(timeout=2)
                return {'case_id': case['id'], 'provider': provider, 'repeat': 1, 'outcome': 'policy_refusal', 'outputs': []}
            with patch.dict('os.environ', {'FAL_KEY':'local-test'}, clear=True), patch.object(b, 'run_attempt', side_effect=attempt):
                out = b.run_benchmark(args, dataset, assets, cases, b.load_profile('nano-banana-pro'), ['fal'], FakeClient())
            rows = c.read_records(out/'results.jsonl')
            self.assertEqual(len(rows), 4)
            self.assertEqual(len({row['case_id'] for row in rows}), 4)
            self.assertEqual(b.read_json(out/'run.json')['concurrency'], 2)
            self.assertTrue(b.summarize(out)['complete'])

    def test_invalid_concurrency_stops_before_credential_or_network_access(self):
        with patch.object(b, 'credentials') as credentials:
            for concurrency in (0, 5, True):
                with self.assertRaises(b.BenchmarkError):
                    b.run_benchmark(argparse.Namespace(concurrency=concurrency), {}, {}, [], {}, [])
            credentials.assert_not_called()

    def test_worker_failure_does_not_dispatch_the_remaining_paid_schedule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); assets = sample_assets(root)
            cases = [{'id': f'C{i}', 'mode': 'image_edit', 'reference_asset_ids': ['R01'], 'prompt': 'Relight'} for i in range(8)]
            dataset = {'dataset_id': 'test', 'version': '1', 'cases': cases}
            args = argparse.Namespace(dataset=root, output=root/'run', repeats=1, timeout=5, account_mode=None, concurrency=2)
            with patch.dict('os.environ', {'FAL_KEY':'local-test'}, clear=True), patch.object(b, 'run_attempt', side_effect=b.BenchmarkError('stop')) as attempt:
                with self.assertRaisesRegex(b.BenchmarkError, 'stop'):
                    b.run_benchmark(args, dataset, assets, cases, b.load_profile('nano-banana-pro'), ['fal'], FakeClient())
            self.assertLessEqual(attempt.call_count, 2)
            self.assertEqual(b.read_json(root/'run/run.json')['status'], 'interrupted')


if __name__ == '__main__':
    unittest.main()
