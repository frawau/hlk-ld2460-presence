def test_public_api_exported():
    import ld2460

    expected = {
        "Motion",
        "Person",
        "PresenceReport",
        "Reporter",
        "Tracker",
        "FrameReader",
        "parse_report_frame",
        "build_report_frame",
        "enable_reporting",
        "disable_reporting",
        "restart",
        "run_pipeline",
        "iter_reports",
        "stream_presence",
    }
    for name in expected:
        assert hasattr(ld2460, name), name
    assert expected <= set(ld2460.__all__)
