// Closed error codes for tool failures. The detail is fixed text chosen by learn: it never
// carries file bytes, a path the caller did not supply, or an environment value.
export const ERROR_CODES = Object.freeze(["INVALID_ARGUMENT", "NOT_FOUND", "CONFLICT", "INTERNAL"]);

export class LearnError extends Error {
  constructor(code, detail, { retryable = false, setup = null } = {}) {
    super(detail);
    this.name = "LearnError";
    this.code = code;
    this.retryable = retryable;
    this.setup = setup;
  }

  toJSON() {
    return { code: this.code, retryable: this.retryable, setup: this.setup, detail: this.message };
  }
}

export const invalid = (detail) => new LearnError("INVALID_ARGUMENT", detail);
export const notFound = (detail) => new LearnError("NOT_FOUND", detail);
export const conflict = (detail) => new LearnError("CONFLICT", detail);
