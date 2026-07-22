import json, sys
from collections import Counter, defaultdict

with open('/Users/adityasingh/PersonalWork/JIRADemo/scratchpad/ITSM-records.json') as f:
    data = json.load(f)

records = data['records']
by_key = {r['key']: r for r in records}
type_counts = Counter(r.get('issue_type') for r in records)
print("=== DATASET ===")
print("total records:", len(records))
print("issue_type distribution:", dict(type_counts))

problems = [r for r in records if r.get('issue_type') == 'Problem']
print("\nProblem records:", len(problems))
print("Problem keys:", sorted(p['key'] for p in problems))

# ---------- Check 1: count problem-side links ----------
# Interpret "problem-side links" as the links on Problem records that represent the causes relation
# We'll examine all links on problems first.
print("\n=== ALL LINK TYPES/RELS ON PROBLEM RECORDS ===")
rel_counter = Counter()
for p in problems:
    for l in p.get('links', []):
        rel_counter[(l.get('rel'), l.get('dir'), l.get('type'))] += 1
for k, v in rel_counter.items():
    print(f"  rel={k[0]!r} dir={k[1]!r} type={k[2]!r} -> {v}")

# Total links on problems
total_problem_links = sum(len(p.get('links', [])) for p in problems)
print("\nTotal links (all) on Problem records:", total_problem_links)

# ---------- Define the "problem->incident causes" links ----------
# Per spec: on the Problem the link dir is 'outward' rel 'causes'
cause_links = []  # list of (problem, link)
for p in problems:
    for l in p.get('links', []):
        if l.get('dir') == 'outward' and l.get('rel') == 'causes':
            cause_links.append((p, l))

print("\n=== CHECK 1: problem-side 'causes/outward' links ===")
print("count of outward/causes links across 13 Problems:", len(cause_links))
print("EXPECTED: 83")

# Also check: how many outward/causes links point to an Incident target?
cause_links_to_incident = []
cause_links_to_nonincident = []
cause_links_unresolved = []
for p, l in cause_links:
    tk = l.get('key')
    tgt = by_key.get(tk)
    if tgt is None:
        cause_links_unresolved.append((p['key'], tk, l.get('issue_type')))
    elif tgt.get('issue_type') == 'Incident':
        cause_links_to_incident.append((p['key'], tk))
    else:
        cause_links_to_nonincident.append((p['key'], tk, tgt.get('issue_type')))

print("  -> resolve to Incident:", len(cause_links_to_incident))
print("  -> resolve to NON-incident:", len(cause_links_to_nonincident), cause_links_to_nonincident[:20])
print("  -> unresolved (target key not in dataset):", len(cause_links_unresolved), cause_links_unresolved[:20])

# ---------- Check 3: every problem's linked neighbour resolves to issue_type Incident ----------
print("\n=== CHECK 3: neighbour issue_type ===")
# link.issue_type field vs resolved record issue_type
mismatch_field_vs_record = []
for p, l in cause_links:
    tgt = by_key.get(l.get('key'))
    if tgt is not None and l.get('issue_type') != tgt.get('issue_type'):
        mismatch_field_vs_record.append((p['key'], l.get('key'), l.get('issue_type'), tgt.get('issue_type')))
print("link.issue_type vs record.issue_type mismatches:", len(mismatch_field_vs_record), mismatch_field_vs_record[:20])

# ---------- Check 2: no incident linked to >1 problem ----------
print("\n=== CHECK 2: incident reuse across problems ===")
incident_to_problems = defaultdict(set)
for p, l in cause_links:
    incident_to_problems[l.get('key')].add(p['key'])
reused = {inc: probs for inc, probs in incident_to_problems.items() if len(probs) > 1}
print("distinct incidents linked:", len(incident_to_problems))
print("incidents linked to >1 problem:", len(reused))
for inc, probs in list(reused.items())[:20]:
    print("   ", inc, "->", sorted(probs))

# ---------- Check 5: no self-link, no duplicate pairs ----------
print("\n=== CHECK 5: self-links & duplicate pairs ===")
self_links = [(p['key'], l.get('key')) for p, l in cause_links if l.get('key') == p['key']]
print("self-links:", len(self_links), self_links[:20])
pair_counter = Counter((p['key'], l.get('key')) for p, l in cause_links)
dup_pairs = {pair: c for pair, c in pair_counter.items() if c > 1}
print("duplicate (problem,incident) pairs:", len(dup_pairs))
for pair, c in list(dup_pairs.items())[:20]:
    print("   ", pair, "x", c)

# ---------- Check 4: direction reciprocity ----------
print("\n=== CHECK 4: direction reciprocity (inward 'is caused by' on incident) ===")
missing_reciprocal = []
bad_reciprocal = []
for p, l in cause_links:
    inc = by_key.get(l.get('key'))
    if inc is None:
        missing_reciprocal.append((p['key'], l.get('key'), 'INCIDENT_NOT_IN_DATASET'))
        continue
    # find a link on the incident pointing back to this problem inward
    back = [bl for bl in inc.get('links', []) if bl.get('key') == p['key']]
    if not back:
        missing_reciprocal.append((p['key'], l.get('key'), 'NO_BACKLINK'))
        continue
    ok = False
    for bl in back:
        if bl.get('dir') == 'inward' and bl.get('rel') == 'is caused by':
            ok = True
    if not ok:
        bad_reciprocal.append((p['key'], l.get('key'), [(bl.get('dir'), bl.get('rel')) for bl in back]))
print("missing reciprocal backlinks:", len(missing_reciprocal), missing_reciprocal[:20])
print("wrong dir/rel reciprocal:", len(bad_reciprocal), bad_reciprocal[:20])

# ---------- Check 6: same-tower + root cause match rate ----------
print("\n=== CHECK 6: same-tower & root-cause match ===")
tower_mismatch = []
rc_match = 0
rc_total = 0
for p, l in cause_links:
    inc = by_key.get(l.get('key'))
    if inc is None:
        continue
    if p.get('tower') != inc.get('tower'):
        tower_mismatch.append((p['key'], p.get('tower'), l.get('key'), inc.get('tower')))
    rc_total += 1
    if p.get('root_cause') == inc.get('root_cause'):
        rc_match += 1
print("tower mismatches:", len(tower_mismatch), tower_mismatch[:20])
print(f"root-cause match rate: {rc_match}/{rc_total} = {(rc_match/rc_total*100 if rc_total else 0):.1f}%")

# ---------- Check 7: footprint ----------
print("\n=== CHECK 7: footprint reconciliation ===")
problems_with_links = sum(1 for p in problems if any(l.get('dir')=='outward' and l.get('rel')=='causes' for l in p.get('links',[])))
incidents_linked = len(incident_to_problems)
total_cause = len(cause_links)
print("problems-with-links:", problems_with_links, "(expected 13)")
print("incidents-linked (distinct):", incidents_linked, "(expected 83)")
print("total cause links:", total_cause, "(expected 83)")
print(f"avg links per problem: {total_cause/len(problems):.2f}" if problems else "n/a", "(expected ~6.4)")

# Per-problem breakdown
print("\nPer-problem outward/causes link counts:")
for p in sorted(problems, key=lambda x: x['key']):
    c = sum(1 for l in p.get('links',[]) if l.get('dir')=='outward' and l.get('rel')=='causes')
    print(f"  {p['key']}: {c} (tower={p.get('tower')})")
