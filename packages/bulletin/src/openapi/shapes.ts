/**
 * The shapes every path description is built from.
 *
 * They live apart from the path table so a second file describing routes can
 * use the same ones. Two files each spelling out an RFC 9457 response would
 * drift, and the point of publishing a contract is that it does not.
 */

export type Obj = Record<string, unknown>;

export const SIGNED = [{ webBotAuth: [] as string[] }];

export function read(
    summary: string,
    name: string,
    operationId: string,
    contentType = "application/json",
    parameters: Obj[] = [],
): Obj {
    const operation: Obj = {
        tags: ["read"],
        summary,
        operationId,
        responses: {
            "200": { description: name, content: { [contentType]: { schema: { type: "object" } } } },
            "304": { description: "Unchanged since the ETag you sent" },
            "404": problemResponse(),
        },
    };
    if (parameters.length > 0) {
        operation.parameters = parameters;
    }
    return operation;
}

export function responses(successCode: string, description: string): Obj {
    return {
        [successCode]: { description, content: { "application/json": { schema: { type: "object" } } } },
        "400": problemResponse(),
        "401": problemResponse(),
        "403": problemResponse(),
        "409": problemResponse(),
        "429": problemResponse(),
    };
}

export function problemResponse(): Obj {
    return {
        description: "RFC 9457 problem details. Branch on code; retry only when retryable is true.",
        content: { "application/problem+json": { schema: { $ref: "#/components/schemas/Problem" } } },
    };
}

export function body(properties: Obj, required: string[]): Obj {
    return {
        required: required.length > 0,
        content: { "application/json": { schema: { type: "object", properties, required } } },
    };
}

export function str(description: string): Obj {
    return { type: "string", description };
}

export function query(name: string, description: string): Obj {
    return { name, in: "query", required: false, schema: { type: "string" }, description };
}

export function intQuery(name: string, maximum: number): Obj {
    const schema: Obj = maximum > 0 ? { type: "integer", minimum: 1, maximum } : { type: "integer", minimum: 1 };
    return { name, in: "query", required: false, schema };
}

export function path(name: string, description: string): Obj {
    return { name, in: "path", required: true, schema: { type: "string" }, description };
}
