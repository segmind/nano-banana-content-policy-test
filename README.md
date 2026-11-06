# Nano Banana content policy tests

Compare explicit content-policy blocks and image returns on Segmind, fal, and
Google Direct through Vertex AI. Every model uses the same included
[violence dataset](datasets/violence/README.md): **15 image edits using 15 color
photographs of theatrical injuries, makeup and training props**.

This is a curated comparison maintained by Segmind. Its selected cases do not
represent either provider's overall production traffic. Lighting accuracy and
other edit-quality judgments are separate from content-policy outcomes.

## Set up your environment

Install Python **3.15.2**, pinned in [.python-version](.python-version), from the
[official Python release](https://www.python.org/downloads/release/python-3152/).
The benchmark uses the standard library, so no third-party packages or
`pip install` step are needed.

On macOS or Linux:

```bash
git clone https://github.com/segmind/nano-banana-content-policy-test.git
cd nano-banana-content-policy-test
python3.15 setup_venv.py
source .venv/bin/activate
python benchmark.py validate --require-assets
python benchmark.py models
python benchmark.py plan --model nano-banana-2
```

`setup_venv.py` checks the pinned interpreter and creates `.venv` with bundled
pip, without downloading packages or contacting providers. It can reuse an
existing matching environment and leaves incompatible directories unchanged.
If `python3.15` is unavailable, install the pinned release first or invoke the
script with its full interpreter path. On Debian-based systems, a missing
`ensurepip` may require the matching Python venv package from the same source
as your interpreter.

On Windows, clone the repository and run these commands from its directory:

```powershell
python setup_venv.py
.\.venv\Scripts\python.exe benchmark.py validate --require-assets
.\.venv\Scripts\python.exe benchmark.py models
.\.venv\Scripts\python.exe benchmark.py plan --model nano-banana-2
```

The setup script prints an activation command for your platform. Activation is
optional: you can use `.venv/bin/python` on macOS/Linux or
`.\.venv\Scripts\python.exe` on Windows in place of `python` in the commands below.
No change to PowerShell execution policy is needed for direct interpreter use.
Keep `.venv` local and recreate it after moving the checkout. See Python's
[venv documentation](https://docs.python.org/3.15/library/venv.html).

## Configure your providers

In a fresh checkout, copy `.env.example` to `.env`, then fill in the providers
you want to compare. Keep an existing `.env` instead of overwriting its keys.
Use `cp .env.example .env` on macOS/Linux or `Copy-Item .env.example .env` in
PowerShell. Both `.env` and `.venv` are ignored by Git.

| Provider | Configuration |
| --- | --- |
| Segmind | `SEGMIND_API_KEY` |
| fal | `FAL_KEY` |
| Google Vertex | `GOOGLE_CLOUD_PROJECT` and `GOOGLE_ACCESS_TOKEN`, or an authenticated `gcloud` CLI for the token |

Only `run --env-file .env` loads the file. Values are literal, without shell
execution or variable expansion; exported values take precedence. Validation,
model listing and planning stay offline and do not inspect credentials.
Missing credentials skip that provider with a recorded reason. Missing keys do
not count as a successful image or a policy failure. With no credentials, a run
is a saved no-op. Present but rejected keys remain authentication errors.

The runner refreshes a `gcloud`-sourced token before each Vertex attempt. An
explicit access token cannot be refreshed and can expire during a long run.

## Choose a model and run

`python benchmark.py models` lists IDs, families, exact endpoints and settings.
The model is independent of the dataset; no dataset argument is needed.

| Model argument | Model family |
| --- | --- |
| `nano-banana` | Gemini 2.5 Flash Image |
| `nano-banana-pro` | Gemini 3 Pro Image |
| `nano-banana-2` | Gemini 3.1 Flash Image |
| `nano-banana-2-lite` | Gemini 3.1 Flash-Lite Image |
| `nano-banana-2.1` | Gemini Nano Banana 2.1 |

First inspect the offline plan and smoke-test a single case:

```bash
python benchmark.py plan --model nano-banana-2 --repeats 3
python benchmark.py run --model nano-banana-2 --env-file .env --case C002N --repeats 1
```

Check the saved outcome before proceeding. A policy block is a measured content
outcome; an authentication or invalid-request error needs resolving first.
Then run all 15 cases, or choose an explicit subset:

```bash
python benchmark.py run --model nano-banana-2 --env-file .env --repeats 3
python benchmark.py run --model nano-banana-pro --env-file .env --case C002N --case C003N --repeats 3
```

Replace the model ID to compare another model. Legacy `--profile` is an alias for
`--model`; use either flag, not both. Each invocation creates a new evidence
directory and records the model profile, dataset version, prompt/reference
hashes, provider settings and account labels. Different models are never pooled
or silently substituted. See [provider contracts](docs/providers.md).

Fifteen cases with three repetitions schedule 45 attempts per active provider:
90 for Segmind and fal, or 135 if all three providers are configured. Planning
shows the potential count; execution records actual active and skipped providers.
Requests can incur charges. There are no automatic inference retries. An
accepted request can complete or be charged after a timeout; inspect its saved
submission ID before deliberately repeating it.

Account modes default to `unknown`. Supply confirmed labels with
`--account-mode segmind=standard --account-mode fal=standard`, or the appropriate
`approved` label for an independently confirmed configuration. Labels do not
change safety settings. Optional `--concurrency 4` bounds active attempts at four.

## Read the results

```bash
python benchmark.py summarize runs/<run-id>
```

The primary comparison is **explicit policy-block rate**, with image return,
operational failures and unresolved outcomes reported separately. A generic
HTTP 422 or an empty response is not proof of a policy block. Returned images do
not have to meet a lighting-fidelity score to count as image returns.

`run.json` stores the exact case and model snapshots; `results.jsonl` retains each
completed attempt; `submissions.jsonl` preserves accepted IDs before polling;
`outputs/` holds saved images. Credentials, account balances, inline image bytes
and signed response URLs are redacted from diagnostics. Evidence stays in ignored
`runs/` until intentionally reviewed and published.

Optional visual review records editing and preservation separately. It can flag
removed content, but does not establish that moderation caused the change:

```bash
python benchmark.py review runs/<run-id> --image outputs/C002N-fal-r1-1.png --edit-success success --preservation preserved --reviewer "Reviewer name or agent" --notes "Describe the visible content."
```

Reviews are append-only and bound to the output checksum. Optional
`comparison.py` strict task-completion analysis includes edit fidelity; do not
use that score as a policy-block rate. See [methodology](docs/methodology.md).

## Maintain the dataset

The only maintained benchmark is [datasets/violence](datasets/violence/README.md).
Add new violence cases and documented references there. Update its version,
review the input/provenance changes, and deliberately replace its freeze before
collecting new comparison results. The freeze must cover every reference, even
for a selected-case smoke test. Earlier definitions remain in Git history;
historical run snapshots and results keep their original identities and hashes.

All 15 references are included and ready. Their [asset manifest](datasets/violence/assets.json)
records exact credits, CC0 or U.S.-only government-work claims, transformations,
SHA-256 values and immutable public URLs. Other jurisdictions, likeness, privacy,
publicity and trademark rights are not claimed cleared. Military imagery carries
its nonendorsement notice. Third-party reference images are not covered by the
repository's MIT license.

The [source review catalog](reference-candidates/violence-harvest-v1/README.md)
is provenance and sourcing material, not another runnable benchmark dataset.
`candidate_review.py` validates that catalog and builds a local review gallery.

## Verify locally

```bash
python -m unittest discover -s tests -v
```

Automated tests make no paid provider requests and require no credentials.
The code, original prompts and documentation are [MIT licensed](LICENSE).
