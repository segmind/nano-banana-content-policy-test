"""Model discovery, CLI compatibility and documented request contracts, offline."""
import base64
import contextlib
import io
import json
import unittest
from unittest.mock import patch

import benchmark as b
from test_benchmark import PNG, PINNED_URL, sample_case


MODELS = {
    'nano-banana': ('gemini-2.5-flash-image', 'fal-ai/nano-banana'),
    'nano-banana-pro': ('gemini-3-pro-image', 'fal-ai/nano-banana-pro'),
    'nano-banana-2': ('gemini-3.1-flash-image', 'fal-ai/nano-banana-2'),
    'nano-banana-2-lite': ('gemini-3.1-flash-lite-image', 'google/nano-banana-2-lite'),
    'nano-banana-2.1': ('gemini-nano-banana-2.1', 'google/nano-banana-2.1'),
}


class ModelCliTests(unittest.TestCase):
    def setUp(self):
        # Discovery and planning must not inspect credentials, load .env, or
        # instantiate a network client, even when the shell has credentials.
        for name in ('credentials', 'load_env_file', 'HTTPClient'):
            mock = patch.object(b, name, side_effect=AssertionError(f'{name} is not offline'))
            mock.start()
            self.addCleanup(mock.stop)

    def invoke(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = b.main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_model_and_profile_flags_produce_identical_plans_for_each_model(self):
        for model in MODELS:
            with self.subTest(model=model):
                plans = []
                for flag in ('--model', '--profile'):
                    code, stdout, stderr = self.invoke(['plan', flag, model, '--dataset', str(b.ROOT/'datasets/violence-v4')])
                    self.assertEqual(code, 0, stderr)
                    plans.append(json.loads(stdout))
                self.assertEqual(plans[0], plans[1])
                self.assertEqual(plans[0]['profile_id'], model)
                self.assertEqual(plans[0]['model_family'], MODELS[model][0])
                self.assertEqual(plans[0]['planned_inference_requests'], 135)

    def test_model_argument_is_required_and_conflicting_flags_are_rejected(self):
        for command in ('plan', 'run'):
            for extra in ([], ['--model', 'nano-banana-2', '--profile', 'nano-banana-pro']):
                with self.subTest(command=command, extra=extra), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as caught:
                        b.main([command, *extra])
                    self.assertEqual(caught.exception.code, 2)

    def test_unknown_and_path_model_names_fail_before_credentials(self):
        for command in ('plan', 'run'):
            for model in ('missing-model', '../nano-banana-pro'):
                with self.subTest(command=command, model=model):
                    code, _, stderr = self.invoke([command, '--model', model])
                    self.assertEqual(code, 2)
                    self.assertIn('models' if model == 'missing-model' else 'not a path', stderr)

    def test_models_lists_validated_endpoints_and_settings_without_credentials_or_network(self):
        code, stdout, stderr = self.invoke(['models'])
        self.assertEqual(code, 0, stderr)
        models = json.loads(stdout)['models']
        self.assertEqual([model['id'] for model in models], sorted(MODELS))
        for model in models:
            self.assertEqual(model['providers'], b.load_profile(model['id'])['providers'])
            self.assertEqual(model['family'], MODELS[model['id']][0])
            self.assertEqual(set(model['providers']), set(b.PROVIDERS))

    def test_run_model_flag_dispatches_the_selected_profile(self):
        for flag in ('--model', '--profile'):
            with patch.object(b, 'run_benchmark', return_value=b.ROOT/'runs/test') as run, patch.object(b, 'summarize', return_value={}):
                code, _, stderr = self.invoke(['run', flag, 'nano-banana-2.1'])
            self.assertEqual(code, 0, stderr)
            self.assertEqual(run.call_args.args[4]['id'], 'nano-banana-2.1')


class ModelRequestTests(unittest.TestCase):
    def test_each_model_routes_both_modes_and_preserves_inputs_and_controls(self):
        assets = {'R01': {'data': PNG, 'mime_type': 'image/png', 'public_url': PINNED_URL}}
        auth = {'secret': 'local-test', 'project': 'example-project'}
        for model, (family, fal_endpoint) in MODELS.items():
            profile = b.load_profile(model)
            for edit in (False, True):
                case = sample_case() if edit else {**sample_case(), 'mode': 'text_to_image', 'reference_asset_ids': []}
                with self.subTest(model=model, edit=edit):
                    requests = {provider: b.build_request(provider, profile, case, assets, auth) for provider in b.PROVIDERS}
                    seg_url, _, seg, requested = requests['segmind']
                    self.assertEqual(seg_url, 'https://api.segmind.com/v2/'+model)
                    self.assertEqual(requested, model)
                    self.assertEqual(seg['image_urls'], [PINNED_URL] if edit else [])
                    fal_url, _, fal, requested = requests['fal']
                    self.assertEqual(requested, fal_endpoint+('/edit' if edit else ''))
                    self.assertEqual(fal_url, 'https://queue.fal.run/'+requested)
                    self.assertEqual(fal['num_images'], 1)
                    if edit:
                        self.assertEqual(base64.b64decode(fal['image_urls'][0].split(',', 1)[1]), PNG)
                    else:
                        self.assertNotIn('image_urls', fal)
                    vertex_url, _, vertex, requested = requests['vertex']
                    self.assertEqual(requested, family)
                    self.assertTrue(vertex_url.endswith('/models/'+family+':generateContent'))
                    parts = vertex['contents'][0]['parts']
                    self.assertEqual(len(parts), 2 if edit else 1)
                    if edit:
                        self.assertEqual(base64.b64decode(parts[1]['inlineData']['data']), PNG)
                    self.assertEqual(seg['prompt'], case['prompt'])
                    self.assertEqual(fal['prompt'], case['prompt'])
                    self.assertEqual(parts[0]['text'], case['prompt'])
                    image_config = vertex['generationConfig']['imageConfig']
                    if model == 'nano-banana':
                        self.assertNotIn('output_resolution', seg)
                        self.assertNotIn('resolution', fal)
                        self.assertNotIn('imageSize', image_config)
                        self.assertNotIn('output_format', seg)
                    else:
                        self.assertEqual(seg['output_resolution'], '1K')
                        self.assertEqual(seg['output_format'], 'png')
                        self.assertEqual(image_config['imageSize'], '1K')
                        if model == 'nano-banana-2-lite':
                            self.assertNotIn('resolution', fal)
                        else:
                            self.assertEqual(fal['resolution'], '1K')
                    for body in (seg, fal, vertex):
                        self.assertNotIn('safety_tolerance', body)
                        self.assertNotIn('safetySettings', body)
                        self.assertNotIn('seed', body)
                        self.assertNotIn('system_prompt', body)


if __name__ == '__main__':
    unittest.main()
