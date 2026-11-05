# Provider contracts and comparison limits

Documentation checked November 5, 2026. Adapter implementation and offline tests do not establish that a paid account or a live endpoint currently works. Run a small smoke test before a complete comparison and record its outcome separately.

## Model profiles

| Profile | Segmind slug | fal generation / editing | Google Vertex model |
| --- | --- | --- | --- |
| `nano-banana` | `nano-banana` | `fal-ai/nano-banana` / `fal-ai/nano-banana/edit` | `gemini-2.5-flash-image` |
| `nano-banana-pro` | `nano-banana-pro` | `fal-ai/nano-banana-pro` / `fal-ai/nano-banana-pro/edit` | `gemini-3-pro-image` |

Both profiles use `1:1`. Pro explicitly requests `1K`; Segmind's documented default is `4K` and fal's is `1K`. The adapters translate that choice to `output_resolution`, `resolution`, and `generationConfig.imageConfig.imageSize` respectively. PNG is requested where format control is available. The original Segmind profile does not assume support for Pro-only fields.

Safety settings remain omitted in the baseline. Segmind Pro documents numeric `safety_tolerance`, fal documents a string enum, and Google exposes its own safety controls. Matching numbers across these APIs is not evidence of matching filters. The runner records account mode and actual submitted settings rather than claiming equivalence.

The mappings select the corresponding advertised families. A third-party provider can change the backend behind an alias; its actual revision may not be exposed. Never substitute a preview, newer family, or fallback endpoint without a new profile and clear result label.

## Segmind

Submit once to `POST https://api.segmind.com/v2/{model}` with the `x-api-key` header. Poll the returned status URL and fetch the final response. Preserve the request ID for an unknown or timed-out result. Do not resubmit just because polling timed out.

The model API documents public URLs in `image_urls`. This runner requires a public URL for every Segmind reference and fetches it before inference to verify its SHA-256 matches the local reference. Use a URL pinned to the asset commit. fal and Vertex receive the same local file bytes through their documented inline mechanisms.

The adapter accepts current `images[]` results and older `output` media envelopes. A JSON-encoded `output.data.finish_reason` can carry a Gemini safety or recitation result even under HTTP 200. The classifier recognizes exact known enum values, including the `FinishReason.` prefix, rather than matching words in a message. Failed HTTP 422 polls with `status: FAILED` are followed by a result fetch so full native diagnostics are preserved.

Segmind's async `FAILED` state and HTTP 422 cover multiple failure types. They do not by themselves establish a policy refusal. Public documentation does not specify a stable typed Nano Banana moderation-error schema; ambiguous errors remain unclassified for human review.

Sources: [original API](https://www.segmind.com/models/nano-banana/api), [Pro API](https://www.segmind.com/models/nano-banana-pro/api), [async inference](https://docs.segmind.com/docs/serverless-api/async-inference).

## fal

Submit to `https://queue.fal.run/{endpoint}` with `Authorization: Key ...`. Use the generation endpoint for prompt-only cases and the `/edit` endpoint when references are present. `image_urls` accepts data URIs, allowing identical local bytes without a separate hosted input.

The queue's `COMPLETED` state is terminal, not a success assertion. Retrieve the final result. An explicit error type `content_policy_violation` is a policy signal; `no_media_generated` is not enough to identify the cause. Some endpoints may still return older error shapes, which should remain preserved for review.

Sources: [original edit API](https://fal.ai/models/fal-ai/nano-banana/edit/api), [Pro edit API](https://fal.ai/models/fal-ai/nano-banana-pro/edit/api), [error taxonomy](https://fal.ai/docs/documentation/model-apis/errors), [queue status](https://fal.ai/docs/api-reference/inference-api/queue/status).

## Google Direct through Vertex AI

Use `POST https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/publishers/google/models/{model}:generateContent` with a Google OAuth bearer token. This is the Google Cloud API, separate from the Gemini Developer API and its API-key authentication.

The request contains the exact prompt and reference bytes in `contents[].parts`, with `responseModalities` set to `TEXT` and `IMAGE`. Preserve `promptFeedback`, candidate finish reasons, safety ratings, response ID, and `modelVersion` when returned. A thought image is not a final generated image.

Explicit safety, blocklist, or prohibited-content reasons are content-policy signals. Recitation is a separate category. `NO_IMAGE`, `IMAGE_OTHER`, `OTHER`, and text-only `STOP` responses need their own labels or manual review. Google's image-safety documentation explains that some model refusals can arrive as text with `STOP`.

Sources: [Pro model](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-pro-image), [model lifecycle](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions), [response schema](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/GenerateContentResponse), [image safety behavior](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/gemini-image-responsible-ai).

## Live evidence still required

Before using a comparative headline, validate the included references, smoke-test each configured adapter, complete the planned runs, and visually review the returned images. Offline tests and credential skips do not establish a provider performance result.
