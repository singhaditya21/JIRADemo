import json
from collections import Counter, defaultdict

with open('/Users/adityasingh/PersonalWork/JIRADemo/scratchpad/ITSM-records.json') as f:
    data = json.load(f)

records = data['records']
by_key = {r['key']: r for r in records}
problems = [r for r in records if r.get('issue_type') == 'Problem']

# Treat "problem-side links" as ALL links present on Problem records (they are all Problem/Incident type)
plinks = []  # (problem, link)
for p in problems:
    for l in p.get('links', []):
        plinks.append((p, l))

print("CHECK 1 count of problem-side links:", len(plinks), "(expected 83)")

# rel/dir distribution on problem side
dist = Counter((l.get('dir'), l.get('rel'), l.get('type')) for _, l in plinks)
print("Problem-side link dir/rel/type distribution:")
for k, v in dist.items():
    print("   ", k, "->", v)

# CHECK 3: targets resolve to Incident
non_incident = []
unresolved = []
for p, l in plinks:
    tgt = by_key.get(l.get('key'))
    if tgt is None:
        unresolved.append((p['key'], l.get('key')))
    elif tgt.get('issue_type') != 'Incident':
        non_incident.append((p['key'], l.get('key'), tgt.get('issue_type')))
print("\nCHECK 3 targets not resolving to Incident:", len(non_incident), non_incident[:20])
print("CHECK 3 targets unresolved (not in dataset):", len(unresolved), unresolved[:20])

# CHECK 2: incident reuse
inc_to_probs = defaultdict(set)
for p, l in plinks:
    inc_to_probs[l.get('key')].add(p['key'])
reused = {i: ps for i, ps in inc_to_probs.items() if len(ps) > 1}
print("\nCHECK 2 distinct incidents linked:", len(inc_to_probs))
print("CHECK 2 incidents linked to >1 problem:", len(reused))
for i, ps in list(reused.items())[:30]:
    print("    REUSED", i, "->", sorted(ps))

# CHECK 5: self links / dup pairs
self_links = [(p['key'], l.get('key')) for p, l in plinks if l.get('key') == p['key']]
pair_counts = Counter((p['key'], l.get('key')) for p, l in plinks)
dup_pairs = {k: v for k, v in pair_counts.items() if v > 1}
print("\nCHECK 5 self-links:", len(self_links), self_links[:20])
print("CHECK 5 duplicate (problem,incident) pairs:", len(dup_pairs), list(dup_pairs.items())[:20])

# CHECK 4: direction semantics.
# Spec expects: Problem side dir='outward' rel='causes'; Incident side dir='inward' rel='is caused by'.
prob_outward_causes = sum(1 for _, l in plinks if l.get('dir')=='outward' and l.get('rel')=='causes')
prob_inward_iscaused = sum(1 for _, l in plinks if l.get('dir')=='inward' and l.get('rel')=='is caused by')
print("\nCHECK 4 problem-side dir=outward rel=causes:", prob_outward_causes, "(spec expects 83)")
print("CHECK 4 problem-side dir=inward rel='is caused by':", prob_inward_iscaused)

# Now look at incident side reciprocity
inc_side_dist = Counter()
missing_back = []
for p, l in plinks:
    inc = by_key.get(l.get('key'))
    if inc is None:
        missing_back.append((p['key'], l.get('key'), 'NO_INCIDENT'))
        continue
    backs = [bl for bl in inc.get('links', []) if bl.get('key') == p['key']]
    if not backs:
        missing_back.append((p['key'], l.get('key'), 'NO_BACKLINK'))
        continue
    for bl in backs:
        inc_side_dist[(bl.get('dir'), bl.get('rel'))] += 1
print("CHECK 4 incident-side reciprocal dir/rel distribution:")
for k, v in inc_side_dist.items():
    print("    ", k, "->", v)
print("CHECK 4 missing reciprocal backlinks:", len(missing_back), missing_back[:20])

# Does spec's expected orientation (incident inward 'is caused by') hold?
inc_inward_iscaused = inc_side_dist.get(('inward','is caused by'), 0)
inc_outward_causes = inc_side_dist.get(('outward','causes'), 0)
print("CHECK 4 incident-side inward 'is caused by':", inc_inward_iscaused, "(spec expects 83)")
print("CHECK 4 incident-side outward 'causes':", inc_outward_causes)

# CHECK 6: same tower + root-cause match
tower_mismatch = []
rc_match = 0
rc_total = 0
for p, l in plinks:
    inc = by_key.get(l.get('key'))
    if inc is None:
        continue
    if p.get('tower') != inc.get('tower'):
        tower_mismatch.append((p['key'], p.get('tower'), l.get('key'), inc.get('tower')))
    rc_total += 1
    if p.get('root_cause') == inc.get('root_cause'):
        rc_match += 1
print("\nCHECK 6 tower mismatches:", len(tower_mismatch), tower_mismatch[:20])
print(f"CHECK 6 root-cause match rate: {rc_match}/{rc_total} = {(rc_match/rc_total*100 if rc_total else 0):.1f}%")

# CHECK 7: footprint
probs_with_links = sum(1 for p in problems if p.get('links'))
print("\nCHECK 7 problems-with-links:", probs_with_links, "(expected 13)")
print("CHECK 7 incidents-linked distinct:", len(inc_to_probs), "(expected 83)")
print("CHECK 7 total links:", len(plinks), "(expected 83)")
print(f"CHECK 7 avg links/problem: {len(plinks)/len(problems):.2f} (expected ~6.4)")
print("\nPer-problem counts:")
for p in sorted(problems, key=lambda x: x['key']):
    print(f"   {p['key']}: {len(p.get('links',[]))} links, tower={p.get('tower')}")
