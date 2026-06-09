from ld2460.model import Motion
from ld2460.tracking import Tracker


def _feed(tracker, sequence):
    """sequence: list of (now, [(x, y), ...]); returns the last PresenceReport."""
    report = None
    for now, targets in sequence:
        report = tracker.update(targets, now)
    return report


def test_no_targets_no_presence():
    t = Tracker()
    report = t.update([], now=0.0)
    assert report.present is False
    assert report.count == 0


def test_count_matches_targets():
    t = Tracker()
    report = t.update([(0.0, 2.0), (1.0, 3.0)], now=0.0)
    assert report.count == 2
    assert report.present is True


def test_static_target():
    t = Tracker(min_samples=3)
    seq = [(i * 0.1, [(0.0, 2.0)]) for i in range(5)]
    report = _feed(t, seq)
    assert report.persons[0].motion is Motion.STATIC


def test_approaching_target():
    t = Tracker(min_samples=3)
    seq = [(i * 0.1, [(0.0, 3.0 - i * 0.4)]) for i in range(5)]
    report = _feed(t, seq)
    assert report.persons[0].motion is Motion.APPROACHING


def test_moving_away_target():
    t = Tracker(min_samples=3)
    seq = [(i * 0.1, [(0.0, 1.0 + i * 0.4)]) for i in range(5)]
    report = _feed(t, seq)
    assert report.persons[0].motion is Motion.MOVING_AWAY


def test_track_id_is_stable():
    t = Tracker()
    r0 = t.update([(0.0, 2.0)], now=0.0)
    r1 = t.update([(0.05, 2.05)], now=0.1)
    assert r0.persons[0].id == r1.persons[0].id


def test_track_ages_out():
    t = Tracker(age_out=0.3)
    t.update([(0.0, 2.0)], now=0.0)
    report = t.update([], now=1.0)
    assert report.count == 0


def test_unknown_until_min_samples():
    t = Tracker(min_samples=3)
    report = t.update([(0.0, 2.0)], now=0.0)
    assert report.persons[0].motion is Motion.UNKNOWN


def test_same_now_repeated_call_clears_absent_targets():
    # Two update() calls sharing the same `now` must not report a stale track.
    t = Tracker()
    t.update([(0.0, 2.0)], now=5.0)
    report = t.update([], now=5.0)
    assert report.count == 0
    assert report.present is False


def test_gate_rejection_spawns_new_id():
    t = Tracker(gate=1.0)
    r0 = t.update([(0.0, 2.0)], now=0.0)
    r1 = t.update([(0.0, 5.0)], now=0.1)  # jumped 3 m, beyond gate
    assert r1.persons[0].id != r0.persons[0].id


def test_two_targets_keep_separate_ids():
    t = Tracker()
    r0 = t.update([(0.0, 2.0), (2.0, 2.0)], now=0.0)
    r1 = t.update([(0.1, 2.0), (2.1, 2.0)], now=0.1)
    assert {p.id for p in r0.persons} == {p.id for p in r1.persons}
    near0 = min(r0.persons, key=lambda p: p.x).id
    near1 = min(r1.persons, key=lambda p: p.x).id
    assert near0 == near1


def test_new_and_aged_out_simultaneously():
    t = Tracker(age_out=0.3)
    r0 = t.update([(0.0, 2.0)], now=0.0)
    old_id = r0.persons[0].id
    r1 = t.update([(3.0, 3.0)], now=1.0)  # old aged out, new target appears
    assert r1.count == 1
    assert r1.persons[0].id != old_id
