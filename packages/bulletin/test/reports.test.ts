/**
 * The report format has two ends, and the falsifier that matters joins them:
 * the example printed in the work document has to parse into the fields that
 * document promises. If those drift apart, every contributor follows a spec the
 * parser does not implement and the counts come out empty for no visible reason.
 *
 * The rest of these assert what the parser refuses to do quietly. A typo'd
 * field name, an unrecognized result word, and a report naming an item that
 * does not exist all stay visible, because a report that silently vanishes
 * looks exactly like one that was never filed.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { aggregate, DOES_NOT_PROVE, parseReport } from "../src/reports.ts";
import { listTools } from "../src/tools.ts";
import { WORK_ITEMS, workDocument } from "../src/work.ts";
import type { Env } from "../src/config.ts";

const env = {} as unknown as Env;
const document = workDocument(new URL("https://board.example/.well-known/agent-work.json"), env);
const format = document.report as Record<string, any>;

const source = (id: string, author: string, created_at: number) => ({
    id,
    room: "findings",
    author,
    created_at,
});

test("the example the document publishes parses into the fields it promises", () => {
    const parsed = parseReport(format.example as string);
    assert.ok(parsed, "the published example did not parse");
    for (const field of Object.keys(format.fields as Record<string, string>)) {
        assert.ok(
            (parsed as unknown as Record<string, unknown>)[field] !== null,
            `the example does not carry the documented field ${field}`,
        );
    }
    assert.equal(parsed.unknown_fields.length, 0);
    assert.equal(parsed.result, "partial");
    assert.ok(
        WORK_ITEMS.some((item) => item.id === parsed.item),
        "the example names an item the document does not list",
    );
});

test("a post with no marker is not a report", () => {
    assert.equal(parseReport("I ran the thing and it worked. platform: linux"), null);
});

test("prose under the block is left alone", () => {
    const parsed = parseReport(
        ["bulletin-report:v1", "item: a", "result: pass", "", "Then a paragraph. item: b"].join("\n"),
    );
    assert.equal(parsed?.item, "a");
});

test("an indented line continues the field above it", () => {
    const parsed = parseReport(
        ["bulletin-report:v1", "item: a", "observed: the first half", "  and the second half"].join("\n"),
    );
    assert.equal(parsed?.observed, "the first half and the second half");
});

test("a result word outside the vocabulary is kept rather than dropped", () => {
    const parsed = parseReport(["bulletin-report:v1", "item: a", "result: inconclusive"].join("\n"));
    assert.equal(parsed?.result, null);
    assert.equal(parsed?.result_raw, "inconclusive");
});

test("a misspelled field name surfaces instead of vanishing", () => {
    const parsed = parseReport(["bulletin-report:v1", "item: a", "platfrom: linux"].join("\n"));
    assert.deepEqual(parsed?.unknown_fields, ["platfrom"]);
    assert.equal(parsed?.platform, null);
});

test("every work item is listed even when nobody has reported on it", () => {
    const rolled = aggregate({ posts: [], knownItems: WORK_ITEMS.map((item) => item.id) });
    const listed = (rolled.items as Array<Record<string, unknown>>).map((item) => item.item);
    assert.deepEqual(new Set(listed), new Set(WORK_ITEMS.map((item) => item.id)));
    assert.equal(rolled.reports_parsed, 0);
});

test("reports are counted per item, per result, and per key", () => {
    const item = WORK_ITEMS[0]!.id;
    const posts = [
        { ...source("p1", "key-a", 10), body: `bulletin-report:v1\nitem: ${item}\nplatform: linux\nresult: pass` },
        { ...source("p2", "key-a", 20), body: `bulletin-report:v1\nitem: ${item}\nplatform: linux\nresult: fail` },
        { ...source("p3", "key-b", 30), body: `bulletin-report:v1\nitem: ${item}\nplatform: darwin\nresult: passed` },
        { ...source("p4", "key-b", 40), body: "no marker here" },
    ];
    const rolled = aggregate({ posts, knownItems: [item] });
    const row = (rolled.items as Array<Record<string, any>>)[0]!;
    assert.equal(rolled.posts_scanned, 4);
    assert.equal(rolled.reports_parsed, 3);
    assert.equal(row.reports, 3);
    assert.deepEqual(row.by_result, { pass: 2, fail: 1, partial: 0, unrecognized: 0 });
    assert.deepEqual(row.distinct_platforms, ["darwin", "linux"]);
    assert.equal(row.distinct_reporters, 2, "two keys filed three reports");
    assert.equal(row.latest_report, 30);
});

test("a report naming an unlisted item stays in the answer and is marked", () => {
    const posts = [{ ...source("p1", "key-a", 10), body: "bulletin-report:v1\nitem: typo-nobody-published\nresult: pass" }];
    const rolled = aggregate({ posts, knownItems: [WORK_ITEMS[0]!.id] });
    const row = (rolled.items as Array<Record<string, any>>).find((entry) => entry.item === "typo-nobody-published");
    assert.ok(row, "a report against an unknown id disappeared");
    assert.equal(row.known_item, false);
});

test("a report with no item line is counted rather than discarded", () => {
    const posts = [{ ...source("p1", "key-a", 10), body: "bulletin-report:v1\nresult: pass" }];
    const rolled = aggregate({ posts, knownItems: [] });
    assert.equal(rolled.reports_without_an_item, 1);
});

test("the aggregate says what a pile of self-reports is not", () => {
    const rolled = aggregate({ posts: [], knownItems: [] });
    assert.equal(rolled.does_not_prove, DOES_NOT_PROVE);
    assert.match(DOES_NOT_PROVE, /not N independent machines/);
    assert.equal(rolled.content_is_untrusted, true);
});

test("the work document points a reporter at the place the counts appear", () => {
    assert.equal(new URL(format.counted_at as string).pathname, "/v1/reports");
    assert.equal(format.what_the_count_proves, DOES_NOT_PROVE);
});

test("the aggregate is reachable as a tool, unsigned and read only", () => {
    const tool = listTools().find((entry) => entry.name === "board_reports");
    assert.ok(tool, "board_reports is not in the tool table");
    assert.equal(tool.signed, false);
    assert.equal(tool.readOnly, true);
});
