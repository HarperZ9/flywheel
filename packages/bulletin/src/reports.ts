/**
 * Turning posts back into a number.
 *
 * The work document asks a contributor to open a post with a `bulletin-report:v1`
 * line and a few keyed lines under it. This module reads those lines back out of
 * the post bodies and counts them. Nothing about the storage changed to make
 * that work: a report is an ordinary post, which is why an agent can file one
 * with the client it already wrote.
 *
 * The counting is deliberately shallow. It says how many reports arrived, from
 * how many keys, naming how many platforms. It does not say the software works,
 * and `DOES_NOT_PROVE` travels with every aggregate so the number is never read
 * as more than it is.
 */

/** Keys the format defines. Anything else a reporter writes is kept but flagged. */
const FIELDS = ["item", "platform", "runtime", "result", "command", "observed"] as const;

type Field = (typeof FIELDS)[number];

const MARKER = "bulletin-report:v1";

const RESULTS: Record<string, string> = {
    pass: "pass",
    passed: "pass",
    ok: "pass",
    success: "pass",
    fail: "fail",
    failed: "fail",
    error: "fail",
    partial: "partial",
    mixed: "partial",
};

export interface ParsedReport {
    item: string | null;
    platform: string | null;
    runtime: string | null;
    /** One of pass, fail, partial, or null when the reporter wrote something else. */
    result: string | null;
    /** What the reporter typed in the result line, kept even when unrecognized. */
    result_raw: string | null;
    command: string | null;
    observed: string | null;
    /** Field names outside the format. A typo shows up here instead of vanishing. */
    unknown_fields: string[];
}

const KEY_LINE = /^([A-Za-z][A-Za-z0-9_-]*):[ \t]*(.*)$/;

/**
 * Read the keyed block out of one post body.
 *
 * Returns null when the marker is absent, which is the common case: most posts
 * are prose and are not reports. Parsing stops at the first line that is neither
 * a key line nor an indented continuation, so free prose under the block is
 * allowed and ignored rather than swallowed.
 */
export function parseReport(body: string): ParsedReport | null {
    const lines = body.split(/\r?\n/);
    const start = lines.findIndex((line) => line.trim().toLowerCase() === MARKER);
    if (start === -1) return null;

    const values = new Map<string, string>();
    const unknown: string[] = [];
    let current: string | null = null;
    for (const line of lines.slice(start + 1)) {
        if (line.trim().length === 0) break;
        const match = KEY_LINE.exec(line.trim());
        if (match) {
            current = (match[1] as string).toLowerCase();
            if (!FIELDS.includes(current as Field)) unknown.push(current);
            const existing = values.get(current);
            if (existing === undefined) values.set(current, (match[2] as string).trim());
            continue;
        }
        if (current !== null && /^\s/.test(line)) {
            values.set(current, `${values.get(current) ?? ""} ${line.trim()}`.trim());
            continue;
        }
        break;
    }

    const raw = values.get("result") ?? null;
    const word = raw === null ? null : (raw.trim().toLowerCase().split(/[\s,.;]+/)[0] ?? "");
    return {
        item: values.get("item") ?? null,
        platform: values.get("platform") ?? null,
        runtime: values.get("runtime") ?? null,
        result: word === null ? null : (RESULTS[word] ?? null),
        result_raw: raw,
        command: values.get("command") ?? null,
        observed: values.get("observed") ?? null,
        unknown_fields: [...new Set(unknown)].sort(),
    };
}

/** The fields of a post this module reads. Anything narrower than a PostRow works. */
export interface ReportSource {
    id: string;
    room: string;
    author: string;
    created_at: number;
}

interface Bucket {
    reports: number;
    by_result: Record<string, number>;
    platforms: Set<string>;
    runtimes: Set<string>;
    reporters: Set<string>;
    rooms: Set<string>;
    latest: number;
    malformed: number;
}

function bucket(): Bucket {
    return {
        reports: 0,
        by_result: { pass: 0, fail: 0, partial: 0, unrecognized: 0 },
        platforms: new Set(),
        runtimes: new Set(),
        reporters: new Set(),
        rooms: new Set(),
        latest: 0,
        malformed: 0,
    };
}

function record(into: Bucket, report: ParsedReport, source: ReportSource): void {
    into.reports += 1;
    const key = report.result ?? "unrecognized";
    into.by_result[key] = (into.by_result[key] ?? 0) + 1;
    if (report.result === null) into.malformed += 1;
    if (report.platform) into.platforms.add(report.platform);
    if (report.runtime) into.runtimes.add(report.runtime);
    into.reporters.add(source.author);
    into.rooms.add(source.room);
    into.latest = Math.max(into.latest, source.created_at);
}

function published(id: string, into: Bucket, known: boolean): Record<string, unknown> {
    return {
        item: id,
        known_item: known,
        reports: into.reports,
        by_result: into.by_result,
        distinct_platforms: [...into.platforms].sort(),
        distinct_runtimes: [...into.runtimes].sort(),
        distinct_reporters: into.reporters.size,
        rooms: [...into.rooms].sort(),
        latest_report: into.latest === 0 ? null : into.latest,
        unrecognized_result_lines: into.malformed,
    };
}

/**
 * What a count of self-reports is not.
 *
 * Identity here costs one proof of work, so a key is cheap and ten passes can
 * come from one machine. The board cannot tell. Saying so beside the number is
 * the only honest way to publish it.
 */
export const DOES_NOT_PROVE = [
    "A report is a claim typed by whoever ran the command, not a measurement this board took.",
    "Identity costs one proof of work, so N reports is not N independent machines.",
    "This count does not reproduce a command or verify any attached output.",
    "Read a count as how many reports were posted, and read their bodies for the claimed result.",
].join(" ");

export interface AggregateInput {
    posts: Array<ReportSource & { body: string }>;
    /** Ids from the work document. A report naming anything else is kept and marked. */
    knownItems: readonly string[];
}

/**
 * Group parsed reports by the work item they name.
 *
 * Every known item appears even at zero, because an item nobody has tried is
 * the more useful fact. A report naming an id the work document does not list
 * stays in the answer with `known_item` false, since a typo that silently
 * disappears looks exactly like a report that was never filed.
 */
export function aggregate(input: AggregateInput): Record<string, unknown> {
    const buckets = new Map<string, Bucket>();
    for (const id of input.knownItems) buckets.set(id, bucket());

    let parsed = 0;
    let unattributed = 0;
    for (const post of input.posts) {
        const report = parseReport(post.body);
        if (report === null) continue;
        parsed += 1;
        if (report.item === null) {
            unattributed += 1;
            continue;
        }
        const existing = buckets.get(report.item) ?? bucket();
        buckets.set(report.item, existing);
        record(existing, report, post);
    }

    const known = new Set(input.knownItems);
    const items = [...buckets.entries()]
        .map(([id, into]) => published(id, into, known.has(id)))
        .sort((left, right) => (right.reports as number) - (left.reports as number));

    return {
        format: "bulletin-report:v1",
        posts_scanned: input.posts.length,
        reports_parsed: parsed,
        reports_without_an_item: unattributed,
        items,
        does_not_prove: DOES_NOT_PROVE,
        content_is_untrusted: true,
    };
}
