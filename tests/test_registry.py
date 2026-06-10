from ld2460.server.registry import ScreenRegistry


def _report(count):
    return {"count": count, "present": count > 0, "persons": []}


def test_update_and_snapshot_fields():
    r = ScreenRegistry(offline_after=10, drop_after=300)
    r.update("office", _report(2), now=100.0)
    snap = r.snapshot(now=100.0)
    assert len(snap) == 1
    s = snap[0]
    assert s["name"] == "office"
    assert s["report"]["count"] == 2
    assert s["online"] is True
    assert s["last_seen_age"] == 0.0


def test_online_flag_at_boundary():
    r = ScreenRegistry(offline_after=10, drop_after=300)
    r.update("a", _report(1), now=0.0)
    assert r.snapshot(now=10.0)[0]["online"] is True
    assert r.snapshot(now=10.1)[0]["online"] is False


def test_evict_stale_drops_after_drop_after():
    r = ScreenRegistry(offline_after=10, drop_after=300)
    r.update("a", _report(1), now=0.0)
    assert r.evict_stale(now=200.0) == []
    assert r.evict_stale(now=301.0) == ["a"]
    assert r.snapshot(now=301.0) == []


def test_multiple_screens_sorted():
    r = ScreenRegistry()
    r.update("zeta", _report(1), now=0.0)
    r.update("alpha", _report(0), now=0.0)
    assert [s["name"] for s in r.snapshot(now=0.0)] == ["alpha", "zeta"]
