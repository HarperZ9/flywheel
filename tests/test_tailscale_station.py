import json

from harness.gateway_auth import check
from harness import tailscale_station
from harness.tailscale_station import plan_tailnet_gateway
from harness.usage_live_parse import literal_loopback_base


def _status(*, online=True, ips=None):
    return {
        "BackendState": "Running",
        "Self": {
            "Online": online,
            "TailscaleIPs": ips or ["100.88.1.2", "fd7a:115c:a1e0::1"],
            "DNSName": "workstation.private.ts.net.",
            "HostName": "private-workstation",
        },
        "User": {"1": {"LoginName": "owner@example.com"}},
        "Peer": {"peer-id": {"DNSName": "phone.private.ts.net."}},
    }


def test_tailnet_plan_accepts_running_online_self_ipv4():
    plan = plan_tailnet_gateway(_status(), port=8799, token_present=True)

    assert plan["ok"] is True
    assert plan["reason"] == "ok"
    assert plan["transport"] == "tailnet"
    assert plan["connection_url"] == "http://100.88.1.2:8799"
    assert plan["bind_hosts"] == ["127.0.0.1", "100.88.1.2"]
    assert plan["allow_hosts"] == ["100.88.1.2"]
    assert plan["token_present"] is True


def test_tailnet_plan_refuses_offline_self_without_fallback_hosts():
    plan = plan_tailnet_gateway(_status(online=False), port=8799)

    assert plan["ok"] is False
    assert plan["reason"] == "tailscale_self_offline"
    assert plan["connection_url"] is None
    assert plan["bind_hosts"] == []
    assert plan["allow_hosts"] == []
    assert "0.0.0.0" not in json.dumps(plan)


def test_tailnet_plan_refuses_non_tailnet_ipv4_without_lan_fallback():
    plan = plan_tailnet_gateway(_status(ips=["192.168.1.44"]), port=8799)

    assert plan["ok"] is False
    assert plan["reason"] == "no_tailnet_ipv4"
    assert plan["connection_url"] is None
    assert plan["bind_hosts"] == []
    assert plan["allow_hosts"] == []
    assert "192.168.1.44" not in plan["bind_hosts"]


def test_tailnet_plan_receipt_redacts_peer_account_dns_and_token_material():
    plan = plan_tailnet_gateway(_status(), port=8799, token_present=True)
    rendered = json.dumps(plan, sort_keys=True)

    assert "owner@example.com" not in rendered
    assert "private.ts.net" not in rendered
    assert "peer-id" not in rendered
    assert "gateway.token" not in rendered
    assert "token_hash" not in rendered
    assert plan["token_present"] is True


def test_tailnet_cli_status_file_dry_plan(capsys, tmp_path):
    fixture = tmp_path / "status.json"
    fixture.write_text(json.dumps(_status()), encoding="utf-8")

    code = tailscale_station._main([
        "--status-file", str(fixture),
        "--port", "8800",
        "--token-present",
    ])
    rendered = json.loads(capsys.readouterr().out)

    assert code == 0
    assert rendered["connection_url"] == "http://100.88.1.2:8800"
    assert rendered["bind_hosts"] == ["127.0.0.1", "100.88.1.2"]
    assert rendered["token_present"] is True


def test_tailnet_gateway_host_still_requires_bearer_token():
    allowed = frozenset({"127.0.0.1", "localhost", "[::1]", "100.88.1.2"})

    assert check({"Host": "100.88.1.2:8799"}, "GET", "secret", allowed_hosts=allowed) == (False, "no_token")
    assert check({"Host": "100.88.1.2:8799", "Authorization": "Bearer wrong"}, "GET", "secret", allowed_hosts=allowed) == (False, "bad_token")
    assert check({"Host": "100.88.1.2:8799", "Authorization": "Bearer secret"}, "GET", "secret", allowed_hosts=allowed) == (True, "ok")


def test_local_model_probe_rejects_tailnet_url():
    assert literal_loopback_base("http://100.88.1.2:8000/v1") == ""
    assert literal_loopback_base("http://127.0.0.1:8000/v1") == "http://127.0.0.1:8000"
