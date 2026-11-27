"""Protocol flows built on the world: renewals, dependent notices and orders."""

from __future__ import annotations

from .canon import fingerprint
from .crypto import envelope, msg_id
from .device import Device
from .orders import order_body, scope_proof, sign_order
from .renewal import build_root, leaf_package, renewal_body, sign_renewal
from .world import World

# Seat indices from seats.default_seats: 2, 3 and 5 hold the non_frontier_state flag.
HALT_SIGNERS = (2, 3, 4, 5)
NO_NONFRONTIER = (0, 1, 4, 6)


def seats_at(world: World, indices) -> list:
    return [world.seats[i] for i in indices]


def bootstrap(world: World, devices: list[Device], epoch: int = 1) -> dict:
    for dev in devices:
        dev.outbox.append(dev.heartbeat())
        world.deliver(dev)
    ren = issue_renewal(world, epoch)
    for dev in devices:
        ok, reason = deliver_renewal(world, dev, ren)
        if not ok:
            raise RuntimeError(f"bootstrap renewal refused: {reason}")
    return ren


def issue_renewal(world: World, epoch: int, signers=None, validity_s: int | None = None) -> dict:
    p = world.params
    members = world.desk.good_standing(world.now_ms())
    tree, order = build_root(members, epoch)
    body = renewal_body(tree, epoch, world.now_ms(), validity_s or p.renewal_validity,
                        world.criterion["body"]["id"])
    chosen = signers if signers is not None else world.seats[: p.k_renew]
    msg = sign_renewal(body, chosen)
    world.publish(msg)
    world.cosign()
    world.open_roots.append({"subject_fp": msg_id(msg), "published_ms": world.now_ms(),
                             "seats": [s.key for s in world.seats],
                             "signed": [s.key for s in chosen]})
    warn = world.desk.note_root(members)
    return {"msg": msg, "tree": tree, "order": order, "members": members, "warn": warn}


def deliver_renewal(world: World, dev: Device, ren: dict) -> tuple[bool, str]:
    pkg = leaf_package(ren["tree"], ren["order"], ren["members"], dev.key)
    return dev.accept_renewal(ren["msg"], world.bundles(ren["msg"], dev), pkg)


def post_notice(world: World, cluster_id: str, tags: list[str], effective_ms: int,
                expires_ms: int, seat_index: int = 2) -> tuple[dict, int]:
    """The proposing seat logs the dependent notice when it opens the vote."""
    body = {"cluster_id": cluster_id, "workload_tags": sorted(tags),
            "criterion_id": world.criterion["body"]["id"], "planned_effective_ms": effective_ms,
            "expires_ms": expires_ms, "appeal_route": "panel-1", "status": "proposed"}
    msg = envelope("dependent-notice", body, [world.seats[seat_index].signer])
    idx = world.publish(msg)
    world.cosign()
    logged = max(world.logs[int(k.split("-")[1])].leaves[v]["logged_ms"] for k, v in idx.items())
    return msg, logged


def build_order(world: World, action: str, cluster_id: str, *, tags=None, level=None,
                signers=None, effective_ms=None, expires_ms=None, notice=None, renews=None,
                lifts=None, convergence=None, evidence=None, logs=None,
                publish: bool = True) -> dict:
    now = world.now_ms()
    eff = now if effective_ms is None else effective_ms
    exp = eff + world.params.t_halt_max * 1000 if expires_ms is None else expires_ms
    ref = None
    if notice is not None:
        ref = {"entry_fp": fingerprint("entry", notice[0]), "logged_ms": notice[1]}
    crit_idx = world.logs[0].find(fingerprint("entry", world.criterion))
    body = order_body(action, cluster_id, world.clusters[cluster_id]["device_set_root"],
                      workload_tags=tags, level=level,
                      criterion={"id": "crit-1", "version": 1, "log_index": crit_idx},
                      evidence=evidence or [], convergence=convergence or {},
                      dependent_notice=ref, issued_ms=now, effective_ms=eff, expires_ms=exp,
                      renews=renews, lifts=lifts)
    msg = sign_order(body, seats_at(world, signers or HALT_SIGNERS))
    if publish:
        world.publish(msg, logs)
        world.cosign()
    return msg


def governance_renewal(world: World, order_id: str, reasons: str = "demo reasons") -> dict:
    """A logged governance decision with written reasons that a halt renewal cites
    (SPEC.md 8.3 and 12.3). The reasons stay sealed; the log holds their fingerprint."""
    body = {"decision": "renew", "renews": order_id,
            "reasons_fp": fingerprint("reasons", {"text": reasons})}
    msg = envelope("governance-decision", body, [world.governance])
    world.publish(msg)
    world.cosign()
    return msg


def package(world: World, msg: dict, dev: Device, notice: tuple | None = None) -> dict:
    cid = msg["body"]["scope"]["cluster_id"]
    keys = world.clusters[cid]["device_keys"]
    pkg = {"order": msg, "bundles": world.bundles(msg, dev),
           "scope_proof": scope_proof(keys, dev.key) if dev.key in keys else None,
           "notice": None, "notice_bundles": []}
    if notice is not None:
        pkg["notice"] = notice[0]
        pkg["notice_bundles"] = world.bundles(notice[0], dev)
    return pkg
