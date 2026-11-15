import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from subsystem_doctor import (
    CheckResult,
    DoctorReport,
    run_doctor,
    ALL_CHECKS,
    _timed_check,
)


def test_check_result_dataclass():
    r = CheckResult(name="test", status="PASS", elapsed_ms=1.5, detail="ok")
    assert r.name == "test"
    d = r.to_dict()
    assert d["status"] == "PASS"
    assert "detail" in d


def test_check_result_no_detail():
    r = CheckResult(name="test", status="PASS")
    d = r.to_dict()
    assert "detail" not in d


def test_doctor_report_empty():
    report = DoctorReport()
    assert report.passed == 0
    assert report.failed == 0
    assert report.healthy is True


def test_doctor_report_counts():
    report = DoctorReport(checks=[
        CheckResult("a", "PASS"),
        CheckResult("b", "FAIL"),
        CheckResult("c", "SKIP"),
    ])
    assert report.passed == 1
    assert report.failed == 1
    assert report.skipped == 1
    assert report.healthy is False


def test_doctor_report_to_dict():
    report = DoctorReport(checks=[
        CheckResult("a", "PASS", 1.0),
    ])
    d = report.to_dict()
    assert "healthy" in d
    assert "checks" in d
    assert len(d["checks"]) == 1


def test_doctor_report_summary():
    report = DoctorReport(checks=[
        CheckResult("a", "PASS", 1.0, "ok"),
    ])
    s = report.summary()
    assert "HEALTHY" in s
    assert "[+] a" in s


def test_timed_check_pass():
    result = _timed_check("test", lambda: "ok")
    assert result.status == "PASS"
    assert result.detail == "ok"


def test_timed_check_fail():
    def fail():
        raise RuntimeError("broken")
    result = _timed_check("test", fail)
    assert result.status == "FAIL"
    assert "broken" in result.detail


def test_timed_check_import_error():
    def missing():
        raise ImportError("no such module")
    result = _timed_check("test", missing)
    assert result.status == "SKIP"


def test_all_checks_registered():
    assert len(ALL_CHECKS) >= 20


def test_run_doctor_subset():
    report = run_doctor(subset=["categories"])
    assert len(report.checks) == 1
    assert report.checks[0].name == "categories"
    assert report.checks[0].status == "PASS"


def test_run_doctor_full():
    report = run_doctor()
    assert report.passed >= 20
    assert report.healthy is True
