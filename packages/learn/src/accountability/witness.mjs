import { createHash } from "node:crypto";

export function sha256hex(input) {
  return createHash("sha256").update(input).digest("hex");
}

export function observe({ organ, subject, summary = "", payload = "", data = {} }) {
  return { organ, subject, summary, digest: "sha256:" + sha256hex(payload), data };
}
