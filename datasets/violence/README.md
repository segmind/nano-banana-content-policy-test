# Violence dataset

This is the single maintained violence benchmark. It contains 15 image edits using
15 distinct color photographs of theatrical injuries, makeup and training props.
All model profiles use these same cases by default; choose the model with
`--model` and optional subsets with repeated `--case` arguments.

```bash
python benchmark.py validate --require-assets
python benchmark.py plan --model nano-banana-2
python benchmark.py run --model nano-banana-2 --env-file .env --repeats 3
```

The cases request neutral warm relighting; three also explicitly preserve the
existing practical effects. [cases.json](cases.json) contains exact prompts,
reference IDs and optional visual checks. The main measure is explicit policy
blocking, with image returns, operational errors and unresolved responses kept
separate. Edit quality and preservation are optional independent review axes;
lighting precision does not determine whether a policy block occurred.

## Inputs and selection scope

The photographs cover zombie makeup, bloodied performers, face and neck wound
effects, simulated casualties, detached training props, fractures and burns.
None document a real attack or injury. The current cases were selected from
exploratory outcomes to maximize a reviewed edit-completion difference. They are
a curated collection, not a representative estimate of general provider behavior.
The selection evidence hashes remain in the case metadata for auditability; its
historical study labels do not name additional maintained datasets.

Reference images are fitted without cropping to a neutral-gray 1536-pixel square.
Both providers receive identical prepared bytes. [assets.json](assets.json)
retains source records, rights evidence, original and prepared hashes, credit,
transformations and the immutable public URL for each image. A pinned URL can
contain a historical folder name because it addresses a fixed Git commit; its
bytes must still match the current local asset hash.

Sources carry CC0 dedications or documented U.S.-only government-work claims.
The maintainer accepts that U.S.-only basis for this comparison. Other
jurisdictions, likeness, privacy, publicity and trademark clearance are not
asserted. These third-party photographs are not covered by the repository's MIT
license. An age-unverified source and original-film frames are excluded.

The appearance of U.S. Department of War (DoW) visual information does not imply
or constitute DoW endorsement.

## Update and freeze

Extend the cases and references in this directory instead of adding another
violence dataset folder. Keep case IDs stable when their inputs are unchanged.
Give materially changed tasks distinct IDs, update the dataset version and design
counts, and document any new reference's rights and checksum before testing.

The runner refuses changed prompts, provenance or reference bytes after a freeze.
For reviewed changes, deliberately remove the tracked `freeze.json`, then run:

```bash
python benchmark.py freeze --reviewer "Reference reviewer"
python benchmark.py validate --require-assets
```

Commit the revised cases, provenance, images and freeze together. The freeze
command never silently overwrites an existing freeze. Historical run snapshots,
checksums and outputs remain unchanged, and older dataset definitions are
recoverable from Git history. Results from different input hashes or models
must remain separate. Use the same planned repetitions for every compared case;
keep exploratory selection and fresh confirmation observations separate.
