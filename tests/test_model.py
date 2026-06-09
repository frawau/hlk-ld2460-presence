from ld2460.model import Motion, Person, PresenceReport


def test_person_to_dict():
    p = Person(
        id=1, x=-1.5, y=2.3, distance=2.74, angle=-33.1, motion=Motion.APPROACHING
    )
    assert p.to_dict() == {
        "id": 1,
        "x": -1.5,
        "y": 2.3,
        "distance": 2.74,
        "angle": -33.1,
        "motion": "approaching",
    }


def test_presence_report_present_and_dict():
    p = Person(id=1, x=0.0, y=2.0, distance=2.0, angle=0.0, motion=Motion.STATIC)
    report = PresenceReport(timestamp=12.5, count=1, persons=[p])
    assert report.present is True
    d = report.to_dict()
    assert d["present"] is True
    assert d["count"] == 1
    assert d["persons"][0]["motion"] == "static"


def test_empty_report_not_present():
    report = PresenceReport(timestamp=0.0, count=0, persons=[])
    assert report.present is False
    assert report.to_dict()["persons"] == []
