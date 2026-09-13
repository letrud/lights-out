# Intent

This folder specifies `software-factory`. An implementation conforming to
`INTENT.md`, `SPEC.md` and `EVAL.md` is a correct implementation, in any
language. Source code is an output of this specification, not a peer of it.

Where a statement here conflicts with existing code, the code is wrong.

## 1. What software-factory is

The delivery fleet: every repository in the estate, held to one declared
standard, with the facts about each gathered from the systems that own them and
rendered as one control room.

Two files under `intent/` are the contract. `software-factory.intent.json` — the
*fleet intent* — declares what a component is, the dimensions it is judged on,
the states those take, the standard it is held to, and the views. This document
and its companions declare how the facts that fill it are gathered, kept honest,
and published.

## 2. The fleet intent is the standard

**2.1** `software-factory.intent.json` is read, validated, audited and rendered by
the harness's `fleet-control` engine (`letrud/harness`, pinned). An
implementation MUST use that engine for schema validation, the contract check,
the audit and the render, and MUST NOT fork or reimplement it.

**2.2** Every field the fleet intent requires of a component MUST be present on
every component record, and MUST have a declared source (§3). A component record
that lacks a required field is a contract break, and a contract break MUST fail
the build.

**2.3** Conformance — whether a component meets the standard — is advisory.
Raising the standard is supposed to produce gaps; they are for people to act on,
never for the implementation to close by changing data.

## 3. Every field has a declared source

**3.1** `collector/sources.yml` MUST declare, for every field the fleet intent
requires, the adapter that supplies it and its status: `live` (a real system,
read by an adapter), `owned` (a person maintains it by design), or `todo`
(carried by hand only because no source exists yet, with a one-line note).

**3.2** An implementation MUST NOT invent a plausible adapter. A field with no
real source is `todo`, and its value is `null` or the fleet intent's absent
state — never a guess.

**3.3** A `live` field's value MUST come from the system that owns it, read
through that system's own interface, keyed by the component's declared identity
(§5). An adapter that cannot reach its system MUST keep the last known value and
say so in its report; it MUST NOT fail the run, and MUST NOT substitute a guess.

## 4. Facts come from the systems that own them

**4.1** Delivery facts — the state of each golden-path stage, deploy frequency,
lead time, change failure rate, time to restore — come from the component's
workflow runs on its default branch. Runs for proposed changes prove a proposal,
not the component, and MUST be ignored.

**4.2** Environment facts — what runs where, and its health — come from the
component's deployments and their statuses.

**4.3** Vulnerability facts come from the component's dependency alerts. Where
alerts are not enabled for a component, the value is unknown, never zero.

**4.4** Quality and supply-chain facts that no platform in the estate provides
yet are `todo`. Supply-chain facts that are simply not done — nothing is signed,
no SBOM is published — are recorded as `false`, because that is a fact, not an
unknown.

## 5. A component is wired by people

Each component is declared by people, as a file under `intent/components/`:
what it is called, where its repository is, who owns it, which team, which
criticality tier, **which workflow proves each golden-path stage**, and **which
deployment environment fills which slot**. `SPEC.md` names these fields. The
collector fills in everything else. A stage with no workflow declared is
absent — not configured — and MUST never render as passing.

A component that is planned but has no repository yet is still a record, at its
honest day-one state, so the fleet shows what is coming.

## 6. Derived files have one writer

`data/` and `site/` are generated: the data file by the collector, the room by
the renderer. The automation on the default branch writes them, on a schedule
and after acceptance, and nobody else. A change to the implementation MUST NOT
modify `data/`, `site/` or anything under `intent/`. A conflict in a derived
file is resolved by regenerating it.

`intent/` likewise has two writers — people for the specification and the fleet
intent, the automation for nothing yet — and a change is neither.

## 7. Honesty constraints

**7.1** A state most components are in most of the time renders neutral;
colour means attention.

**7.2** `absent` is never `ok`. A component that has never run must look like it
has never run.

**7.3** A passing stage with a recent failure is degraded, not passing.

**7.4** The room MUST say when it was last refreshed and from which commit of
the data.

## 8. Publication

The control room is a static page, regenerated from the data file whenever the
data or the fleet intent changes, and published where `SPEC.md` says. What is
published MUST be what the repository holds; nothing is rendered at request time.

## 9. Form

This folder states what MUST be true, so that it reads as instructions rather
than as narrative. Rationale, history and alternatives considered do not belong
here; neither does anything a capable implementer would arrive at unaided.
