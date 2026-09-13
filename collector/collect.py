#!/usr/bin/env python3
"""Build this fleet's data file from its declared sources.

    python3 collector/collect.py --check     # every field the intent requires has a source
    python3 collector/collect.py             # run the adapters and write the data file
    python3 collector/collect.py --dry-run   # run the adapters, print what would change

The intent is the contract. This script exists to prove the local implementation
still satisfies it: when the intent gains a field and nothing here supplies it,
--check fails and CI dispatches Claude to close the gap. Do not silence a failure
by trimming the intent.

Every GitHub-backed adapter talks to the API through the `gh` CLI, so it works
wherever `gh` is authenticated: a developer's machine, or a runner with
GH_TOKEN / GITHUB_TOKEN set. Without `gh` or a token the adapters keep the last
known value rather than failing the run.

Per-component wiring lives in the data file, owned by a human:

    path      owner/name of the GitHub repo
    pipeline  {stage: workflow file}   which workflow proves each golden-path stage
    envMap    {deployment env: slot}   which GitHub deployment environment is which slot
"""
import json, os, pathlib, shutil, statistics, subprocess, sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = ROOT / "collector" / "sources.yml"

# The harness carries the contract logic. CI checks it out to .harness/;
# locally, set HARNESS=../harness or keep a sibling checkout.
HARNESS_CANDIDATES = [
    pathlib.Path(os.environ["HARNESS"]) if os.environ.get("HARNESS") else None,
    ROOT / ".harness",
    ROOT.parent / "harness",
]

STAGES = ("build", "test", "scan", "sign", "release", "deploy")
FREQ_DAYS = 10          # the intent's trend: deploys per day, last 10 days
DEPLOY_WINDOW_DAYS = 7  # the intent's counter: deploys in the last 7 days
CFR_WINDOW_DAYS = 30
FLAKY_LOOKBACK = 5      # a passing stage with a failure in its last N runs is "warn"


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


# ---------------------------------------------------------------- github client
# One cached fetch per repo per endpoint; the adapters below are called once per
# field per record, so they must not hit the API each time.

_CACHE = {}


def gh_available():
    if not shutil.which("gh"):
        return False
    if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        return True
    return subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0


def gh_api(path):
    """GET a REST path through `gh api`. None on any error (404, 403, no auth)."""
    if path in _CACHE:
        return _CACHE[path]
    env = dict(os.environ)
    if not env.get("GH_TOKEN") and env.get("GITHUB_TOKEN"):
        env["GH_TOKEN"] = env["GITHUB_TOKEN"]
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True, env=env)
    _CACHE[path] = json.loads(r.stdout) if r.returncode == 0 and r.stdout else None
    return _CACHE[path]


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def now():
    return datetime.now(timezone.utc)


def humanize(minutes):
    if minutes is None:
        return None
    m = int(round(minutes))
    if m < 60:
        return f"{m}m"
    h, m = divmod(m, 60)
    if h < 48:
        return f"{h}h {m:02d}m" if m else f"{h}h"
    return f"{h // 24}d {h % 24}h"


def ago(dt):
    if dt is None:
        return "never"
    m = (now() - dt).total_seconds() / 60
    if m < 1:
        return "just now"
    if m < 60:
        return f"{int(m)}m ago"
    if m < 60 * 48:
        return f"{int(m // 60)}h ago"
    return f"{int(m // 1440)}d ago"


def runs_for(repo):
    """Completed and running workflow runs on the default branch, newest first.
    Pull-request runs are excluded: they prove a proposal, not the component."""
    key = ("runs", repo)
    if key not in _CACHE:
        data = gh_api(f"repos/{repo}/actions/runs?per_page=100")
        runs = [r for r in (data or {}).get("workflow_runs", []) if r.get("event") != "pull_request"]
        _CACHE[key] = runs
    return _CACHE[key]


def runs_of(repo, workflow_file):
    if not workflow_file:
        return []
    return [r for r in runs_for(repo) if r.get("path", "").endswith("/" + workflow_file)]


def stage_state(runs):
    """Golden-path state of one stage from the runs of the workflow that proves it."""
    if not runs:
        return "idle"
    latest = runs[0]
    if latest.get("status") in ("queued", "in_progress", "waiting", "pending", "requested"):
        return "run"
    c = latest.get("conclusion")
    if c in ("failure", "timed_out", "startup_failure", "action_required"):
        return "crit"
    if c in ("cancelled", "neutral", "stale", None):
        return "warn"
    recent = [r.get("conclusion") for r in runs[:FLAKY_LOOKBACK] if r.get("status") == "completed"]
    if any(x in ("failure", "timed_out", "startup_failure") for x in recent):
        return "warn"
    return "ok"


