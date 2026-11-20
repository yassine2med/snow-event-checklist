import json
from datetime import datetime

import pytest

from snowlist.cli import main
from snowlist.core import ChecklistError, Task, blocked_by, classify, load_checklist, parse_time, timeline, validate

START = datetime(2026, 1, 24, 18, 0)


def t(id, hours, deps=(), owner="o", title="x"):
    return Task(id, title, owner, hours, tuple(deps))


def test_example_loads_and_is_valid():
    event, tasks = load_checklist("examples/snow_event.json")
    assert event == "Winter storm response" and len(tasks) == 11
    assert validate(tasks) == []


def test_due_time_is_offset_from_start():
    assert t("a", -8).due(START) == datetime(2026, 1, 24, 10, 0)


def test_timeline_sorted():
    order = [task.id for _, task in timeline([t("b", 2), t("a", -2)], START)]
    assert order == ["a", "b"]


def test_duplicate_id():
    assert "duplicate id 'a'" in validate([t("a", 1), t("a", 2)])


def test_unknown_dependency():
    assert any("unknown task 'zzz'" in p for p in validate([t("a", 1, ["zzz"])]))


def test_dependency_due_later_is_flagged():
    problems = validate([t("a", 5), t("b", 1, ["a"])])
    assert any("due before its dependency" in p for p in problems)


def test_cycle_detected():
    problems = validate([t("a", 1, ["b"]), t("b", 1, ["a"])])
    assert any(p.startswith("circular dependency") for p in problems)


def test_empty_owner_and_title():
    problems = validate([Task("a", " ", "", 0)])
    assert "a: owner is empty" in problems and "a: title is empty" in problems


def test_classify_states():
    task = t("a", -2)
    assert classify(task, START, datetime(2026, 1, 24, 17, 0), {"a"}) == "DONE"
    assert classify(task, START, datetime(2026, 1, 24, 17, 0), set()) == "OVERDUE"
    assert classify(task, START, datetime(2026, 1, 24, 14, 30), set()) == "DUE SOON"
    assert classify(task, START, datetime(2026, 1, 23, 8, 0), set()) == "UPCOMING"


def test_blocked_by():
    assert blocked_by(t("c", 1, ["a", "b"]), {"a"}) == ["b"]


def test_parse_time_error():
    with pytest.raises(ChecklistError):
        parse_time("Jan 24")


def test_bad_json_file(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{nope")
    with pytest.raises(ChecklistError, match="not valid JSON"):
        load_checklist(str(p))


def test_task_needs_numeric_due_hours(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"tasks": [{"id": "a", "due_hours": "soon"}]}))
    with pytest.raises(ChecklistError, match="must be a number"):
        load_checklist(str(p))


def test_cli_validate_codes(capsys):
    assert main(["validate", "examples/snow_event.json"]) == 0
    assert main(["validate", "examples/bad_checklist.json"]) == 1
    assert main(["validate", "none.json"]) == 2


def test_cli_plan(capsys):
    assert main(["plan", "examples/snow_event.json", "--start", "2026-01-24 18:00"]) == 0
    assert "11 tasks" in capsys.readouterr().out


def test_cli_status_overdue_and_done_file(capsys, tmp_path):
    done = tmp_path / "d.json"
    done.write_text(json.dumps(["forecast"]))
    args = ["status", "examples/snow_event.json", "--start", "2026-01-24 18:00", "--now", "2026-01-23 10:00",
            "--done-file", str(done)]
    assert main(args) == 1
    out = capsys.readouterr().out
    assert "OVERDUE" in out and "1 done" in out


def test_cli_status_rejects_unknown_done_id(capsys):
    code = main(["status", "examples/snow_event.json", "--start", "2026-01-24 18:00",
                 "--now", "2026-01-24 09:00", "--done", "nope"])
    assert code == 2
