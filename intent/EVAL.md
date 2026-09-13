# Eval — what the data may claim

Normative. RFC 2119 keywords.

## 1. Requirement

A `live` field's value MUST have been produced by its adapter from the owning
system, on the version being built. A value the adapter merely kept is not
evidence; it is the last evidence, and MUST be reported as such.

## 2. Evidence

`collect` produces a report — to standard output, and as
`data/collect-report.json` written by the automation alongside the data file —
recording, per component and per `live` field: `produced` (the adapter read the
system), `kept` (the adapter could not, and says why), or `unsourced` (the field
has no declared source). It records the run's timestamp and the commit of the
fleet intent it ran against.

Only `produced` is evidence. The room MUST show the report's timestamp as when it
was last refreshed (INTENT.md §7.4).

## 3. Procedure

The evaluation is `collect` against the real estate, through the implementation's
own commands, with the credentials available to it: every component whose
repository exists MUST have every `live` field `produced`. A component whose
repository does not exist yet is expected `kept` at its day-one values and is
not a failure.

Coverage MUST include: the contract check, the sources check, one `collect`,
the audit, one `room`, and that `check` fails on a record with a required field
removed.

## 4. Consequences

| Condition | Build | Room |
|---|---|---|
| every `live` field `produced` | succeeds | current |
| some `kept`, with reasons | succeeds | current, showing the report |
| a contract break, an unsourced field, an undeclared adapter | **fails** | not regenerated |
| GitHub unreachable | succeeds | last known, saying so |

The owning systems being unreachable MUST NOT fail a build. Only conditions this
repository controls may.

## 5. Staleness

Data is stale when the report is older than the collection schedule allows, or
when the fleet intent has changed since the report ran. Stale data still renders
and MUST be reported as stale.

## 6. Credentials

Adapters authenticate as `gh` does. On a runner, `GH_TOKEN` or `GITHUB_TOKEN`;
locally, a person's `gh auth login`. No other credential is needed for the
adapters this specification names; an adapter for another system MUST name its
credential's environment variable in `sources.yml` under the adapter's `note`,
and that variable MUST be the only way the credential reaches the adapter.

## 7. Acceptance

A change to the implementation MUST NOT be accepted until:

1. every MUST and MUST NOT in `INTENT.md` and `SPEC.md` is pinned by a test that
   fails when it is violated, and those tests pass on the change;
2. `collect` has run against the real estate **on the change itself**, and every
   `live` field that was `produced` before the change is `produced` after it;
3. `check`, `audit` and `room` succeed on the change.

**Whoever makes a change runs `collect` before submitting it**, with the
credentials available to them, and reads the report as a verdict on the change:

- a field `kept` because the adapter itself failed against a reachable system is
  a **defect in the change**, to be fixed before submission — never reported as
  the last known value and moved past;
- a field `kept` because the system was unreachable or the credential absent is
  not a verdict; the submission says which components could not be collected
  and why;
- a system rejecting what the adapter sends is a defect in the adapter. What the
  adapter learned about the system is recorded in `sources.yml` under the
  adapter's `note`, as its own change, and named in the submission that depends
  on it.

The submission states the report's summary — components, fields `produced`,
`kept` with reasons, `unsourced`.

## 8. Automation

`collect` MUST exit `0` in all cases. `check` MUST exit non-zero for any condition
§4 marks as failing the build.

**A change to the implementation MUST NOT modify anything under `intent/`,
`data/` or `site/`.** Those have two writers and a change is neither:

- people change the specification, the fleet intent and the component files
  under `intent/components/` (SPEC.md §3), deliberately, as changes of their own;
- the automation on the default branch writes `data/` and `site/`, on its
  schedule and after acceptance, from its own run.

A change states its report in the submission (§7); the automation verifies it by
running `collect` on the change and comparing with the report on the default
branch, and writes nothing until the change is merged.