def deploy_metrics(repo, workflow_file):
    """DORA-style figures from the workflow that proves the deploy stage."""
    runs = [r for r in runs_of(repo, workflow_file) if r.get("status") == "completed"]
    ok = [r for r in runs if r.get("conclusion") == "success"]
    t = now()
    within = lambda r, days: ts(r["updated_at"]) >= t - timedelta(days=days)

    freq = [0] * FREQ_DAYS
    for r in ok:
        d = (t.date() - ts(r["updated_at"]).date()).days
        if 0 <= d < FREQ_DAYS:
            freq[FREQ_DAYS - 1 - d] += 1

    leads = []
    for r in ok[:10]:
        head = ts(((r.get("head_commit") or {}).get("timestamp")))
        done = ts(r["updated_at"])
        if head and done and done >= head:
            leads.append((done - head).total_seconds() / 60)
    lead_m = round(statistics.median(leads)) if leads else None

    window = [r for r in runs if within(r, CFR_WINDOW_DAYS)]
    failed = [r for r in window if r.get("conclusion") in ("failure", "timed_out", "startup_failure")]
    cfr = round(100 * len(failed) / len(window), 1) if window else None

    # time to restore: each failure to the next success after it, oldest first
    restores, pending = [], None
    for r in reversed(runs):
        if r.get("conclusion") in ("failure", "timed_out", "startup_failure"):
            pending = pending or ts(r["updated_at"])
        elif r.get("conclusion") == "success" and pending:
            restores.append((ts(r["updated_at"]) - pending).total_seconds() / 60)
            pending = None
    mttr = round(statistics.mean(restores)) if restores else None

    return {
        "deploys": sum(1 for r in ok if within(r, DEPLOY_WINDOW_DAYS)),
        "freq": freq,
        "lastDeploy": ago(ts(ok[0]["updated_at"])) if ok else "never",
        "leadM": lead_m,
        "lead": humanize(lead_m),
        "cfr": cfr,
        "mttr": humanize(mttr),
    }


# ---------------------------------------------------------------- adapters
# One function per system that owns values. Each takes the instance record as it
# stands and returns the fields it owns. Keep them small and side-effect free;
# anything that needs a token reads it from the environment.


def adapter_manual(record, field, spec):
    """Value is maintained by a human in the data file. Carry it through."""
    return record.get(field)


def adapter_github_actions(record, field, spec):
    """Pipeline stage states and DORA figures from workflow runs on the default branch."""
    if not gh_available():
        return record.get(field)          # no gh / no token in this context: keep last known
    repo = record.get("path")
    if not repo or gh_api(f"repos/{repo}") is None:
        return record.get(field)          # repo not on GitHub (yet): keep last known
    pipeline = record.get("pipeline") or {}
    if field == "stages":
        return {s: stage_state(runs_of(repo, pipeline.get(s))) for s in STAGES}
    if field == "stageLinks":             # the run that put each stage in its current state
        links = {}
        for s in STAGES:
            runs = runs_of(repo, pipeline.get(s))
            if runs and runs[0].get("html_url"):
                links[s] = runs[0]["html_url"]
        return links
    if field == "auto":
        stages = {s: stage_state(runs_of(repo, pipeline.get(s))) for s in STAGES}
        return round(100 * sum(1 for v in stages.values() if v != "idle") / len(STAGES))
    metrics = deploy_metrics(repo, pipeline.get("deploy"))
    return metrics.get(field, record.get(field))


def adapter_github_deployments(record, field, spec):
    """Deployed version and health per environment, from GitHub Deployments."""
    if not gh_available():
        return record.get(field)
    repo = record.get("path")
    if not repo or gh_api(f"repos/{repo}") is None:
        return record.get(field)
    env_map = record.get("envMap") or {}
    slots = list((record.get("env") or {}).keys()) or ["dev", "test", "stage", "prod"]
    versions = {s: None for s in slots}
    states = {s: "none" for s in slots}
    deployments = gh_api(f"repos/{repo}/deployments?per_page=50") or []
    seen = set()
    for d in deployments:                 # newest first; first hit per environment wins
        env = d.get("environment")
        slot = env_map.get(env)
        if not slot or env in seen or slot not in versions:
            continue
        seen.add(env)
        statuses = gh_api(f"repos/{repo}/deployments/{d['id']}/statuses?per_page=1") or []
        state = (statuses[0].get("state") if statuses else None)
        ref = d.get("ref") or ""
        versions[slot] = ref if ref and not ref.startswith("refs/heads/") and ref != "main" else (d.get("sha") or "")[:7]
        states[slot] = {"success": "ok", "inactive": "ok", "failure": "crit", "error": "crit",
                        "in_progress": "run", "queued": "run", "pending": "run"}.get(state, "warn")
    return versions if field == "env" else states


def adapter_github_dependabot(record, field, spec):
    """Open vulnerability counts by severity, from Dependabot alerts."""
    if not gh_available():
        return record.get(field)
    repo = record.get("path")
    alerts = gh_api(f"repos/{repo}/dependabot/alerts?state=open&per_page=100") if repo else None
    if alerts is None:                    # disabled on the repo, or repo absent: keep last known
        return record.get(field)
    counts = {"c": 0, "h": 0, "m": 0}
    for a in alerts:
        sev = ((a.get("security_advisory") or {}).get("severity") or "").lower()
        key = {"critical": "c", "high": "h", "medium": "m"}.get(sev)
        if key:
            counts[key] += 1
    return counts


ADAPTERS = {
    "manual": adapter_manual,
    "github_actions": adapter_github_actions,
    "github_deployments": adapter_github_deployments,
    "github_dependabot": adapter_github_dependabot,
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
            if rec.get(field) != value:
                if dry_run:
                    print(f"  {rec.get('name')}.{field}: {json.dumps(rec.get(field))} -> {json.dumps(value)}")
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
