import threading

from agent_support_resolution.audit import AuditLog


def test_record_and_read_back(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    log.record("T1", "ticket_received", "intake", {"a": 1})
    log.record("T1", "sent", "send", {})
    log.record("T2", "ticket_received", "intake", {})
    events = log.events_for("T1")
    assert [e.event_type for e in events] == ["ticket_received", "sent"]
    assert events[0].detail == {"a": 1}
    assert len(log.all_events()) == 3


def test_missing_file_reads_empty(tmp_path):
    log = AuditLog(tmp_path / "nope.jsonl")
    assert log.events_for("T1") == []
    assert log.all_events() == []


def test_concurrent_appends_do_not_corrupt(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")

    def write_many(n):
        for i in range(25):
            log.record(f"T{n}", "evt", "node", {"i": i})

    threads = [threading.Thread(target=write_many, args=(n,)) for n in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    # Every line must be valid JSON (all_events parses them) and complete.
    assert len(log.all_events()) == 100
