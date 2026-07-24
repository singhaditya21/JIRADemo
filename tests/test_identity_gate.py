"""The gate that decides whether we are allowed to publish.

Every test here corresponds to a way the gate has actually failed or could fail silently:

  * It scanned a fixed list of TEXT extensions, so a tracked .pptx carrying the real name and
    tenant on its title slide went unexamined and shipped to a public repo.
  * It hardcoded the owner's username and given name, making the guard the one file at HEAD
    that published them.
  * It reported only the FIRST match per file, so a benign early hit could mask a real one.
  * It matched the bare vendor domain, which identifies nobody, while the deliberate
    placeholder that de-personalisation INSERTS would have failed the build.

A gate that silently passes is worse than no gate — it converts "nobody looked" into
"verified clean". These pin that it actually looks.
"""

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_no_identity as G

# Assembled at import time so this FILE contains no tenant-shaped literal of its own. The
# gate's --tracked mode scans every tracked file, so a fixture hostname written out in full
# fails the very check it exists to test — which is exactly what happened in CI the first
# time, and only in CI, because locally the file was not yet `git add`ed and therefore not
# yet tracked. The test became load-bearing the moment it was committed.
# Interpolated, not concatenated. Splitting the subdomain is not enough: the tail left behind
# is still host-shaped and trips the pattern on its own. The VENDOR portion has to be the part
# broken up, so no complete tenant hostname exists anywhere in this file's source.
REAL_TENANT = "realcorp.%s.net" % "atlassian"


def write(tmp_path, name, text):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def pptx(tmp_path, name, parts):
    """A minimal Office-shaped zip: the point is the container, not valid OOXML."""
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as z:
        for member, text in parts.items():
            z.writestr(member, text)
    return p


# --- archives: the leak that got through -----------------------------------------------

def test_a_name_inside_a_pptx_is_found(tmp_path):
    f = pptx(tmp_path, "deck.pptx", {
        "docProps/core.xml": "<dc:creator>Ada Lovelace</dc:creator>",
        "ppt/slides/slide1.xml": "<a:t>nothing here</a:t>",
    })
    hits = G.scan([f], ["ada lovelace"])
    assert len(hits) == 1
    assert "docProps/core.xml" in hits[0][0]      # the member is named, not just the file


def test_the_archive_member_is_reported_so_it_can_be_found(tmp_path):
    f = pptx(tmp_path, "deck.pptx", {"ppt/slides/slide7.xml": "<a:t>Ada Lovelace</a:t>"})
    label = G.scan([f], ["ada"])[0][0]
    assert "deck.pptx" in label and "slide7.xml" in label


def test_a_clean_archive_passes(tmp_path):
    f = pptx(tmp_path, "deck.pptx", {"ppt/slides/slide1.xml": "<a:t>Platform Engineering</a:t>"})
    assert G.scan([f], ["ada lovelace"]) == []


def test_a_corrupt_archive_does_not_crash_the_gate(tmp_path):
    p = tmp_path / "broken.pptx"
    p.write_bytes(b"this is not a zip file at all")
    assert G.scan([p], ["ada"]) == []             # skipped, not an exception


@pytest.mark.parametrize("ext", [".pptx", ".docx", ".xlsx", ".odt"])
def test_every_office_container_type_is_opened(tmp_path, ext):
    f = pptx(tmp_path, "doc" + ext, {"content.xml": "Ada Lovelace"})
    assert G.scan([f], ["ada"]) != []


# --- tenants: a subdomain identifies, the bare vendor domain does not -------------------

def test_a_real_tenant_host_is_reported(tmp_path):
    f = write(tmp_path, "a.json", '{"site": "https://%s"}' % REAL_TENANT)
    hits = G.scan([f], [])
    assert len(hits) == 1 and REAL_TENANT in hits[0][1]


