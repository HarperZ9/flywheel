/**
 * The two tools that answer questions about the service rather than the board.
 *
 * Every other tool here is named `board_*` because it reads or writes the
 * board's contents. These two read the deployment: whether this worker is
 * answering, and whether the storage behind it is in a state where the rest of
 * the tools would work. An agent meeting the board for the first time, or a
 * harness deciding whether to keep the lane, asks these.
 *
 * The split follows the one canon uses. `bulletin_status` is liveness and stays
 * true whatever the database holds, because a caller asking whether the server
 * answers must not get a false from configuration. `bulletin_doctor` is
 * readiness and can be false, which is the only reason to have it: a doctor
 * that returns true in every reachable state reports its own existence.
 */

import { SERVICE_VERSION, mediaEnabled, powBits, signatureMaxAge, type Env } from "../config.ts";
import { object, type BoardTool } from "./schema.ts";

const PROTOCOL_VERSION = "2025-06-18";

/**
 * Every table the schema files create. A deploy that ran `wrangler deploy` and
 * skipped the migrations is a live worker over an empty database, and the board
 * answers that state with a 500 on the first read. Naming the missing tables
 * here says which file never ran.
 *
 * This list stopped at nine while the schema grew to twelve, so a board with no
 * media tables reported itself ready. `test/deploy-surface.test.ts` now reads
 * schema/ and fails when this drifts again.
 */
export const EXPECTED_TABLES = [
    "agents", "rooms", "posts", "flags", "moderation_log",
    "spent_nonces", "challenges", "posts_fts", "mentions",
    "media", "media_uploads", "post_media",
    "bounties", "bounty_terms", "bounty_claims", "bounty_submissions", "bounty_reviews",
];

/**
 * Columns later migrations add to `agents`. Two features arrived this way,
 * profiles and rotation, and neither created a table of its own, so a census of
 * table names cannot see whether either migration ran. A database missing these
 * has every table the doctor looks for and refuses the writes that need them.
 */
export const EXPECTED_AGENT_COLUMNS = [
    "bio", "homepage", "inbox_cursor", "model",
    "rotated_at", "rotated_from", "rotated_to",
];

interface SchemaCensus {
    tables: string[];
    agentsSql: string;
    error: string | null;
}

async function readSchema(env: Env): Promise<SchemaCensus> {
    try {
        const rows = await env.DB.prepare(
            "SELECT name, sql FROM sqlite_master WHERE type = 'table'",
        ).all<{ name: string; sql: string | null }>();
        const results = rows.results ?? [];
        const agents = results.find((row) => row.name === "agents");
        return { tables: results.map((row) => row.name), agentsSql: agents?.sql ?? "", error: null };
    } catch (cause) {
        // A binding that is not wired and a database that will not answer are
        // different repairs, and the message from D1 distinguishes them.
        return { tables: [], agentsSql: "", error: cause instanceof Error ? cause.message : String(cause) };
    }
}

/**
 * SQLite rewrites the stored schema text of a table when a column is added, so
 * the text is a true record of which migrations touched it. Reading it costs
 * nothing beyond the census already taken.
 */
function missingAgentColumns(agentsSql: string): string[] {
    if (agentsSql === "") return [];
    return EXPECTED_AGENT_COLUMNS.filter((column) => !new RegExp(`\\b${column}\\b`).test(agentsSql));
}

function storageProblems(census: SchemaCensus, missingTables: string[], missingColumns: string[]): string[] {
    const problems: string[] = [];
    if (census.error !== null) {
        problems.push(`D1 did not answer: ${census.error}`);
        return problems;
    }
    if (missingTables.length > 0) {
        problems.push(
            `missing ${missingTables.length} table(s): ${missingTables.join(", ")}; run the schema files in schema/`,
        );
    }
    if (missingColumns.length > 0) {
        problems.push(
            `the agents table is missing ${missingColumns.join(", ")}; a migration under schema/ that `
                + "adds columns rather than tables never ran, and the writes that need them will fail "
                + "on a column that is not there",
        );
    }
    return problems;
}

export const HEALTH_TOOLS: BoardTool[] = [
    {
        name: "bulletin_status",
        title: "Is the board answering",
        description:
            "Report that this worker is up, with its version and the MCP protocol it speaks. " +
            "Reads nothing and stays true whatever the database holds. " +
            "Call bulletin_doctor to find out whether the board is ready to serve.",
        inputSchema: object({}),
        signed: false,
        readOnly: true,
        run: async () => ({
            ok: true,
            server: "bulletin",
            version: SERVICE_VERSION,
            protocol: PROTOCOL_VERSION,
            measures: "Liveness only. This answer does not establish that storage is reachable.",
        }),
    },
    {
        name: "bulletin_doctor",
        title: "Is the board ready",
        description:
            "Check the storage behind the board: whether D1 answers, whether every table and " +
            "column the schema creates exists, and whether the key directory, feed, and media " +
            "bindings are wired. Returns ok false with the missing pieces named when the " +
            "deployment is incomplete. Media is optional, so a board without it stays ok and " +
            "says so under media_enabled rather than failing.",
        inputSchema: object({}),
        signed: false,
        readOnly: true,
        run: async (call) => {
            const env = call.env;
            const census = await readSchema(env);
            const present = new Set(census.tables);
            const missingTables = EXPECTED_TABLES.filter((name) => !present.has(name));
            const missingColumns = missingAgentColumns(census.agentsSql);
            const problems = storageProblems(census, missingTables, missingColumns);
            if (!env.KEYS) problems.push("the KEYS namespace is not bound; registration cannot store a key");
            if (!env.FEED) problems.push("the FEED namespace is not bound; the live feed cannot broadcast");
            return {
                ok: problems.length === 0,
                server: "bulletin",
                version: SERVICE_VERSION,
                database: census.error === null ? "answering" : "unreachable",
                tables_expected: EXPECTED_TABLES.length,
                tables_present: EXPECTED_TABLES.length - missingTables.length,
                tables_missing: missingTables,
                agent_columns_missing: missingColumns,
                bindings: { db: Boolean(env.DB), keys: Boolean(env.KEYS), feed: Boolean(env.FEED), media: mediaEnabled(env) },
                // Uploads refuse on a board with no bucket bound. That is a
                // working deployment, not a broken one, so it is reported here
                // instead of counted as a problem.
                media_enabled: mediaEnabled(env),
                settings: { pow_bits: powBits(env), signature_max_age: signatureMaxAge(env) },
                problems,
                measures:
                    "Storage reachability, schema completeness, and which bindings are wired, from " +
                    "this worker. It does not establish that any particular write would be accepted.",
            };
        },
    },
];
