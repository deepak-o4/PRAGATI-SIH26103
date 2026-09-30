"""Generate a clearly-labelled SYNTHETIC_DEMO dataset in the PAIMANA-style column layout.

This is NOT official data. Every row carries origin=SYNTHETIC_DEMO and project codes start with 'DEMO-'.
Deterministic (seeded). Real data: place PAIMANA-style exports in data/raw/ and use the ingestion API/CLI.
"""
import csv, random, sys
from datetime import date, timedelta
from pathlib import Path

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "data" / "sample"
OUT.mkdir(parents=True, exist_ok=True)
rnd = random.Random(20260930)

SECTORS = {
    "Roads and Highways": ("Ministry of Road Transport and Highways", "NHAI"),
    "Railways": ("Ministry of Railways", "Indian Railways"),
    "Power": ("Ministry of Power", "State Power Utility"),
    "Petroleum": ("Ministry of Petroleum and Natural Gas", "Public Sector Undertaking"),
    "Urban Development": ("Ministry of Housing and Urban Affairs", "Metro Rail Corporation"),
    "Ports and Shipping": ("Ministry of Ports, Shipping and Waterways", "Port Authority"),
}
STATES = {  # state: (lat, lon) approximate centroid
    "Uttar Pradesh": (26.85, 80.91), "Maharashtra": (19.75, 75.71), "Karnataka": (15.32, 75.71),
    "Gujarat": (22.26, 71.19), "Tamil Nadu": (11.13, 78.66), "Rajasthan": (27.02, 74.22),
    "Madhya Pradesh": (22.97, 78.66), "Bihar": (25.10, 85.31), "Odisha": (20.95, 85.10),
    "Assam": (26.20, 92.94),
}
ISSUES = ["LAND", "ENVIRONMENT_CLEARANCE", "FUNDING", "CONTRACTOR", "PROCUREMENT", "UTILITY_SHIFTING",
          "LEGAL", "DESIGN", "MATERIAL", "LABOUR", "WEATHER", "APPROVAL"]
AS_OF = date(2026, 9, 1)
N, MONTHS = 60, 18

def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)

