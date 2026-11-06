# How to run and interpret the comparison

This is a small, deliberately selected collection of violence-related image tasks. It can show reproducible differences on the listed cases. It cannot estimate a provider's overall production failure rate or establish that every rejected request should have been allowed.

## Freeze the inputs before collecting comparison results

Use the same dataset commit, exact prompt strings, reference image bytes, model family, and supported output settings across providers. Every reference has a SHA-256, provenance, redistribution license, and a fixed public URL. Prepare any size reduction once before freezing the files. Do not resize or retouch separately for one provider.

The single maintained dataset is `datasets/violence`: 15 image edits with 15 staged-photo references. Model selection does not change the dataset. Exact bytes, source credits, rights evidence and preparation steps are recorded in its asset manifest. Reference preparation is separate from tested-provider inference and does not count as a benchmark outcome. Update the dataset version and freeze in this same directory when extending it; older definitions remain in Git history and saved run snapshots.

Run each case three times per provider, including failures. This schedules 135 attempts for three providers. These are 15 tasks with repeated observations, not 135 independently sampled tasks. Results from an original Nano Banana profile and a Pro profile are separate comparisons.

Do not edit a prompt after a failure and overwrite its result. Give a revised case a new version or ID and retain the old result. Repeated requests are planned trials, not a loop that keeps trying until an image appears.

## Compare the actual service configuration

The first configuration uses each endpoint's default safety behavior, with no safety override or prompt rewrite. Record the account mode as `standard`, `approved`, or `unknown`. If accounts have different approved configurations, describe that difference beside the results. A default API key comparison and an approved studio configuration comparison answer different questions.

The profiles explicitly separate Nano Banana, Pro, 2, 2 Lite and 2.1. Google Direct means the Vertex AI API in this project. Google's Gemini Developer API is a separate surface and should receive its own adapter and result label if added later.

Named endpoints identify the requested model family, but third-party aliases do not prove an identical underlying revision. Preserve returned model-version metadata where available and mark it unknown when absent. Record run dates, region, settings, and the profile hash. Changes in routing, defaults, or upstream filters can change future results.

No common seed is imposed because reproducibility semantics can differ across providers. A client-side attempt also may include undisclosed server-side retries. Preserve provider retry metadata when returned and do not claim to measure one raw model invocation.

The [violence dataset](../datasets/violence/README.md) uses already injured or violent staged references. Its runner-enforced freeze covers case and provenance manifests and every reference file. The current cases were selected from exploratory edit-completion outcomes; disclose this selection when reporting policy results. Do not combine measurements from different input hashes or model families.

## Measure refusals separately from availability

Retain an individual record for every scheduled trial. The runner classifies explicit provider policy signals, returned images, invalid requests, authentication failures, rate limits, timeouts, server errors, and unexplained responses separately.

- A generic HTTP 400 or 422 is not proof of a policy block.
- An empty response or a response without an image is not proof of a policy block.
- A queue marked complete is not proof that inference succeeded. Fetch and inspect its final result.
- Preserve the provider's exact policy code or finish reason. Infer an input/output block stage only when the response supplies it.
- Text-only responses require review if they lack a documented refusal signal. Do not classify text as a refusal merely because it contains a safety-related word.

Report both denominators: all scheduled attempts, and evaluable content outcomes after separately listing operational failures and unresolved responses. Never count a missing reference, authentication problem, or untested case as a successful generation. If the run is interrupted, show planned versus completed attempts.

Providers expose different amounts of error detail. A provider with more unclassified failures must not appear to have fewer policy failures merely because its diagnostics are less specific. Review unresolved responses before interpreting a comparative rejection rate. A clear task-completion example requires a visually verified output, not just the absence of an explicit policy code.

Use the phrase **policy-related rejection rate on this test set**. Calling a rejection a false positive requires a documented judgment against the provider's applicable policy and the actual input/output request. The dataset's expected behavior describes the creative task, not a guarantee of policy approval.

## Optional visual review

For this policy comparison, a returned image is an API outcome regardless of whether its lighting is accurate. Optional visual review scores editing and preservation independently. A no-op may preserve content while failing the edit; an effective edit may remove defining content. Neither observation alone proves moderation. Keep these judgments separate from explicit policy-block rates and keep the reviewed-image denominator explicit.

For the included image edits, optional reviews use `edit_success` and
`preservation` scores bound to the saved output checksum. Legacy fidelity labels
remain supported for historical runs and text-generation records. Record the
reviewer, date and notes without rewriting native API evidence. A strict visual
pass in `comparison.py` requires successful editing and preserved content; it is
not the primary policy measure.

When adding controlled contrasts, hold the source image constant where possible
and change only the operation being studied, such as removing versus preserving
an existing injury. Reference-to-text counterparts are descriptive comparisons,
not clean causal tests, because the generation task differs. Freeze the complete
case pool before inference and give all cases the same planned repeat count.

## Publish useful examples with a clear scope

The blog may focus on examples where Segmind completes a requested task that another endpoint rejects. Label these as selected examples and include all repetitions for each highlighted case, not just the best-looking attempt.

Suggested disclosure:

> These examples were selected to illustrate cases where Segmind completed the requested task and another tested endpoint did not. The linked results identify the exact inputs, model profiles, account configuration, and all attempts for these examples.

For a headline about all 15 cases, publish the complete 15-case run, including neutral and unfavorable results. If cases are selected after observing outcomes, label the release a **curated comparison suite** and state that selection rule. Its results establish what happened on those selected examples, not a general ranking of providers.

Do not infer why a provider accepts more cases from results alone. Moderation settings, account configuration, backend routing, model revision, and random variation are possible explanations, not established causes.

## Adding another category or provider

Maintain violence cases in the single `datasets/violence` directory. Track reviewed changes with its version, freeze hashes, Git history and saved run snapshots instead of parallel dataset folders. Reuse the case and asset schemas when extending coverage. Add an independently documented adapter and profile entries for another provider rather than silently routing its name through a different endpoint.

Keep run artifacts in ignored `runs/` until reviewed for accidental secrets, account identifiers, signed URLs, output licensing, and correct labels. Publish an intentional result snapshot with its dataset and profile commit. Do not include private meeting transcripts, internal operational information, or credentials in this public repository.
