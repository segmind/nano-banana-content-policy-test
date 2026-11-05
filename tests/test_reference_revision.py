"""Offline regression checks for frozen references and independent visual scores."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import benchmark as b
from test_benchmark import PNG, FakeClient, sample_assets


class ReferenceRevisionTests(unittest.TestCase):
    def test_design_counts_and_neutral_prompt_are_enforced(self):
        directory = b.ROOT / 'datasets/violence-v2'
        dataset, assets = b.load_dataset(directory)
        self.assertEqual(dataset['cases'][0]['prompt'], dataset['cases'][1]['prompt'])
        for change in ('prompt', 'violence', 'checks'):
            changed_dataset, changed_assets = copy.deepcopy(dataset), copy.deepcopy(assets)
            if change == 'prompt':
                changed_dataset['cases'][1]['prompt'] += ' Alter the pose.'
            elif change == 'violence':
                changed_assets['assets'][1]['contains_existing_violence'] = False
            else:
                changed_dataset['cases'][0]['edit_checks'] = []
            with self.subTest(change=change), self.assertRaises(b.BenchmarkError):
                b.validate_reference_design(changed_dataset, changed_assets)

    def make_frozen(self, root):
        assets = sample_assets(root)
        dataset = {'dataset_id': 'fixture', 'version': '1', 'freeze_required': True,
                   'cases': [{'id': 'V01', 'mode': 'image_edit', 'reference_asset_ids': ['R01']}]}
        b.freeze_dataset(root, dataset, assets, 'Test reviewer')
        return dataset, assets

    def test_freeze_rejects_prompt_provenance_and_image_changes(self):
        for change in ('prompt', 'provenance', 'image'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                dataset, assets = self.make_frozen(root)
                self.assertIsNotNone(b.verify_freeze(root, dataset, assets))
                if change == 'prompt':
                    dataset['cases'][0]['prompt'] = 'Changed'
                elif change == 'provenance':
                    assets['assets'][0]['creator'] = 'Changed'
                else:
                    (root / 'assets/R01.png').write_bytes(b'Changed')
                with self.assertRaises(b.BenchmarkError):
                    b.verify_freeze(root, dataset, assets)

    def test_freeze_requires_all_assets_and_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset, assets = self.make_frozen(root)
            with self.assertRaises(b.BenchmarkError):
                b.freeze_dataset(root, dataset, assets, 'Another reviewer')
            assets['assets'][0]['status'] = 'pending'
            with self.assertRaises(b.BenchmarkError):
                b.freeze_dataset(root / 'other', dataset, assets, 'Test reviewer')

    def test_run_blocks_before_network_when_freeze_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = sample_assets(root)
            case = {'id': 'V01', 'mode': 'image_edit', 'prompt': 'Relight', 'reference_asset_ids': ['R01']}
            dataset = {'dataset_id': 'fixture', 'version': '1', 'freeze_required': True, 'cases': [case]}
            args = argparse.Namespace(dataset=root, account_mode=None, timeout=10, repeats=1, output=root / 'run')
            client = FakeClient()
            with patch.dict('os.environ', {'FAL_KEY': 'test-only'}, clear=True), self.assertRaises(b.BenchmarkError):
                b.run_benchmark(args, dataset, assets, [case], b.load_profile('nano-banana-pro'), ['fal'], client)
            self.assertEqual(client.calls, [])
            self.assertFalse((root / 'run').exists())

    def test_independent_scores_do_not_infer_from_legacy_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'outputs').mkdir()
            (root / 'outputs/image.png').write_bytes(PNG)
            run = {'run_id': 'axes', 'dataset_id': 'fixture', 'providers': ['fal'], 'case_ids': ['V01'],
                   'status': 'complete', 'planned_inference_requests': 1, 'review_schema': 'independent_axes_v1',
                   'cases_snapshot': [{'id': 'V01', 'mode': 'image_edit'}]}
            (root / 'run.json').write_text(json.dumps(run))
            output = {'path': 'outputs/image.png', 'sha256': b.digest(PNG)}
            b.append_jsonl(root / 'results.jsonl', {'provider': 'fal', 'case_id': 'V01', 'outcome': 'image_returned', 'outputs': [output]})
            b.append_jsonl(root / 'reviews.jsonl', {**output, 'label': 'instruction_followed'})
            summary = b.summarize(root)
            self.assertFalse(summary['visual_review_complete'])
            self.assertEqual(summary['independent_review_counts']['fal']['edit_success']['unreviewed'], 1)
            args = argparse.Namespace(run_directory=root, image=output['path'], label=None, reviewer='Agent review',
                                      notes='Lighting unchanged; bruise retained.', edit_success='failed', preservation='preserved')
            b.review_output(args)
            summary = b.summarize(root)
            self.assertTrue(summary['visual_review_complete'])
            self.assertEqual(summary['provider_metrics']['fal']['image_return_rate_on_recorded_attempts'], 1)
            self.assertEqual(summary['provider_metrics']['fal']['edit_success']['rate_on_reviewed_applicable_images'], 0)
            self.assertEqual(summary['provider_metrics']['fal']['preservation']['rate_on_reviewed_applicable_images'], 1)
            args.preservation = 'not_applicable'
            with self.assertRaises(b.BenchmarkError):
                b.review_output(args)
            self.assertEqual(len((root / 'reviews.jsonl').read_text().splitlines()), 2)


if __name__ == '__main__':
    unittest.main()
