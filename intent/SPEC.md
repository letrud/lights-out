# Spec — representation

Normative. RFC 2119 keywords.

## 1. Files

```
intent/
  software-factory.intent.json   the fleet intent — the standard; schema in the harness
  components/<name>.json         one component's owned wiring — people write these
  INTENT.md  SPEC.md  EVAL.md    this specification
collector/
  sources.yml                    where every required field comes from
  <implementation>               the adapters
data/
  software-factory.data.json     generated — the component records
site/
  control-room.html              generated — the room
```

The fleet intent's schema, the contract check, the audit and the renderer are the
harness's: `letrud/harness`, `plugins/fleet-control/skills/*/references/`, at the
ref the implementation pins. Locally the harness is expected at `../harness` or
at `HARNESS`.

## 2. `collector/sources.yml`

```yaml
fleet: software-factory
adapters:
  <adapter>: { note: <what system, read how> }
fields:
  <field>: { adapter: <adapter>, status: live | owned | todo, note?: <text> }
```

**2.1** Every field the fleet intent requires MUST appear under `fields`. The
required set is what the harness's scaffold seeds for a new component; the
implementation MUST derive it from the fleet intent, never list it by hand.

**2.2** Every `adapter` named MUST be implemented; an adapter implemented but
not named is dead code.

**2.3** `todo` MUST carry a note saying what source would be needed.

## 3. Components

A component is declared by people in `intent/components/<name>.json`, one file
per component, carrying exactly the owned fields below and nothing else. Adding a
component to the fleet is a change under `intent/` with no code in it. The
collector produces `data/software-factory.data.json` from these files: one
record per component, the owned fields copied through, every other required
field filled by its adapter or left at its day-one value.

Owned fields — people write these, an adapter MUST NOT:

| Field | Meaning |
|---|---|
| `name` | short name; records are sorted by it |
| `path` | `owner/repository` on GitHub; every adapter keys on it. A repository that does not exist keeps its day-one values |
| `lang`, `squad`, `tier`, `owner` | as the fleet intent describes them |
| `pipeline` | `{stage: workflow file}` — which workflow's runs prove each golden-path stage. A stage absent from the map is `idle` |
| `envMap` | `{deployment environment: slot}` — which deployment environment fills which of the fleet intent's slots. Unmapped slots are `none` |

Everything else on a record is a `live` or `todo` field and is written only by
the collector. A component file that lacks an owned field is a contract break.

## 4. Adapters

**4.1 `github_actions`** — reads the repository's workflow runs on its default
branch, ignoring pull-request runs.

- A stage's state is the latest run of its declared workflow: in progress →
  `run`; failure, timed out, startup failure → `crit`; cancelled or unknown →
  `warn`; success → `ok`, but `warn` if any of the last five completed runs
  failed. No declared workflow, or no runs → `idle`.
- `stageLinks` is the URL of that latest run per stage that has one.
- `auto` is the percentage of stages not `idle`.
- From the `deploy` stage's workflow: `deploys` (successes in 7 days); `freq`
  (successes per day over 10 days, oldest first, always 10 long); `lastDeploy`
  (relative time of the last success, or `never`); `leadM` and `lead` (median
  minutes from head commit to run completion over the last 10 successes);
  `cfr` (failed over completed in 30 days, percent); `mttr` (mean minutes from a
  failure to the next success). With no deploy workflow: `deploys` 0, `freq` all
  zero, `lastDeploy` `never`, the rest `null`.

**4.2 `github_deployments`** — for each environment in `envMap`, the newest
deployment: its ref (or short SHA) as the slot's version, its latest status as
the slot's state (`success`/`inactive` → `ok`; `failure`/`error` → `crit`;
`in_progress`/`queued`/`pending` → `run`; otherwise `warn`). Unmapped slots are
`null` / `none`.

**4.3 `github_dependabot`** — open alerts by severity into `vuln.c/h/m`. Alerts
disabled → last known value kept, report says so.

**4.4** Adapters read GitHub through the `gh` CLI, authenticated by whatever
`gh` finds — a person's login, or `GH_TOKEN`/`GITHUB_TOKEN` on a runner. Without
either, every `live` field keeps its last known value.

## 5. Commands

The implementation MUST offer, runnable locally and in CI:

| Command | Does |
|---|---|
| `check` | schema (fleet intent against the harness schema), components (every `intent/components/*.json` carries exactly the owned fields), contract (every data record complete), sources (every required field declared) |
| `audit` | ranked gaps against the standard, via the harness |
| `collect` | run the adapters and rewrite the data file; `--check` for sources only; `--dry-run` to print what would change |
| `room` | render `site/control-room.html` via the harness |

## 6. Automation

| Workflow | Role |
|---|---|
| `.github/workflows/build.yml` | proves the implementation on every push and pull request: `check`, the adapters' tests, `audit`; refuses a pull request that changes `intent/`, `data/` or `site/` together with anything else |
| `.github/workflows/collect.yml` | on a schedule — every five minutes — and on dispatch: `collect`, `check`, `room`; commits `data/` and `site/` on the default branch only when something changed, then publishes |
| `.github/workflows/pages.yml` | publishes `site/` to GitHub Pages; also after the fleet-intent workflow re-renders |
| `.github/workflows/on-intent-change.yml` | the harness's fleet workflow: on a change to the fleet intent, validates, audits, re-renders; report-only |

Commits made by the automation carry no push event, so publication after a
regeneration MUST be dispatched explicitly or chained by `workflow_run`.

## 7. Publication

`site/control-room.html` is published at
`https://letrud.github.io/software-factory/`, with the file copied to
`index.html` in the published artifact only, so the repository holds one
generated file and the root URL resolves.

## 8. Validation

A build MUST fail for: a fleet intent that does not validate against the
harness schema; a component file missing an owned field or carrying a field it
does not own; a data record missing a required field; a required field with no
declared source; an adapter declared but not implemented; a `freq` array of the
wrong length on any record.