projects, snaps, miles, issues = [], [], [], []
for i in range(1, N + 1):
    code = f"DEMO-{i:04d}"
    sector = rnd.choice(list(SECTORS)); ministry, agency = SECTORS[sector]
    state = rnd.choice(list(STATES)); lat, lon = STATES[state]
    orig = round(rnd.lognormvariate(6.2, 0.9), 1) + 150
    dur = rnd.randint(36, 96)
    start = add_months(AS_OF, -rnd.randint(24, 60))
    orig_end = add_months(start, dur)
    health = rnd.choices(["good", "watch", "bad"], [0.45, 0.35, 0.20])[0]
    slip_m = {"good": rnd.randint(0, 3), "watch": rnd.randint(4, 14), "bad": rnd.randint(15, 36)}[health]
    rev_end = add_months(orig_end, slip_m)
    cost_up = {"good": rnd.uniform(0, 0.05), "watch": rnd.uniform(0.05, 0.2), "bad": rnd.uniform(0.2, 0.6)}[health]
    rev = round(orig * (1 + cost_up), 1)
    elapsed = max(1, (AS_OF.year - start.year) * 12 + AS_OF.month - start.month)
    plan_total = max(1, (rev_end.year - start.year) * 12 + rev_end.month - start.month)
    base_speed = {"good": 1.05, "watch": 0.8, "bad": 0.55}[health] * 100 / plan_total
    prog = 0.0; exp = 0.0; hist = []
    for k in range(MONTHS, 0, -1):
        m = add_months(AS_OF, -k)
        if m < start: continue
        stall = health == "bad" and rnd.random() < 0.3
        prog = min(99.0, prog + (0 if stall else max(0, rnd.gauss(base_speed, base_speed * 0.3))))
        exp_pct = min(100, prog * rnd.uniform(0.95, 1.35 if health != "bad" else 1.7))
        hist.append((m, round(prog, 1), round(exp_pct / 100 * rev, 1)))
    # snapshots earlier than the first month are simply absent (NULL, not fabricated)
    if not hist: hist = [(add_months(AS_OF, -1), 1.0, round(0.01 * rev, 1))]
    cur_prog, cur_exp = hist[-1][1], hist[-1][2]
    lat_j, lon_j = lat + rnd.uniform(-2.5, 2.5), lon + rnd.uniform(-2.5, 2.5)
    projects.append([code, f"DEMO {sector} Project {i:02d}", sector, ministry, "", agency, state, "", "Infrastructure",
                     "Synthetic demonstration project", orig, rev, cur_exp, start, orig_end, rev_end, cur_prog,
                     round(cur_exp / rev * 100, 1), "UNDER_CONSTRUCTION", round(lat_j, 4), round(lon_j, 4), "SYNTHETIC_DEMO"])
    for m, pp, ee in hist:
        snaps.append([code, m, pp, round(ee / rev * 100, 1), ee, rev, rev_end, "", "", "synthetic-generator", "SYNTHETIC_DEMO"])
    for j, nm in enumerate(["Land / site handover", "Design approval", "Main construction", "Testing & commissioning"]):
        ps = add_months(start, int(plan_total * j / 4)); pe = add_months(start, int(plan_total * (j + 1) / 4))
        thr = 25 * (j + 1)
        done = cur_prog >= thr
        ae = add_months(pe, rnd.randint(0, 6 if health != "good" else 1)) if done else None
        if ae and ae > AS_OF: ae = AS_OF
        comp = 100 if done else max(0, min(99, (cur_prog - 25 * j) * 4))
        miles.append([code, nm, ps, pe, ps if comp > 0 else "", ae or "", round(comp, 1), miles and j and f"{['Land / site handover','Design approval','Main construction'][j-1]}" or "", 1])
    n_iss = {"good": rnd.randint(0, 1), "watch": rnd.randint(1, 3), "bad": rnd.randint(2, 4)}[health]
    for _ in range(n_iss):
        t = rnd.choice(ISSUES); sev = rnd.choice(["MEDIUM", "HIGH"] + (["CRITICAL"] if health == "bad" else []))
        rep = add_months(AS_OF, -rnd.randint(1, 12))
        resolved = rnd.random() < 0.25
        issues.append([code, t, f"Synthetic {t.lower().replace('_', ' ')} bottleneck", sev, rep,
                       add_months(rep, rnd.randint(2, 8)), add_months(rep, 3) if resolved else "",
                       "Implementing agency", "RESOLVED" if resolved else "OPEN", "Schedule impact"])

def w(name, header, rows):
    with open(OUT / name, "w", newline="", encoding="utf-8") as fh:
        c = csv.writer(fh); c.writerow(header); c.writerows(rows)
w("projects.csv", ["project_code","project_name","sector","line_ministry","department","implementing_agency","state","district","project_type","description","original_cost_crore","revised_cost_crore","cumulative_expenditure_crore","start_date","original_end_date","revised_end_date","physical_progress_pct","financial_progress_pct","status","latitude","longitude","origin"], projects)
w("project_snapshots.csv", ["project_code","snapshot_month","physical_progress_pct","financial_progress_pct","cumulative_expenditure_crore","revised_cost_crore","revised_end_date","status","issues","source","origin"][:0] or ["project_code","snapshot_month","physical_progress_pct","financial_progress_pct","cumulative_expenditure_crore","revised_cost_crore","revised_end_date","status","issues","source","origin"], [r[:7] + ["", r[8], r[9], r[10]] if False else [r[0],r[1],r[2],r[3],r[4],r[5],r[6],"","",r[9],r[10]] for r in snaps])
w("project_milestones.csv", ["project_code","milestone_name","planned_start","planned_end","actual_start","actual_end","completion_percentage","dependency","weight"], miles)
w("project_issues.csv", ["project_code","issue_type","description","severity","reported_date","expected_resolution_date","actual_resolution_date","owner","status","impact"], issues)
(OUT / "SOURCE.md").write_text("# Sample data\n\n**SYNTHETIC_DEMO** - generated by `scripts/generate_demo_data.py` (seed 20260930). Not official; not PAIMANA data. Every row is tagged `origin=SYNTHETIC_DEMO`.\n", encoding="utf-8")
print(f"wrote {len(projects)} projects, {len(snaps)} snapshots, {len(miles)} milestones, {len(issues)} issues -> {OUT}")
