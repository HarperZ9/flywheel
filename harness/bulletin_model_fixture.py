"""Owned synthetic A/B fixtures with sealed contracts and separate observation.

Pinned parent reads do not pin the child scripts' ordinary path writes. Those
trusted fixture processes and the supplied executable/dependency tree are part
of the trusted host; this wrapper does not provide a hostile-host sandbox.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import math
import os
from pathlib import Path
import re
import time
from urllib.parse import quote

from .bulletin_model_exchange import PrivateExchange
from .bulletin_observer import _Reader, _project, observe_handoff
from .bulletin_task_contract import validate_contract
from .bulletin_task_review import build_review
from .cross_harness_process import start_owned_process
from .evidence_json import canonical_bytes, strict_load_json
from .private_artifact_fs import open_artifact_root
from .strict_local_http import StrictLocalHTTPPolicy


class FixtureError(RuntimeError):
    pass


def _require(condition):
    if not condition:
        raise FixtureError("fixture_not_admitted")


def _token(value, size=128):
    return type(value) is str and bool(re.fullmatch(r"[A-Za-z0-9_-]{1," + str(size) + "}", value))


def _sha(value, size=64):
    return type(value) is str and bool(re.fullmatch(r"[a-f0-9]{" + str(size) + "}", value))


def _origin(value):
    return StrictLocalHTTPPolicy(value, frozenset({("GET", "/v1/feed")})).origin


class OwnedBulletinFixture:
    @classmethod
    def start(cls, *, slot, spec, repository, bulletin, dependencies, node_executable,
              python_executable, setup_timeout_seconds=120, launcher=start_owned_process,
              reader_factory=_Reader, observer=observe_handoff):
        fixture = cls()
        fixture.slot, fixture._processes, fixture._roots = slot, [], []
        fixture._recorded = set()
        fixture._read_used = fixture._observed = fixture._closed = False
        fixture._reader_factory, fixture._observer = reader_factory, observer
        try:
            _require(type(setup_timeout_seconds) in (int, float) and math.isfinite(setup_timeout_seconds)
                     and 0 < setup_timeout_seconds <= 120)
            fixture._deadline = time.monotonic() + setup_timeout_seconds
            fixture._spec = strict_load_json(canonical_bytes(spec), max_bytes=32768, max_depth=8)
            fixture._admit_spec()
            for path in (repository, bulletin, dependencies):
                _require(path.is_absolute())
                with open_artifact_root(path):
                    pass
            _require(all(p.is_absolute() and p.is_file() for p in (node_executable, python_executable)))
            source_out, native_out = slot.path / "source-a", slot.path / "native-b"
            fixture.config_path = slot.path / "gateway-config.json"
            _require(not any(os.path.lexists(p) for p in (source_out, native_out, fixture.config_path)))
            fixture._input_sha = slot.put("fixture-input.json", canonical_bytes(fixture._spec), max_bytes=32768)
            env = {k: v for k, v in os.environ.items() if k.upper() in
                   {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP"}}
            script = repository / "scripts" / "bulletin_eval" / "actor_worker_fixture.mjs"
            gateway = repository / "desktop" / "tool" / "bulletin_media_gateway_fixture.py"
            _require(script.is_file() and gateway.is_file())
            fixture._launch(launcher, (str(node_executable), str(script), "--bulletin", str(bulletin),
                "--dependencies", str(dependencies), "--out", str(source_out), "--input",
                str(slot.path / "fixture-input.json")), repository, env)
            fixture._wait(lambda: (source_out / "ready.json").exists())
            root = open_artifact_root(source_out)
            root.__enter__()
            fixture._roots.append(root)
            fixture._ready = strict_load_json(root.read_bytes("ready.json", max_bytes=8192), max_bytes=8192)
            fixture._admit_ready()
            native_root = PrivateExchange.create(native_out)
            fixture._roots.append(native_root)
            native_env = {**env, "USERPROFILE": str(native_out), "HOME": str(native_out)}
            fixture._launch(launcher, (str(python_executable), "-I", str(gateway), "--fixture-root", str(native_out),
                "--config", str(fixture.config_path), "--bulletin-base-url", fixture._ready["base"],
                "--handle", "evaluation-b-" + fixture._spec["slot_id"]), repository, native_env)
            fixture._wait(fixture.config_path.exists)
            raw = slot.read("gateway-config.json", max_bytes=65536)
            fixture._config, fixture.config_sha = strict_load_json(raw, max_bytes=65536), hashlib.sha256(raw).hexdigest()
            fixture._admit_config()
            fixture._seal()
            return fixture
        except Exception as exc:
            fixture.close()
            raise FixtureError("fixture_setup_failed") from exc

    def _alive(self):
        _require(not self._closed)
        for index, process in enumerate(self._processes):
            outcome = process.wait(0)
            if outcome is not None:
                self._terminal(index, outcome, "liveness_check")
                raise FixtureError("fixture_child_exited")

    def _terminal(self, index, outcome, observed_during):
        if index in self._recorded or outcome is None:
            return
        child, outputs = ("source-a", "native-b")[index], {}
        for stream in ("stdout", "stderr"):
            raw = getattr(outcome, stream).encode("utf-8")
            name = f"fixture-{child}-{stream}.txt"
            outputs[stream] = {"record_name": name, "sha256": self.slot.put(
                name, raw[:1048576], max_bytes=1048576), "truncated": len(raw) > 1048576}
        self.slot.put(f"fixture-{child}-process.json", canonical_bytes({
            "schema_version": 1, "run_id": self._spec["run_id"], "slot_id": self._spec["slot_id"],
            "child": child, "observed_during": observed_during,
            "returncode": outcome.returncode, "elapsed_ms": outcome.elapsed_ms,
            "timed_out": outcome.timed_out, "malformed_output": outcome.malformed_output,
            "outputs": outputs}), max_bytes=8192)
        self._recorded.add(index)

    def _wait(self, ready):
        while time.monotonic() < self._deadline:
            self._alive()
            if ready():
                return
            time.sleep(.01)
        raise FixtureError("fixture_setup_timeout")

    def _launch(self, launcher, argv, repository, env):
        _require(time.monotonic() < self._deadline)
        self.slot.read("fixture-input.json", max_bytes=32768, expected_sha256=self._input_sha)
        process = launcher(argv, cwd=repository, stdin_bytes=b"", env=env)
        self._processes.append(process)
        _require(time.monotonic() < self._deadline and process.resume())

    def _admit_spec(self):
        s = self._spec
        fields = {"schema", "run_id", "slot_id", "expected_source_commit", "room", "source_payload", "lifetime_seconds"}
        _require(type(s) is dict and fields <= set(s) and not set(s) - fields - {"decoy_payload"}
            and s["schema"] == "flywheel.bulletin-actor-fixture-input/v1"
            and all(_token(s[k]) for k in ("run_id", "slot_id")) and _sha(s["expected_source_commit"], 40)
            and type(s["room"]) is str and bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", s["room"]))
            and type(s["lifetime_seconds"]) is int and 1 <= s["lifetime_seconds"] <= 7200)
        for key in ("source_payload", "decoy_payload"):
            if key not in s:
                continue
            p = s[key]
            _require(type(p) is dict and {"task_id", "state"} <= set(p) and not set(p) - {"task_id", "state", "note"}
                and _token(p["task_id"]) and p["state"] == "reported" and len(canonical_bytes(p)) <= 4000)
            _require("note" not in p or type(p["note"]) is str and "\0" not in p["note"])
        _require("decoy_payload" not in s or s["decoy_payload"]["task_id"] != s["source_payload"]["task_id"])

    def _admit_ready(self):
        r, s = self._ready, self._spec
        _require(type(r) is dict and set(r) == {"schema", "run_id", "slot_id", "base", "room", "sourceId",
            "sourceAuthor", "baselineIds", "decoyId", "sourceCommit", "clientSha256", "workerBundleSha256",
            "inputSha256", "lifetime_seconds"} and r["schema"] == "flywheel.bulletin-actor-fixture-ready/v1")
        _require(all(r[k] == s[k] for k in ("run_id", "slot_id", "room", "lifetime_seconds"))
            and type(r["lifetime_seconds"]) is int and r["sourceCommit"] == s["expected_source_commit"]
            and r["inputSha256"] == self._input_sha and _sha(r["clientSha256"]) and _sha(r["workerBundleSha256"]))
        _origin(r["base"])
        _require(type(r["sourceAuthor"]) is str and bool(re.fullmatch(r"[A-Za-z0-9_-]{43}", r["sourceAuthor"]))
            and _token(r["sourceId"]) and type(r["baselineIds"]) is list)
        expected = [r["sourceId"]]
        if "decoy_payload" in s:
            _require(_token(r["decoyId"]) and r["decoyId"] != r["sourceId"])
            expected.append(r["decoyId"])
        else:
            _require(r["decoyId"] is None)
        _require(r["baselineIds"] == expected)

    def _admit_config(self):
        c = self._config
        _require(type(c) is dict and c.get("schema") == "flywheel.bulletin-media-gateway-fixture/v1"
            and c.get("mode") == "actual_worker_loopback" and c.get("bulletin_base_url") == self._ready["base"]
            and type(c.get("identity_thumbprint")) is str and bool(re.fullmatch(r"[A-Za-z0-9_-]{43}", c["identity_thumbprint"]))
            and c["identity_thumbprint"] != self._ready["sourceAuthor"])
        _require(_origin(c["base_url"]) != self._ready["base"] and c.get("control_url") == "")
        _require(type(c.get("token")) is str and 0 < len(c["token"]) <= 1024 and
            not any(ch in c["token"] for ch in ("\r", "\n", "\0")) and _sha(c.get("event_head"))
            and type(c.get("journey_ref")) is str and bool(re.fullmatch(r"jrn_[a-f0-9]{32}", c["journey_ref"]))
            and type(c.get("credential_ref")) is str and bool(re.fullmatch(r"cred_[a-f0-9]{32}", c["credential_ref"]))
            and type(c.get("identity_registration")) is dict and c["identity_registration"].get("registered") is True)

    def _seal(self):
        self._alive()
        limits = {"request_timeout_seconds": 5, "max_response_bytes": 65536}
        reader = self._reader_factory(self._ready["base"], limits)
        reader.deadline = min(time.monotonic() + 60, self._deadline)
        source = _project(reader.get("/v1/posts/" + quote(self.source_id, safe=""))["post"])
        feed = reader.get("/v1/feed?room=" + quote(self.room, safe="") + "&limit=100")
        _require(feed.get("ok") is True and feed.get("next_before", "missing") is None
            and type(feed.get("posts")) is list and len(feed["posts"]) == len(self.parent_ids))
        posts = [_project(p) for p in feed["posts"]]
        _require({p["id"] for p in posts} == set(self.parent_ids) and source in posts)
        self._decoy = None
        for index, post_id in enumerate(self.parent_ids):
            post = next(p for p in posts if p["id"] == post_id)
            expected = self._spec["decoy_payload" if index else "source_payload"]
            _require(post["author"] == self._ready["sourceAuthor"] and post["room"] == self.room
                and post["parent_id"] is None and strict_load_json(post["body"], max_bytes=4000) == expected)
            if index:
                self._decoy = post
        self._contract = validate_contract({"schema": "flywheel.bulletin-task-contract/v1",
            "task_id": self._spec["source_payload"]["task_id"], "actor_a": self._ready["sourceAuthor"],
            "actor_b": self._config["identity_thumbprint"], "room": self.room, "source_id": self.source_id,
            "baseline_ids": list(self.parent_ids), "source_payload": self._spec["source_payload"],
            "result_payload": {"task_id": self._spec["source_payload"]["task_id"], "state": "needs_review"},
            "max_writes": 1, "max_pages": 4, "page_size": 50,
            "max_response_bytes": 262144, "request_timeout_seconds": 5})
        self._alive()
        _require(time.monotonic() < self._deadline)
        self._contract_sha = self.slot.put("contract.json", canonical_bytes(self._contract), max_bytes=32768)
        self.slot.put("fixture-baseline.json", canonical_bytes({"source": source, "posts": posts}), max_bytes=65536)

    @property
    def ready(self): return deepcopy(self._ready)
    @property
    def config(self): return deepcopy(self._config)
    @property
    def contract(self): return deepcopy(self._contract)
    @property
    def room(self): return self._ready["room"]
    @property
    def source_id(self): return self._ready["sourceId"]
    @property
    def parent_ids(self): return tuple(self._ready["baselineIds"])
    @property
    def public_decoy(self): return deepcopy(self._decoy)

    def read_source(self, source_id):
        self._alive()
        _require(source_id == self.source_id and not self._read_used)
        self._read_used = True
        reader = self._reader_factory(self._ready["base"], {"request_timeout_seconds": 5, "max_response_bytes": 65536})
        reader.deadline = time.monotonic() + 5
        post = _project(reader.get("/v1/posts/" + quote(source_id, safe=""))["post"])
        _require(post["id"] == self.source_id)
        self.slot.put("fixture-actor-source.json", canonical_bytes(post), max_bytes=65536)
        return post

    def observe(self):
        self._alive()
        _require(not self._observed)
        self._observed = True
        self.slot.read("contract.json", max_bytes=32768, expected_sha256=self._contract_sha)
        observation = self._observer(deepcopy(self._contract), self._ready["base"], allow_loopback=True)
        review = build_review(self._contract, observation)
        self.slot.put("observation.json", canonical_bytes(observation), max_bytes=1048576)
        self.slot.put("review.json", canonical_bytes(review), max_bytes=2097152)
        return review

    def close(self):
        if self._closed:
            return
        self._closed = True
        failed = False
        for index, process in reversed(list(enumerate(self._processes))):
            try:
                if process.signal_tree() is False:
                    failed = True
            except Exception:
                failed = True
            try:
                process.close()
                self._terminal(index, process.wait(0), "cleanup")
            except Exception:
                failed = True
        for root in reversed(self._roots):
            try:
                root.close()
            except Exception:
                failed = True
        if failed:
            raise FixtureError("fixture_cleanup_failed")

    def __enter__(self): return self
    def __exit__(self, *_args): self.close()
