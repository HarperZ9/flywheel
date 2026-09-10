import json
from pathlib import Path

from desktop.tool import installed_launch_acceptance as ila

COMMIT = "276d399d37485ca63815cea1e629db06f123e839"
TOKEN = "secret-token-that-must-never-appear"


def make_install(root: Path) -> tuple[Path, str, str]:
    install = root / "Flywheel"
    (install / "engine").mkdir(parents=True)
    app = install / "flywheel_desktop.exe"
    engine = install / "engine" / "flywheel-gateway.exe"
    app.write_bytes(b"app")
    engine.write_bytes(b"engine")
    return install, ila.sha256_file(app), ila.sha256_file(engine)


def build_manifest(root: Path, install: Path, *, app_sha="", engine_sha="",
                   source=COMMIT, version="0.6.1") -> Path:
    app_path = install / "flywheel_desktop.exe"
    engine_path = install / "engine" / "flywheel-gateway.exe"
    app_sha = app_sha or (ila.sha256_file(app_path) if app_path.exists() else "")
    engine_sha = engine_sha or (ila.sha256_file(engine_path) if engine_path.exists() else "")
    path = root / "build-manifest.json"
    path.write_text(json.dumps({
        "schema": "flywheel.installed-build-manifest/v1",
        "source_commit": source,
        "version": version,
        "artifacts": {"app_sha256": app_sha, "engine_sha256": engine_sha},
        "trust_boundary": "operator_supplied_integrity_binding",
    }), encoding="utf-8")
    return path


def valid_registry(install: Path, *, version="0.6.1") -> ila.MetadataResult:
    return ila.MetadataResult("PASS", {
        "AppId": ila.APP_ID,
        "DisplayName": "Flywheel",
        "DisplayVersion": version,
        "InstallLocation": str(install),
        "registry_key": ila.APP_ID + "_is1",
    })


def valid_windows(install: Path) -> "FakeWindows":
    return FakeWindows(
        start=[ila.ShortcutRecord("Flywheel", install / "flywheel_desktop.exe")],
        registry=valid_registry(install),
    )


def config(tmp_path: Path, install: Path, **overrides) -> ila.HarnessConfig:
    manifest = overrides.pop("build_manifest", "auto")
    if manifest == "auto":
        manifest = build_manifest(tmp_path, install)
    values = {
        "install_root": install,
        "out": tmp_path / "receipt.json",
        "run_id": "run-a",
        "source_commit_expected": COMMIT,
        "expected_version": "0.6.1",
        "build_manifest": manifest,
    }
    values.update(overrides)
    return ila.HarnessConfig(**values)


def run_harness(tmp_path, install, **kwargs):
    adapters = {
        "windows": kwargs.pop("windows", valid_windows(install)),
        "http": kwargs.pop("http", ila.NullHttpClient()),
        "process": kwargs.pop("process", ila.NullProcessController()),
    }
    cfg = config(tmp_path, install, **kwargs)
    return ila.AcceptanceHarness(
        cfg,
        fs=ila.LocalFilesystem(),
        windows=adapters["windows"],
        http=adapters["http"],
        process=adapters["process"],
        clock=ila.FixedClock("2026-09-10T00:00:00Z"),
    ).run()


def row(receipt, assertion_id):
    return next(r for r in receipt["assertions"] if r["id"] == assertion_id)


def valid_receipt(**assertion_states):
    rows = [{"id": aid, "state": assertion_states.get(aid, "PASS"), "severity": "critical"}
            for aid in ila.ASSERTION_IDS]
    phases = [{"id": pid, "state": "RECORDED",
               "assertion_ids": list(ila.PHASE_ASSERTIONS[pid])}
              for pid in ila.PHASE_IDS]
    return {"schema": ila.SCHEMA, "run_id": "run-a", "complete": True,
            "mode": "preflight", "assertions": rows, "phase_results": phases}


def status_doc(status="ok", live=1, total=1):
    return {"schema": "flywheel.desktop-status/v1", "status": status,
            "api_version": 1, "lanes_live": live, "lanes_total": total,
            "compatible": True}


def write_token(root: Path) -> Path:
    token_path = root / "validation" / "home" / "gateway.token"
    token_path.parent.mkdir(parents=True)
    token_path.write_text(TOKEN, encoding="utf-8")
    return token_path


class FakeWindows:
    def __init__(self, *, start=None, desktop=None, registry=None, protocol=None):
        self.start = start or []
        self.desktop = desktop
        self.registry = registry or ila.MetadataResult("UNTESTED")
        self.protocol = protocol or ila.MetadataResult("UNSUPPORTED")

    def start_menu_shortcuts(self):
        return self.start

    def desktop_shortcut(self):
        return self.desktop

    def uninstall_registry(self, app_id, install_root=None):
        return self.registry

    def protocol_registration(self, scheme):
        return self.protocol


class FakeHttp:
    def __init__(self, status=None, world=None, journey=None):
        self.status = status or []
        self.world = world or []
        self.journey = journey or []
        self.calls = []

    def get_json(self, url, token=None, timeout=2.0):
        self.calls.append(("GET", url))
        if token == TOKEN:
            token = "<token-present>"
        if url.endswith("/api/desktop/status"):
            return self.status.pop(0)
        if url.endswith("/api/world"):
            return self.world.pop(0)
        raise AssertionError(f"unexpected URL {url}")

    def post_json(self, url, payload, token=None, timeout=2.0):
        self.calls.append(("POST", url, payload))
        if token == TOKEN:
            token = "<token-present>"
        if url.endswith("/api/journeys/list") and payload == {}:
            return self.journey.pop(0)
        raise AssertionError(f"unexpected POST {url} {payload}")


class FakeProcess:
    def __init__(self, *, port_open_before=False, listener_pid=44, survivors=None):
        self.started = []
        self.cleaned = False
        self.port_open_before = port_open_before
        self.listener_pid = listener_pid
        self.survivors = survivors or []
        self.open_after_start = True

    def is_port_open(self, port):
        return self.port_open_before if not self.started else self.open_after_start

    def start_engine(self, exe, args, env, cwd, stdout, stderr):
        self.started.append((exe, args, env, cwd, stdout, stderr))
        return ila.ProcessHandle(pid=44)

    def listener_pids(self, port):
        return [self.listener_pid] if self.listener_pid is not None else []

    def cleanup(self, handle, port):
        self.cleaned = True
        self.open_after_start = False
        return self.survivors
