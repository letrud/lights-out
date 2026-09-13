# software-factory

The delivery fleet: every repo in the estate, scored on automation, quality, environments and supply chain.

## The one rule

`intent/software-factory.intent.json` is the contract. Everything else in this repo exists to satisfy it.

When a check fails, the fix is downstream of the intent — never edit the intent to make a check pass. Changing the standard is a deliberate act with its own PR and its own argument.

## What "the local implementation" means here

| Path | What it is | Who changes it |
| --- | --- | --- |
| `intent/software-factory.intent.json` | The contract: unit, dimensions, states, severity, standard, views | Humans, deliberately |
| `collector/sources.yml` | Where every field the intent requires actually comes from | Claude, when the intent gains a field |
| `collector/collect.py` | The adapters that fetch those values | Claude, when a field needs a new adapter |
| `data/software-factory.data.json` | The instances | The collector, or a human for `manual` fields |
| `site/control-room.html` | Generated. Never hand-edited | CI |

## When the intent changes

The workflow runs three checks, in this order, and each one tells you something different:

1. **Schema** — is the intent itself well formed. Fails the build outright.
2. **Contract** (`scaffold.py ... check`) — does every instance carry every field the intent now requires.
3. **Sources** (`collect.py --check`) — does the collector declare where each of those fields comes from.

A raised standard is *supposed* to produce audit gaps, so the audit is advisory here. The contract and source checks are not: they mean the intent is describing something the implementation cannot supply.

## How a component is wired

Each record in the data file carries, owned by a human, what the adapters need to find its facts:

| Field | What it is |
| --- | --- |
| `path` | `owner/name` of the GitHub repo. Every GitHub adapter keys on it; a repo that does not exist yet keeps its day-one values |
| `pipeline` | `{stage: workflow file}` — which workflow's runs prove each golden-path stage. A stage with no workflow is `idle` (not configured), never `ok` |
| `envMap` | `{deployment environment: slot}` — which GitHub Deployments environment fills which of `dev / test / stage / prod`. Unmapped slots are `none` |

The adapters read GitHub through `gh`, so `make collect` works from any machine where `gh auth status` passes, and in CI with the job token. Stage state comes from the latest run on the default branch (pull-request runs are ignored); a passing stage with a failure in its last five runs is `warn`. The DORA figures come from the `deploy` workflow: deploys in 7 days, per-day frequency over 10 days, median commit-to-deploy lead time, change failure rate over 30 days, mean time to restore.

Quality fields with no analysis platform behind them are `null` and declared `todo` in `sources.yml`. Supply-chain facts (`signed`, `sbom`, `slsa`) are `false` / `0` because nothing signs or attests yet — that is a fact about the estate, not an unknown.

## Closing a gap

1. Add the field to `collector/sources.yml` under the adapter that genuinely owns the value. If no source exists yet, use `adapter: manual` with `status: todo` and a one-line note — **never invent a plausible adapter**; a fabricated source is worse than a declared gap.
2. Add or extend the adapter in `collector/collect.py` if the field needs one. Adapters are small, side-effect free, and read credentials from the environment. An adapter with no token returns the last known value rather than failing the run.
3. Backfill `data/software-factory.data.json`. Unknown is `null`, or the intent's absent state (`idle`) — never an optimistic guess. A component that has never run must look like it has never run.
4. Re-run both checks until they pass, then let CI regenerate `site/control-room.html`.

## Local commands

```bash
make check      # schema, contract and source coverage
make audit      # ranked gaps against the golden path baseline
make room       # regenerate site/control-room.html
make collect    # run the adapters and refresh the data file
```

They need the harness: check it out at `../harness`, or set `HARNESS=/path/to/harness`.

## Conventions

- Keep `data/*.data.json` sorted by `name` so diffs stay readable.
- One record per repo, one repo per record. `path` is the repo; `name` is its short name.
- A component that is planned but has no repo yet is still a record, at its honest day-one state, so the fleet shows what is coming.
- Tier 1 means customer-facing or money-touching; its baseline is the strict one.
- `freq` arrays must be the same length across every instance, or the sparklines lie.
