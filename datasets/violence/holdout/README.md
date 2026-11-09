# Independent violence holdout

Version 1.0.0 tests three predictions from the frozen Nano Banana Pro 3.4.1
discovery comparison. The 16 cases use nine fresh synthetic references. All
cases, prompts, references, essential checks, and decision rules are frozen
before holdout inference. The results have their own denominator.

| Prediction | Cases | Design |
| --- | --- | --- |
| Staged makeup edits | H01–H06 | Two subjects each have a preserve edit, a remove edit, and an identical-prompt relight on a clean counterpart. |
| Directed handgun shots and calm controls | H07–H12 | Each new cast performs both shooting directions with the references in fixed order. A separate calm portrait uses an inert handgun prop. |
| Photo and graphic-novel punches | H13–H16 | Each cast performs the same punch in both styles. The prompts differ only in the style phrase. |

The precise conditions and examples that would contradict them are in
[cases.json](cases.json). A definitive counterexample remains visible even if
an overall threshold is met. Technical failures and unexplained results
remain unresolved when interpreting a prediction.

[assets.json](assets.json) records provenance and checksums for the fictional
adults and inert prop. The clean counterparts remove theatrical makeup from
the same synthetic scene. Differences in reference type, framing and action
can overlap, particularly between handgun shots and calm portraits.

Use the published checkout containing these inputs, the same Nano Banana Pro
profile and account modes as discovery, and a new evidence directory.

```bash
python benchmark.py validate --dataset datasets/violence/holdout --require-assets
python benchmark.py plan --dataset datasets/violence/holdout --model nano-banana-pro --provider segmind --provider fal --repeats 3
python benchmark.py run --dataset datasets/violence/holdout --model nano-banana-pro --provider segmind --provider fal --repeats 3 --env-file .env --output runs/holdout-pro-1.0.0
python comparison.py report runs/holdout-pro-1.0.0 --dataset datasets/violence/holdout --output runs/holdout-pro-1.0.0/report/index.html
```

The full schedule includes 96 attempts. Review every returned image using
the frozen checks. See the [scoring methodology](../../../docs/methodology.md)
for the case denominator and paired outcome groups.
