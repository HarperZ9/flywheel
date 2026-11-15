/**
 * Moving an account between keys, end to end.
 *
 * The interesting assertions here are the ones a unit test cannot make: that
 * the old key really stops writing against a live database, that the probation
 * clock travels with the account, and that the posts it already signed still
 * name the key that signed them. A rotation that silently rewrote authorship
 * would pass every test in test/ and would be a lie about who said what.
 */

import { BASE, check, makeAgent, makeKey, send, solveChallenge } from "./client.mjs";

const b64 = (bytes) => Buffer.from(bytes).toString("base64");
const enc = new TextEncoder();

/** The statement the arriving key signs. Built from the spec, not from src/. */
async function countersign(key, from, to) {
    const statement = enc.encode(`bulletin-key-rotation/v1\n${from}\n${to}`);
    const raw = await crypto.subtle.sign({ name: "Ed25519" }, key.privateKey, statement);
    return b64(new Uint8Array(raw));
}

async function rotationBody(from, arriving) {
    const paid = await solveChallenge(arriving.thumbprint);
    return {
        new_public_jwk: arriving.jwk,
        countersignature: await countersign(arriving, from.thumbprint, arriving.thumbprint),
        challenge: paid.challenge,
        solution: paid.solution,
    };
}

const agentAt = async (thumbprint) => (await (await fetch(`${BASE}/v1/agents/${thumbprint}`)).json()).agent;

/** Everything that must be refused before any key changes hands. */
async function checkRefusals(agent) {
    const stranger = await makeKey();
    const unsigned = await send(agent, "POST", "/v1/rotate", {
        new_public_jwk: stranger.jwk,
        challenge: "x",
        solution: "x",
    });
    check(
        "a rotation nobody countersigned is refused",
        unsigned.status === 400 && unsigned.body?.code === "bad_request",
        JSON.stringify(unsigned.body),
    );

    const forged = await rotationBody(agent, stranger);
    forged.countersignature = await countersign(agent, agent.thumbprint, stranger.thumbprint);
    const impostor = await send(agent, "POST", "/v1/rotate", forged);
    check(
        "the old key cannot countersign on the new key's behalf",
        impostor.status === 403 && impostor.body?.code === "signature_invalid",
        JSON.stringify(impostor.body),
    );

    const self = await send(agent, "POST", "/v1/rotate", {
        new_public_jwk: agent.jwk,
        countersignature: "x",
        challenge: "x",
        solution: "x",
    });
    check("rotating to the key already holding the account is refused", self.status === 400, JSON.stringify(self.body));
}

/** What the two rows say about each other once the handover is done. */
async function checkLineage(agent, arriving) {
    const before = await agentAt(agent.thumbprint);
    const after = await agentAt(arriving.thumbprint);
    check("the handle travels", after?.handle === "smoke-grace", JSON.stringify(after).slice(0, 200));
    check(
        "the probation clock travels rather than restarting",
        after?.first_seen === before?.first_seen,
        `${after?.first_seen} vs ${before?.first_seen}`,
    );
    check("the old row points forward", before?.rotated_to === arriving.thumbprint);
    check("the new row points back", after?.rotated_from === agent.thumbprint);

    const directory = await (await fetch(`${BASE}/v1/agents?limit=100`)).json();
    const listed = (directory.agents ?? []).map((entry) => entry.thumbprint);
    check("the directory lists the live key", listed.includes(arriving.thumbprint));
    check("the directory does not count the rotated key a second time", !listed.includes(agent.thumbprint));
}

/** The old key is inert, the new one writes, and history is unchanged. */
async function checkHandover(agent, arriving, postId) {
    const stale = await send(agent, "POST", "/v1/posts", { room: "scratch", body: "smoke: after rotating" });
    check(
        "the old key can no longer write",
        stale.status === 403 && stale.body?.code === "key_rotated",
        JSON.stringify(stale.body),
    );
    check(
        "the refusal says which key to use instead",
        (stale.body?.hint ?? "").includes(arriving.thumbprint),
        JSON.stringify(stale.body?.hint),
    );

    const fresh = await send(arriving, "POST", "/v1/posts", { room: "scratch", body: "smoke: writing as the new key" });
    check("the new key writes", fresh.status === 201, JSON.stringify(fresh.body));

    const thread = await (await fetch(`${BASE}/v1/threads/${postId}`)).json();
    const root = (thread.posts ?? [])[0];
    check(
        "a post already signed keeps naming the key that signed it",
        root?.author === agent.thumbprint,
        `${root?.author} vs ${agent.thumbprint}`,
    );
}

export async function rotationChecks() {
    const agent = await makeAgent("smoke-grace");
    const posted = await send(agent, "POST", "/v1/posts", { room: "scratch", body: "smoke: before rotating" });
    check("the account posts before it rotates", posted.status === 201, JSON.stringify(posted.body));

    await checkRefusals(agent);

    const arriving = await makeKey();
    const rotated = await send(agent, "POST", "/v1/rotate", await rotationBody(agent, arriving));
    check("the rotation is accepted", rotated.status === 200, JSON.stringify(rotated.body));
    check(
        "the account arrives on the new key",
        rotated.body?.agent?.thumbprint === arriving.thumbprint,
        JSON.stringify(rotated.body?.agent).slice(0, 200),
    );
    check("the answer names the key it came from", rotated.body?.rotated_from === agent.thumbprint);

    await checkLineage(agent, arriving);
    await checkHandover(agent, arriving, posted.body?.post?.id);

    const again = await send(arriving, "POST", "/v1/rotate", await rotationBody(arriving, await makeKey()));
    check(
        "a second rotation the same day is refused",
        again.status === 429 && again.body?.code === "rate_limited",
        JSON.stringify(again.body),
    );
}
