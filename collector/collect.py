#!/usr/bin/env python3
"""Build this fleet's data file from its declared sources.

    python3 collector/collect.py --check     # every field the intent requires has a source
    python3 collector/collect.py             # run the adapters and write the data file
    python3 collector/collect.py --dry-run   # run the adapters, print what would change

The intent is the contract. This script exists to prove the local implementation
still satisfies it: when the intent gains a field and nothing here supplies it,
--check fails and CI dispatches Claude to close the gap. Do not silence a failure
by trimming the intent.
"""
import json, os, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = ROOT / "collector" / "sources.yml"

# The harness carries the contract logic. CI checks it out to .harness/;
# locally, set HARNESS=../harness or keep a sibling checkout.
HARNESS_CANDIDATES = [
    pathlib.Path(os.environ["HARNESS"]) if os.environ.get("HARNESS") else None,
    ROOT / ".harness",
    ROOT.parent / "harness",
]


def harness_scaffold():
    for base in filter(None, HARNESS_CANDIDATES):
        p = base / "plugins/fleet-control/skills/fleet-scaffold/references"
        if (p / "scaffold.py").exists():
            sys.path.insert(0, str(p))
            import scaffold
            return scaffold
    sys.exit("harness not found. Set HARNESS=/path/to/harness or check one out at ../harness")


def load_yaml(path):
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except ImportError:
        sys.exit("pip install pyyaml")


def paths():
    intents = sorted(ROOT.glob("intent/*.intent.json"))
    if len(intents) != 1:
        sys.exit(f"expected exactly one intent file, found {len(intents)}")
    fleet = intents[0].name.removesuffix(".intent.json")
    return fleet, intents[0], ROOT / "data" / f"{fleet}.data.json"


# ---------------------------------------------------------------- adapters
# One function per system that owns values. Each takes the instance record as it
# stands and returns the fields it owns. Keep them small and side-effect free;
# anything that needs a token reads it from the environment.


def adapter_manual(record, field, spec):
    """Value is maintained by a human in the data file. Carry it through."""
    return record.get(field)


def adapter_github_actions(record, field, spec):
    """Pipeline stage states and deploy frequency from workflow runs."""
    if not os.environ.get("GITHUB_TOKEN"):
        return record.get(field)          # no token in this context: keep last known
    raise NotImplementedError("wire gh api workflow runs here")


def adapter_sonarqube(record, field, spec):
    """Coverage, rating, debt and the quality gate verdict."""
    if not os.environ.get("SONAR_TOKEN"):
        return record.get(field)
    raise NotImplementedError("wire the SonarQube measures API here")


def adapter_argocd(record, field, spec):
    """Deployed version and health per environment."""
    if not os.environ.get("ARGOCD_TOKEN"):
        return record.get(field)
    raise NotImplementedError("wire the Argo CD applications API here")


def adapter_trivy(record, field, spec):
    """Open vulnerability counts by severity."""
    return record.get(field)


ADAPTERS = {
    "manual": adapter_manual,
    "github_actions": adapter_github_actions,
    "sonarqube": adapter_sonarqube,
    "argocd": adapter_argocd,
    "trivy": adapter_trivy,
}


# ---------------------------------------------------------------- contract
def required_fields(intent):
    """Top-level fields the intent expects on every instance."""
    scaffold = harness_scaffold()
    return set(scaffold.skeleton(intent, "__contract__").keys())


def check(intent, sources):
    declared = set((sources.get("fields") or {}).keys())
    needed = required_fields(intent)
    missing = sorted(needed - declared)
    stale = sorted(declared - needed)
    todo = sorted(f for f, s in (sources.get("fields") or {}).items()
                  if (s or {}).get("status") == "todo")
    unknown = sorted({(s or {}).get("adapter") for s in (sources.get("fields") or {}).values()}
                     - set(ADAPTERS) - {None})

    for f in missing:
        print(f"NO SOURCE   {f} — the intent requires it and sources.yml does not declare it")
    for a in unknown:
        print(f"NO ADAPTER  {a} — declared in sources.yml but not implemented in collect.py")
    for f in stale:
        print(f"orphan      {f} — declared but no longer in the intent")
    for f in todo:
        print(f"todo        {f} — carried manually, no real source yet")
    print(f"\n{len(needed)} fields required · {len(declared)} declared · "
          f"{len(missing)} unsourced · {len(todo)} manual")
    return not missing and not unknown


def collect(intent, sources, data_path, dry_run=False):
    raw = json.loads(data_path.read_text(encoding="utf-8"))
    items = raw.get("items", raw if isinstance(raw, list) else [])
    fields = sources.get("fields") or {}
    changed = 0
    for rec in items:
        for field, spec in fields.items():
            fn = ADAPTERS.get((spec or {}).get("adapter", "manual"), adapter_manual)
            try:
                value = fn(rec, field, spec or {})
            except NotImplementedError as e:
                print(f"  {rec.get('id') or rec.get('name')}: {field} — {e}")
                continue
            if value is not None and rec.get(field) != value:
                rec[field] = value
                changed += 1
    print(f"{len(items)} instances · {changed} values refreshed"
          + (" (dry run, nothing written)" if dry_run else ""))
    if not dry_run and changed:
        data_path.write_text(json.dumps({"items": items}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return True


def main():
    fleet, intent_path, data_path = paths()
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    sources = load_yaml(SOURCES)
    if "--check" in sys.argv:
        sys.exit(0 if check(intent, sources) else 1)
    collect(intent, sources, data_path, dry_run="--dry-run" in sys.argv)


if __name__ == "__main__":
    main()
