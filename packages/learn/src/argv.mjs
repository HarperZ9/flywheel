// The command line, read once. A flag that takes a value consumes the next token, so a value (an
// attestation note, an id, a topic) is never read back as a flag, and a grant such as
// --allow-cost or --submit counts only where a flag can stand. Any other token that starts with
// "--" is a switch; the rest are positional.

// Every flag that takes a value. tests/argv.test.mjs keeps this list in step with the CLI.
export const VALUE_FLAGS = new Set([
  "--answer", "--as-of", "--attest", "--correct", "--desired-retention", "--dir", "--draft",
  "--feedback", "--file", "--grade", "--id", "--index", "--match", "--min", "--note", "--now",
  "--objective", "--objectives", "--out", "--packet", "--prediction", "--prompt", "--seed",
  "--submit", "--threshold", "--title", "--topic", "--url",
]);

export function parseArgv(argv) {
  const values = new Map();
  const switches = new Set();
  const positionals = [];
  for (let i = 0; i < argv.length; i++) {
    const token = argv[i];
    if (VALUE_FLAGS.has(token)) {
      if (!values.has(token)) values.set(token, argv[i + 1]);
      i++;
    } else if (typeof token === "string" && token.startsWith("--")) {
      switches.add(token);
    } else {
      positionals.push(token);
    }
  }
  return { values, switches, positionals };
}

// The value given for `flag`: null when the flag is absent, undefined when it ends the line.
export function arg(argv, flag) {
  if (!VALUE_FLAGS.has(flag)) throw new Error(`${flag} is not a registered value flag (src/argv.mjs)`);
  const { values } = parseArgv(argv);
  return values.has(flag) ? values.get(flag) : null;
}

// Whether `flag` stands in flag position: a switch, or a value flag that was given.
export function has(argv, flag) {
  const { values, switches } = parseArgv(argv);
  return switches.has(flag) || values.has(flag);
}
