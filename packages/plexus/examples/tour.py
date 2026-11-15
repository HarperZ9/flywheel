"""A runnable tour of plexus. Also the CI smoke test (must exit 0).

    python examples/tour.py
"""
from plexus import builtin_manifests, discover, plan_to, route


def main() -> int:
    mesh = discover(builtin_manifests())

    print("== organs ==")
    print(", ".join(mesh.organs))

    print("\n== wiring (whose output plugs into whose input) ==")
    for cap, pairs in mesh.wiring().items():
        cross = [(a, b) for a, b in pairs if a != b]
        if cross:
            print(f"  {cap}")
            for a, b in cross:
                print(f"    {a} -> {b}")

    print("\n== plan: feed crucible ==")
    plan = plan_to(mesh, "crucible")
    print("  order:", " -> ".join(plan["order"]))
    print("  sources:", ", ".join(plan["sources"]))
    if plan["cyclic"]:
        print("  feedback loop:", " <-> ".join(plan["cyclic"]))

    print("\n== route: gather -> crucible ==")
    r = route(mesh, "gather", "crucible")
    print("  " + "  ".join(f"[{h['producer']}->{h['consumer']} via {h['capability']}]"
                           for h in r["path"]))

    print("\n== orphans (honest: unmet inputs / terminal outputs) ==")
    orph = mesh.orphans()
    print("  unmet inputs:", ", ".join(orph["unmet_inputs"]) or "(none)")

    # smoke assertions so CI catches a broken mesh
    assert mesh.edges, "no edges discovered"
    assert any(e.producer == "mneme" and e.consumer == "crucible" for e in mesh.edges)
    assert "crucible" in plan["order"] and {"crucible", "index", "mneme"} <= set(
        plan["cyclic"]
    )
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