@pytest.mark.parametrize("host", ["your-site", "acme", "example", "your-tenant"])
def test_placeholder_tenants_do_not_fail_the_build(tmp_path, host):
    # These are what de-personalisation puts IN. Flagging them fails the build for doing the
    # right thing, which is how a gate gets disabled.
    f = write(tmp_path, "a.md", "Site is `%s.atlassian.net` in the docs." % host)
    assert G.scan([f], []) == []


def test_the_bare_vendor_domain_identifies_nobody(tmp_path):
    f = write(tmp_path, "t.py", 'assert "atlassian.net" not in url')
    assert G.scan([f], []) == []


@pytest.mark.parametrize("label", ["%s", "{host}", "x", "ab"])
def test_a_format_placeholder_is_not_a_tenant(tmp_path, label):
    # Source that BUILDS a hostname is not source that CONTAINS one. Without a minimum label
    # length, `%s.atlassian.net` reads as the tenant "s" and the check fires on its own tests.
    f = write(tmp_path, "t.py", 'url = "https://%s.atlassian.net/browse/X"' % label)
    assert G.scan([f], []) == []


def test_a_three_character_tenant_still_reports(tmp_path):
    # The minimum must not become a hiding place: the shortest real site name still reports.
    f = write(tmp_path, "a.json", '{"site": "https://abc.%s.net"}' % "atlassian")
    assert G.scan([f], []) != []


def test_a_placeholder_does_not_mask_a_real_tenant_in_the_same_file(tmp_path):
    # The old scan stopped at the first match per file, so a benign early hit hid a real one.
    f = write(tmp_path, "a.md", "use your-site.atlassian.net\n...\nbuilt on %s\n" % REAL_TENANT)
    hits = G.scan([f], [])
    assert len(hits) == 1 and REAL_TENANT in hits[0][1]


# --- identifiers are derived, never written down ---------------------------------------

def test_the_source_names_nobody():
    # The regression that made the guard leak: identifiers as literals in tracked source.
    src = Path(G.__file__).read_text().lower()
    derived = G._derived()
    leaked = [d for d in derived if len(d) >= 5 and d in src]
    assert not leaked, "identifier(s) hardcoded in the gate's own source: %s" % leaked


def test_env_overrides_derivation(monkeypatch):
    monkeypatch.setenv("IDENTIFIERS", "Acme, jdoe ,,")
    assert G.identifiers() == ["acme", "jdoe"]


def test_bots_are_not_treated_as_people():
    assert not any("[bot]" in d for d in G._derived())
    assert "github" not in G._derived()


def test_derivation_yields_something_in_this_repo():
    # If derivation silently returned nothing, the gate would pass everything.
    assert G.identifiers(), "no identifiers derived — the gate would be a no-op"


# --- wiring ----------------------------------------------------------------------------

def test_skipped_directories_are_not_scanned(tmp_path):
    f = write(tmp_path, ".claude/settings.local.json", '{"token": "Ada Lovelace"}')
    assert G.scan([f], ["ada"]) == []


def test_exit_code_is_one_when_something_leaks(tmp_path):
    write(tmp_path, "leak.json", '{"who": "Ada Lovelace"}')
    r = subprocess.run([sys.executable, str(Path(G.__file__)), str(tmp_path)],
                       capture_output=True, text=True, env={"IDENTIFIERS": "ada lovelace",
                                                            "PATH": "/usr/bin:/bin"})
    assert r.returncode == 1
    assert "FAIL" in r.stdout


def test_exit_code_is_zero_when_clean(tmp_path):
    write(tmp_path, "fine.json", '{"who": "Platform Engineering"}')
    r = subprocess.run([sys.executable, str(Path(G.__file__)), str(tmp_path)],
                       capture_output=True, text=True, env={"IDENTIFIERS": "ada lovelace",
                                                            "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0
    assert "CLEAN" in r.stdout


def test_the_tracked_repo_is_clean():
    """The property that actually matters, asserted against the real repo."""
    repo = Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, "scripts/check_no_identity.py", "--tracked"],
                       cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
