import { mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { dirname } from "node:path";
import { newSession } from "./tutor.mjs";
import { stateFile } from "../state.mjs";

// `<dir>/tutor/<id><suffix>`. The id is checked and the resolved file must stay inside `dir`,
// so a sessionId can never name a file elsewhere (`..`, an absolute path or a linked folder).
export function sessionPath(dir, id, suffix = ".json") {
  return stateFile(dir, "tutor", id, suffix, "sessionId");
}

export function writeSessionFile(dir, id, suffix, text) {
  const p = sessionPath(dir, id, suffix);
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, text);
  return p;
}

export function saveSession(dir, id, session) {
  return writeSessionFile(dir, id, ".json", JSON.stringify(session, null, 2));
}

export function sessionExists(dir, id) {
  return existsSync(sessionPath(dir, id));
}

export function loadSession(dir, id) {
  const p = sessionPath(dir, id);
  if (!existsSync(p)) return null;
  return JSON.parse(readFileSync(p, "utf8"));
}

export function loadOrCreate(dir, id, { topic = "", objectives = [] } = {}) {
  return loadSession(dir, id) || newSession({ topic, objectives });
}
