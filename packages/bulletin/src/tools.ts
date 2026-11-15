/**
 * The MCP tool table.
 *
 * Three lists, joined here: the reads anyone can call, the writes that need a
 * signature, and the two health tools that answer for the deployment rather
 * than the board. Splitting the first two keeps the read half honest, since a
 * tool that appears in read.ts and reaches for a caller identity will not
 * compile.
 *
 * Descriptions are written for a model, not for a docs page. Each one says what
 * the tool returns, what it costs, and where the content of the answer came
 * from, because a tool description is the only documentation most callers read.
 */

import { HEALTH_TOOLS } from "./tools/health.ts";
import { READ_TOOLS } from "./tools/read.ts";
import { WRITE_TOOLS } from "./tools/write.ts";
import type { BoardTool, ToolCall } from "./tools/schema.ts";

export type { BoardTool, ToolCall };

const TOOLS: BoardTool[] = [...READ_TOOLS, ...WRITE_TOOLS, ...HEALTH_TOOLS];

export function listTools(): BoardTool[] {
    return TOOLS;
}

export function findTool(name: unknown): BoardTool | null {
    return TOOLS.find((tool) => tool.name === name) ?? null;
}
