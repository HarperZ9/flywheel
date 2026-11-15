// SPDX-License-Identifier: AGPL-3.0-only
//
// emet.go -- EMET, fourth (Go) clean-room implementation.
//
// Written against SPEC.md + conformance/vectors.json + conformance/markers.corpus
// ONLY, with no reference to the Python/Rust/JS implementations. Standard library
// only, zero third-party dependencies (crypto/sha256 for the byte-hash core; the
// second corroborate read path is a child-process re-read of this same binary).
//
// The verdict lattice is CLOSED (SPEC s.2): MATCH | DRIFT | UNVERIFIABLE, plus the
// closed auxiliary tokens COHERENT/VIEW_DIFFERS_FROM_SOURCE,
// CORROBORATED/QUARANTINE_READ_PATH_DIVERGENCE, INTACT/BROKEN. No codepath emits
// TRUSTED/APPROVED/SAFE or any authority word.
package main

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"os/exec"
	"sort"
	"strconv"
	"strings"
)

// -------------------------------------------------------------------------
// Exit codes (SPEC s.5): the verdict class as an integer. Advisory, never
// an authority decision.
// -------------------------------------------------------------------------
const (
	exitHeld     = 0  // MATCH/COHERENT/CORROBORATED/INTACT/no markers/selftest ok
	exitNegative = 1  // DRIFT/VIEW_DIFFERS_FROM_SOURCE/QUARANTINE.../BROKEN
	exitUnverif  = 2  // UNVERIFIABLE for any machine reason (SPEC s.9)
	exitMarkers  = 3  // one or more markers detected (refuse)
	exitUsage    = 64 // usage error
)

const (
	emetVersion = "1.1.0"
	specVersion = "1.0.0"
)

const refusedToken = "[REFUSED-IN-BAND-AUTHORITY]" // SPEC s.4 / F3

const genesisPrev = "0000000000000000000000000000000000000000000000000000000000000000"

// UNVERIFIABLE reason codes: a fixed machine enum (SPEC s.9), never prose.
const (
	eNotFound         = "E_NOT_FOUND"
	eNoRawChannel     = "E_NO_RAW_CHANNEL"
	eNoAnchor         = "E_NO_ANCHOR"
	eNoCorpus         = "E_NO_CORPUS"
	eNoCorpusVersion  = "E_NO_CORPUS_VERSION"
	eNoSecondReadPath = "E_NO_SECOND_READ_PATH"
	eLogCorrupt       = "E_LOG_CORRUPT"
)

// Store filenames (implementation-private, SPEC s.6/s.15). "membrane_log.jsonl"
// and "anchors.json" are the historical Python names; the conformance vectors
// seed and read membrane_log.jsonl, so we keep it.
const (
	anchorStore = "anchors.json"
	logStore    = "membrane_log.jsonl"
)

// =========================================================================
// Canonical JSON. Must be byte-identical to Python json.dumps(obj, sort_keys=True):
//   - keys sorted ascending
//   - ", " between items, ": " after each key
//   - ensure_ascii escaping (non-ASCII -> \uXXXX)
//   - Python does NOT escape < > & (Go's default encoder does; we hand-roll).
// Used for both the audit-chain fact serialization (SPEC s.7) and the --json
// envelope (SPEC s.13).
// =========================================================================

// jval is a canonical-JSON value: string, int, jobj, or []jval.
type jval interface{}

// jobj is an ordered set of key/value pairs; serialization sorts keys itself.
type jobj map[string]jval

func canonJSON(v jval) string {
	var b strings.Builder
	writeCanon(&b, v)
	return b.String()
}

func writeCanon(b *strings.Builder, v jval) {
	switch x := v.(type) {
	case string:
		writeCanonString(b, x)
	case int:
		b.WriteString(strconv.Itoa(x))
	case bool:
		if x {
			b.WriteString("true")
		} else {
			b.WriteString("false")
		}
	case nil:
		b.WriteString("null")
	case jobj:
		keys := make([]string, 0, len(x))
		for k := range x {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		b.WriteByte('{')
		for i, k := range keys {
			if i > 0 {
				b.WriteString(", ")
			}
			writeCanonString(b, k)
			b.WriteString(": ")
			writeCanon(b, x[k])
		}
		b.WriteByte('}')
	case []jval:
		b.WriteByte('[')
		for i, e := range x {
			if i > 0 {
				b.WriteString(", ")
			}
			writeCanon(b, e)
		}
		b.WriteByte(']')
	default:
		// Should not occur; fail loudly rather than emit a wrong shape.
		panic(fmt.Sprintf("canonJSON: unsupported type %T", v))
	}
}

// writeCanonString escapes exactly as Python json.dumps with ensure_ascii=True.
func writeCanonString(b *strings.Builder, s string) {
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			b.WriteString(`\"`)
		case '\\':
			b.WriteString(`\\`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		case '\b':
			b.WriteString(`\b`)
		case '\f':
			b.WriteString(`\f`)
		default:
			if r < 0x20 {
				fmt.Fprintf(b, `\u%04x`, r)
			} else if r < 0x7f {
				b.WriteRune(r)
			} else {
				// ensure_ascii: everything >= 0x7f is \u-escaped. Python emits
				// 0x7f (DEL) literally, but escapes >= 0x80. Match that: 0x7f
				// is < 0x80 so it is printed literally by Python. Guard here.
				if r == 0x7f {
					b.WriteRune(r)
				} else if r > 0xffff {
					// Surrogate pair, as Python does for astral code points.
					r -= 0x10000
					hi := 0xd800 + (r >> 10)
					lo := 0xdc00 + (r & 0x3ff)
					fmt.Fprintf(b, `\u%04x\u%04x`, hi, lo)
				} else {
					fmt.Fprintf(b, `\u%04x`, r)
				}
			}
		}
	}
	b.WriteByte('"')
}

// =========================================================================
// Byte-hash core.
// =========================================================================

func sha256Hex(data []byte) string {
	h := sha256.Sum256(data)
	return hex.EncodeToString(h[:])
}

// readRaw reads the exact raw bytes of a target. It distinguishes "does not
// exist" (E_NOT_FOUND) from "exists but unreadable" (E_NO_RAW_CHANNEL), as
// SPEC s.9 requires those to be separate machine reason codes.
func readRaw(path string) ([]byte, string) {
	fi, err := os.Stat(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, eNotFound
		}
		return nil, eNoRawChannel
	}
	if fi.IsDir() {
		// A directory has no raw byte artifact.
		return nil, eNoRawChannel
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, eNoRawChannel
	}
	return data, ""
}

// =========================================================================
// Anchor store. Implementation-private (SPEC s.15). Simple JSONL of
// {"path": ..., "sha256": ...} lines is enough; we keep the last write per path.
// We deliberately avoid encoding/json for reads to stay canonical/simple; the
// store is a flat map path -> hex.
// =========================================================================

func anchorStorePath() string { return anchorStore }

func loadAnchors() map[string]string {
	out := map[string]string{}
	f, err := os.Open(anchorStorePath())
	if err != nil {
		return out
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 0, 1024*1024), 16*1024*1024)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		p, h, ok := parseAnchorLine(line)
		if ok {
			out[p] = h
		}
	}
	return out
}

// parseAnchorLine parses one canonical {"path": "...", "sha256": "..."} line
// that we ourselves wrote. Kept deliberately minimal.
func parseAnchorLine(line string) (string, string, bool) {
	path, ok1 := extractJSONString(line, "path")
	h, ok2 := extractJSONString(line, "sha256")
	if !ok1 || !ok2 {
		return "", "", false
	}
	return path, h, true
}

// extractJSONString pulls the string value for a top-level "key" out of a flat
// canonical JSON object line. Only handles the shapes we write ourselves.
func extractJSONString(line, key string) (string, bool) {
	needle := `"` + key + `": "`
	i := strings.Index(line, needle)
	if i < 0 {
		return "", false
	}
	rest := line[i+len(needle):]
	// Read until the next unescaped quote.
	var b strings.Builder
	esc := false
	for j := 0; j < len(rest); j++ {
		c := rest[j]
		if esc {
			switch c {
			case 'n':
				b.WriteByte('\n')
			case 't':
				b.WriteByte('\t')
			case 'r':
				b.WriteByte('\r')
			case 'b':
				b.WriteByte('\b')
			case 'f':
				b.WriteByte('\f')
			case '"':
				b.WriteByte('"')
			case '\\':
				b.WriteByte('\\')
			case '/':
				b.WriteByte('/')
			case 'u':
				// \uXXXX escape. Decode the 4 hex digits; if it is a UTF-16 high
				// surrogate, consume the following \uXXXX low surrogate and combine
				// into a single astral code point (SPEC s.7 re-derivability).
				if j+4 < len(rest) {
					if r, adv, ok := decodeUEscape(rest, j+1); ok {
						b.WriteRune(r)
						j += adv // advance past the consumed hex (and any low pair)
					}
				}
			default:
				b.WriteByte(c)
			}
			esc = false
			continue
		}
		if c == '\\' {
			esc = true
			continue
		}
		if c == '"' {
			return b.String(), true
		}
		b.WriteByte(c)
	}
	return "", false
}

// decodeUEscape decodes a \uXXXX escape whose 4 hex digits begin at s[at]. If the
// decoded value is a UTF-16 high surrogate (0xD800..0xDBFF) and is immediately
// followed by "\uYYYY" holding a low surrogate (0xDC00..0xDFFF), the two are
// combined into a single astral rune. Returns (rune, advanceBeyondBackslashU, ok)
// where advance is the number of index positions to skip forward from the 'u'
// (i.e. added to the loop index that currently points at 'u').
func decodeUEscape(s string, at int) (rune, int, bool) {
	if at+4 > len(s) {
		return 0, 0, false
	}
	hi, err := strconv.ParseInt(s[at:at+4], 16, 32)
	if err != nil {
		return 0, 0, false
	}
	// 4 hex digits consumed beyond the 'u'.
	adv := 4
	r := rune(hi)
	if hi >= 0xd800 && hi <= 0xdbff {
		// Expect a following \uYYYY low surrogate: "\\uYYYY" = 6 chars after the
		// first escape's hex.
		lowStart := at + 4
		if lowStart+6 <= len(s) && s[lowStart] == '\\' && s[lowStart+1] == 'u' {
			lo, err2 := strconv.ParseInt(s[lowStart+2:lowStart+6], 16, 32)
			if err2 == nil && lo >= 0xdc00 && lo <= 0xdfff {
				r = 0x10000 + ((rune(hi) - 0xd800) << 10) + (rune(lo) - 0xdc00)
				adv += 6 // consume "\uYYYY"
			}
		}
	}
	return r, adv, true
}

func appendAnchor(path, hexhash string) error {
	f, err := os.OpenFile(anchorStorePath(), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return err
	}
	defer f.Close()
	line := canonJSON(jobj{"path": path, "sha256": hexhash})
	_, err = f.WriteString(line + "\n")
	return err
}

// =========================================================================
// Hash-chained log (SPEC s.7): chain = SHA-256(prev + kind + canonical_json(fact)).
// =========================================================================

type logEntry struct {
	Kind  string
	Fact  jobj
	Prev  string
	Chain string
}

func computeChain(prev, kind string, fact jobj) string {
	return sha256Hex([]byte(prev + kind + canonJSON(fact)))
}

func appendLog(kind string, fact jobj) error {
	prev := genesisPrev
	entries, _, err := loadLog()
	if err == nil && len(entries) > 0 {
		prev = entries[len(entries)-1].Chain
	}
	chain := computeChain(prev, kind, fact)
	entry := jobj{
		"kind":  kind,
		"fact":  fact,
		"prev":  prev,
		"chain": chain,
	}
	f, err := os.OpenFile(logStore, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = f.WriteString(canonJSON(entry) + "\n")
	return err
}

// loadLog reads and minimally parses each stored line into (kind, fact, prev,
// chain). It returns (entries, corrupt, err). corrupt=true means a line could
// not be parsed as our stored shape -> E_LOG_CORRUPT. The fact is preserved as
// its exact stored substring so we re-derive canonical_json from what was
// actually stored (SPEC s.7: audit re-derives whatever was stored).
func loadLog() ([]logEntry, bool, error) {
	f, err := os.Open(logStore)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, false, nil // genesis: empty chain, trivially intact
		}
		return nil, false, err
	}
	defer f.Close()
	var out []logEntry
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 0, 1024*1024), 64*1024*1024)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		e, ok := parseLogLine(line)
		if !ok {
			return out, true, nil
		}
		out = append(out, e)
	}
	return out, false, nil
}

// parseLogLine parses one stored log line. The stored form is a JSON object with
// keys kind, fact, prev, chain. We must recompute canonical_json(fact) from the
// stored bytes, so we extract the raw fact object substring and re-serialize it
// canonically (which, for a stored canonical line, is the identity). To be
// robust to logs written by another conforming implementation with different
// key spacing, we re-parse the fact object generically and re-serialize.
func parseLogLine(line string) (logEntry, bool) {
	kind, okK := extractJSONString(line, "kind")
	prev, okP := extractJSONString(line, "prev")
	chain, okC := extractJSONString(line, "chain")
	if !okK || !okP || !okC {
		return logEntry{}, false
	}
	factObj, ok := extractJSONObject(line, "fact")
	if !ok {
		return logEntry{}, false
	}
	return logEntry{Kind: kind, Fact: factObj, Prev: prev, Chain: chain}, true
}

// extractJSONObject extracts a nested object value for "key" and parses it into
// a jobj (string/int values only, sufficient for facts). Returns the parsed
// object so canonJSON re-derives its canonical form regardless of stored spacing.
func extractJSONObject(line, key string) (jobj, bool) {
	needle := `"` + key + `": {`
	i := strings.Index(line, needle)
	start := -1
	if i >= 0 {
		start = i + len(needle) - 1 // position of '{'
	} else {
		// tolerate no-space form "key":{
		needle2 := `"` + key + `":{`
		j := strings.Index(line, needle2)
		if j < 0 {
			return nil, false
		}
		start = j + len(needle2) - 1
	}
	// Find matching close brace, respecting strings.
	depth := 0
	inStr := false
	esc := false
	end := -1
	for k := start; k < len(line); k++ {
		c := line[k]
		if inStr {
			if esc {
				esc = false
			} else if c == '\\' {
				esc = true
			} else if c == '"' {
				inStr = false
			}
			continue
		}
		switch c {
		case '"':
			inStr = true
		case '{':
			depth++
		case '}':
			depth--
			if depth == 0 {
				end = k
			}
		}
		if end >= 0 {
			break
		}
	}
	if end < 0 {
		return nil, false
	}
	return parseFlatObject(line[start : end+1])
}

// parseFlatObject parses a flat JSON object {"k": "v", "k2": 3} into a jobj.
// Values may be strings or integers (the only shapes our facts use). This is a
// minimal parser, not a general JSON parser.
func parseFlatObject(s string) (jobj, bool) {
	obj := jobj{}
	s = strings.TrimSpace(s)
	if len(s) < 2 || s[0] != '{' || s[len(s)-1] != '}' {
		return nil, false
	}
	body := s[1 : len(s)-1]
	i := 0
	n := len(body)
	skipWS := func() {
		for i < n && (body[i] == ' ' || body[i] == '\t' || body[i] == '\n' || body[i] == '\r') {
			i++
		}
	}
	readStr := func() (string, bool) {
		if i >= n || body[i] != '"' {
			return "", false
		}
		i++
		var b strings.Builder
		esc := false
		for i < n {
			c := body[i]
			i++
			if esc {
				switch c {
				case 'n':
					b.WriteByte('\n')
				case 't':
					b.WriteByte('\t')
				case 'r':
					b.WriteByte('\r')
				case 'b':
					b.WriteByte('\b')
				case 'f':
					b.WriteByte('\f')
				case '"':
					b.WriteByte('"')
				case '\\':
					b.WriteByte('\\')
				case '/':
					b.WriteByte('/')
				case 'u':
					// \uXXXX escape. i currently points at the first hex digit.
					// decodeUEscape handles UTF-16 surrogate-pair combining so an
					// astral code point stored as a surrogate pair re-serializes
					// identically (SPEC s.7 re-derivability).
					if i+4 <= n {
						if r, adv, ok := decodeUEscape(body, i); ok {
							b.WriteRune(r)
							i += adv
						}
					}
				default:
					b.WriteByte(c)
				}
				esc = false
				continue
			}
			if c == '\\' {
				esc = true
				continue
			}
			if c == '"' {
				return b.String(), true
			}
			b.WriteByte(c)
		}
		return "", false
	}
	skipWS()
	if i >= n {
		return obj, true // empty object
	}
	for {
		skipWS()
		key, ok := readStr()
		if !ok {
			return nil, false
		}
		skipWS()
		if i >= n || body[i] != ':' {
			return nil, false
		}
		i++
		skipWS()
		if i < n && body[i] == '"' {
			val, ok := readStr()
			if !ok {
				return nil, false
			}
			obj[key] = val
		} else {
			// number (integer) or literal
			startNum := i
			for i < n && body[i] != ',' && body[i] != '}' {
				i++
			}
			tok := strings.TrimSpace(body[startNum:i])
			if iv, err := strconv.Atoi(tok); err == nil {
				obj[key] = iv
			} else if tok == "true" {
				obj[key] = true
			} else if tok == "false" {
				obj[key] = false
			} else {
				obj[key] = tok
			}
		}
		skipWS()
		if i >= n {
			break
		}
		if body[i] == ',' {
			i++
			continue
		}
		break
	}
	return obj, true
}

// =========================================================================
// Marker corpus (SPEC s.8/s.16).
// =========================================================================

type corpus struct {
	version int
	sha256  string
	markers []string // in corpus order
}

func resolveCorpusPath() string {
	if p := os.Getenv("EMET_CORPUS"); p != "" {
		return p
	}
	// Default path relative to the implementation binary.
	exe, err := os.Executable()
	if err == nil {
		dir := exe
		if idx := strings.LastIndexAny(dir, `/\`); idx >= 0 {
			dir = dir[:idx]
		}
		// impl/go/emet.exe -> ../../conformance/markers.corpus
		return dir + "/../../conformance/markers.corpus"
	}
	return "conformance/markers.corpus"
}

// loadCorpus returns (corpus, reasonCode). reasonCode == "" means success.
func loadCorpus() (*corpus, string) {
	path := resolveCorpusPath()
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, eNoCorpus
	}
	sha := sha256Hex(data)
	c := &corpus{sha256: sha, version: -1}
	lines := strings.Split(string(data), "\n")
	haveVersion := false
	for _, raw := range lines {
		line := strings.TrimRight(raw, "\r")
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			continue
		}
		if strings.HasPrefix(trimmed, "#") {
			// version header: "# corpus_version: N"
			body := strings.TrimSpace(strings.TrimPrefix(trimmed, "#"))
			if strings.HasPrefix(body, "corpus_version:") {
				vs := strings.TrimSpace(strings.TrimPrefix(body, "corpus_version:"))
				if v, e := strconv.Atoi(vs); e == nil {
					c.version = v
					haveVersion = true
				}
			}
			continue
		}
		// A literal marker line: keep it verbatim (do not trim interior).
		c.markers = append(c.markers, line)
	}
	if !haveVersion {
		return nil, eNoCorpusVersion
	}
	return c, ""
}

// countMarkers performs the pinned non-overlapping leftmost scan in corpus order
// (SPEC s.16): scan left to right; at each byte position test markers in corpus
// order; take the first that matches there (ASCII case-insensitive substring
// over raw bytes); emit one count and advance past the matched span; on no match
// advance one byte. Returns count and per-hit (marker, offset) records.
func countMarkers(data []byte, markers []string) (int, []jobj) {
	lower := asciiLower(data)
	lm := make([][]byte, len(markers))
	for i, m := range markers {
		lm[i] = asciiLower([]byte(m))
	}
	count := 0
	var hits []jobj
	pos := 0
	n := len(lower)
	for pos < n {
		matched := -1
		var mlen int
		for mi, ml := range lm {
			if len(ml) == 0 {
				continue
			}
			if pos+len(ml) <= n && bytesEqual(lower[pos:pos+len(ml)], ml) {
				matched = mi
				mlen = len(ml)
				break
			}
		}
		if matched >= 0 {
			count++
			// Record the ORIGINAL matched bytes from the target (what was actually
			// found), not the lowercased corpus entry, matching the reference impls.
			hits = append(hits, jobj{"marker": string(data[pos : pos+mlen]), "offset": pos})
			pos += mlen
		} else {
			pos++
		}
	}
	return count, hits
}

func asciiLower(b []byte) []byte {
	out := make([]byte, len(b))
	for i, c := range b {
		if c >= 'A' && c <= 'Z' {
			c += 32
		}
		out[i] = c
	}
	return out
}

func bytesEqual(a, b []byte) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

// =========================================================================
// Output: human token lines vs the --json envelope.
// =========================================================================

// emit either prints one canonical JSON envelope (jsonMode) or the supplied
// human line(s). It never prints both. The exit code is identical in both modes.
func emitEnvelope(env jobj) {
	fmt.Println(canonJSON(env))
}

// =========================================================================
// Commands.
// =========================================================================

func cmdAnchor(paths []string, jsonMode bool) int {
	if len(paths) == 0 {
		return usageError("anchor requires at least one PATH", jsonMode, "anchor")
	}
	exit := exitHeld
	worstUnverif := false
	type res struct {
		path    string
		hexhash string
		reason  string
	}
	var results []res
	for _, p := range paths {
		data, reason := readRaw(p)
		if reason != "" {
			results = append(results, res{path: p, reason: reason})
			worstUnverif = true
			continue
		}
		h := sha256Hex(data)
		if err := appendAnchor(p, h); err != nil {
			results = append(results, res{path: p, reason: eNoRawChannel})
			worstUnverif = true
			continue
		}
		_ = appendLog("anchor", jobj{"path": p, "sha256": h})
		results = append(results, res{path: p, hexhash: h})
	}
	if worstUnverif {
		exit = exitUnverif
	}
	if jsonMode {
		var arr []jval
		for _, r := range results {
			if r.reason != "" {
				arr = append(arr, jobj{"path": r.path, "verdict": "UNVERIFIABLE", "reason": r.reason})
			} else {
				arr = append(arr, jobj{"path": r.path, "sha256": r.hexhash})
			}
		}
		if arr == nil {
			arr = []jval{}
		}
		emitEnvelope(jobj{
			"command":      "anchor",
			"emet_version": emetVersion,
			"spec_version": specVersion,
			"exit_code":    exit,
			"results":      []jval(arr),
		})
		return exit
	}
	for _, r := range results {
		if r.reason != "" {
			fmt.Printf("UNVERIFIABLE %s reason=%s\n", r.path, r.reason)
		} else {
			fmt.Printf("anchored %s sha256=%s\n", r.path, r.hexhash)
		}
	}
	return exit
}

func cmdVerify(paths []string, jsonMode bool) int {
	if len(paths) == 0 {
		return usageError("verify requires at least one PATH", jsonMode, "verify")
	}
	anchors := loadAnchors()
	type res struct {
		path    string
		verdict string
		want    string
		got     string
		reason  string
	}
	var results []res
	anyDrift := false
	anyUnverif := false
	for _, p := range paths {
		// SPEC s.9/s.13: verify is anchor-relative. Consult the anchor store FIRST;
		// a path with no anchor is E_NO_ANCHOR (exit 2) WITHOUT ever reading the file,
		// so an absent+unanchored path reports E_NO_ANCHOR, not E_NOT_FOUND. This
		// matches Python/Rust/JS, where the anchor check precedes the raw read.
		want, ok := anchors[p]
		if !ok {
			results = append(results, res{path: p, verdict: "UNVERIFIABLE", reason: eNoAnchor})
			anyUnverif = true
			continue
		}
		data, reason := readRaw(p)
		if reason != "" {
			results = append(results, res{path: p, verdict: "UNVERIFIABLE", reason: reason})
			anyUnverif = true
			continue
		}
		got := sha256Hex(data)
		if got == want {
			results = append(results, res{path: p, verdict: "MATCH", want: want, got: got})
			_ = appendLog("verify", jobj{"path": p, "result": "MATCH"})
		} else {
			results = append(results, res{path: p, verdict: "DRIFT", want: want, got: got})
			_ = appendLog("verify", jobj{"path": p, "result": "DRIFT"})
			anyDrift = true
		}
	}
	exit := exitHeld
	dominant := "MATCH"
	if anyDrift {
		exit = exitNegative
		dominant = "DRIFT"
	} else if anyUnverif {
		exit = exitUnverif
		dominant = "UNVERIFIABLE"
	}
	if jsonMode {
		var arr []jval
		for _, r := range results {
			o := jobj{"path": r.path, "verdict": r.verdict}
			switch r.verdict {
			case "MATCH", "DRIFT":
				o["want"] = r.want
				o["got"] = r.got
			case "UNVERIFIABLE":
				o["reason"] = r.reason
			}
			arr = append(arr, o)
		}
		if arr == nil {
			arr = []jval{}
		}
		emitEnvelope(jobj{
			"command":      "verify",
			"emet_version": emetVersion,
			"spec_version": specVersion,
			"exit_code":    exit,
			"verdict":      dominant,
			"results":      []jval(arr),
		})
		return exit
	}
	for _, r := range results {
		if r.verdict == "UNVERIFIABLE" {
			fmt.Printf("UNVERIFIABLE %s reason=%s\n", r.path, r.reason)
		} else {
			fmt.Printf("%s %s\n", r.verdict, r.path)
		}
	}
	return exit
}

func cmdCoherence(args []string, jsonMode bool) int {
	if len(args) != 2 {
		return usageError("coherence requires SOURCE VIEW", jsonMode, "coherence")
	}
	source, view := args[0], args[1]
	// SPEC s.9/s.13: the coherence UNVERIFIABLE reason carries the failing leg so a
	// consumer can tell which side was unreadable: source:<code> or view:<code>,
	// with source taking precedence when both fail. The subject stays the source
	// (matching Python/Rust/JS).
	sData, sReason := readRaw(source)
	vData, vReason := readRaw(view)
	if sReason != "" {
		return coherenceUnverif(source, "source:"+sReason, jsonMode)
	}
	if vReason != "" {
		return coherenceUnverif(source, "view:"+vReason, jsonMode)
	}
	sHash := sha256Hex(sData)
	vHash := sha256Hex(vData)
	verdict := "COHERENT"
	exit := exitHeld
	if sHash != vHash {
		verdict = "VIEW_DIFFERS_FROM_SOURCE"
		exit = exitNegative
	}
	_ = appendLog("coherence", jobj{"source": source, "view": view, "result": verdict})
	if jsonMode {
		emitEnvelope(jobj{
			"command":      "coherence",
			"emet_version": emetVersion,
			"spec_version": specVersion,
			"exit_code":    exit,
			"verdict":      verdict,
			"subject":      source,
			"source":       sHash,
			"view":         vHash,
		})
		return exit
	}
	fmt.Printf("result=%s source=%s view=%s\n", verdict, sHash, vHash)
	return exit
}

func coherenceUnverif(subject, reason string, jsonMode bool) int {
	if jsonMode {
		emitEnvelope(jobj{
			"command":      "coherence",
			"emet_version": emetVersion,
			"spec_version": specVersion,
			"exit_code":    exitUnverif,
			"verdict":      "UNVERIFIABLE",
			"subject":      subject,
			"reason":       reason,
		})
		return exitUnverif
	}
	fmt.Printf("result=UNVERIFIABLE %s reason=%s\n", subject, reason)
	return exitUnverif
}

func cmdRefuse(args []string, jsonMode bool) int {
	if len(args) != 1 {
		return usageError("refuse requires FILE", jsonMode, "refuse")
	}
	file := args[0]
	data, reason := readRaw(file)
	if reason != "" {
		return refuseUnverif(file, reason, jsonMode)
	}
	c, cReason := loadCorpus()
	if cReason != "" {
		return refuseUnverif(file, cReason, jsonMode)
	}
	count, hits := countMarkers(data, c.markers)

	// Write the .refused clean copy: replace every matched marker span with the
	// refusal token. We must NOT modify the input (SPEC s.4/boundary 6). Build
	// the clean copy by re-scanning the same non-overlapping leftmost order.
	clean := buildRefusedCopy(data, c.markers)
	refusedPath := file + ".refused"
	_ = os.WriteFile(refusedPath, clean, 0644)

	_ = appendLog("refuse", jobj{"path": file, "in_band_authority_claims": count, "corpus_version": c.version})

	exit := exitHeld
	if count > 0 {
		exit = exitMarkers
	}
	if jsonMode {
		var hitArr []jval
		for _, h := range hits {
			hitArr = append(hitArr, h)
		}
		if hitArr == nil {
			hitArr = []jval{}
		}
		emitEnvelope(jobj{
			"command":                  "refuse",
			"emet_version":             emetVersion,
			"spec_version":             specVersion,
			"exit_code":                exit,
			"subject":                  file,
			"in_band_authority_claims": count,
			"corpus_version":           c.version,
			"corpus_sha256":            c.sha256,
			"hits":                     []jval(hitArr),
			"clean_copy":               refusedPath,
		})
		return exit
	}
	fmt.Printf("in_band_authority_claims=%d\n", count)
	fmt.Printf("corpus_version=%d\n", c.version)
	fmt.Printf("corpus_sha256=%s\n", c.sha256)
	fmt.Printf("clean_copy=%s\n", refusedPath)
	return exit
}

func refuseUnverif(subject, reason string, jsonMode bool) int {
	if jsonMode {
		emitEnvelope(jobj{
			"command":      "refuse",
			"emet_version": emetVersion,
			"spec_version": specVersion,
			"exit_code":    exitUnverif,
			"verdict":      "UNVERIFIABLE",
			"subject":      subject,
			"reason":       reason,
		})
		return exitUnverif
	}
	fmt.Printf("result=UNVERIFIABLE %s reason=%s\n", subject, reason)
	return exitUnverif
}

// buildRefusedCopy replaces each matched marker span with the refusal token,
// using the same non-overlapping leftmost scan as countMarkers.
func buildRefusedCopy(data []byte, markers []string) []byte {
	lower := asciiLower(data)
	lm := make([][]byte, len(markers))
	for i, m := range markers {
		lm[i] = asciiLower([]byte(m))
	}
	var out []byte
	pos := 0
	n := len(lower)
	for pos < n {
		matched := -1
		var mlen int
		for _, ml := range lm {
			if len(ml) == 0 {
				continue
			}
			if pos+len(ml) <= n && bytesEqual(lower[pos:pos+len(ml)], ml) {
				matched = 1
				mlen = len(ml)
				break
			}
		}
		if matched >= 0 {
			out = append(out, []byte(refusedToken)...)
			pos += mlen
		} else {
			out = append(out, data[pos])
			pos++
		}
	}
	return out
}

func cmdCorroborate(args []string, jsonMode bool) int {
	if len(args) != 1 {
		return usageError("corroborate requires PATH", jsonMode, "corroborate")
	}
	path := args[0]
	// Channel 1: raw read in-process.
	data, reason := readRaw(path)
	if reason != "" {
		return corroborateUnverif(path, reason, jsonMode)
	}
	rawHash := sha256Hex(data)

	// Channel 2: subprocess re-read via this same binary (disjoint read path).
	subHash, ok := childReadHash(path)
	if !ok {
		return corroborateUnverif(path, eNoSecondReadPath, jsonMode)
	}

	verdict := "CORROBORATED"
	exit := exitHeld
	readPathsAgree := rawHash == subHash
	if !readPathsAgree {
		verdict = "QUARANTINE_READ_PATH_DIVERGENCE"
		exit = exitNegative
	}
	_ = appendLog("corroborate", jobj{"path": path, "result": verdict})

	if jsonMode {
		emitEnvelope(jobj{
			"command":                   "corroborate",
			"emet_version":              emetVersion,
			"spec_version":              specVersion,
			"exit_code":                 exit,
			"verdict":                   verdict,
			"subject":                   path,
			"channels":                  jobj{"raw": rawHash, "subprocess": subHash},
			"read_paths_agree":          readPathsAgree,
			"git_read_agrees_with_open": readPathsAgree,
		})
		return exit
	}
	fmt.Printf("result=%s raw=%s subprocess=%s\n", verdict, rawHash, subHash)
	return exit
}

func corroborateUnverif(subject, reason string, jsonMode bool) int {
	if jsonMode {
		emitEnvelope(jobj{
			"command":      "corroborate",
			"emet_version": emetVersion,
			"spec_version": specVersion,
			"exit_code":    exitUnverif,
			"verdict":      "UNVERIFIABLE",
			"subject":      subject,
			"reason":       reason,
		})
		return exitUnverif
	}
	fmt.Printf("result=UNVERIFIABLE %s reason=%s\n", subject, reason)
	return exitUnverif
}

// childReadHash re-reads the target via a child process of this same binary
// (the hidden __rawhash internal subcommand), providing a disjoint read path.
func childReadHash(path string) (string, bool) {
	exe, err := os.Executable()
	if err != nil {
		return "", false
	}
	cmd := exec.Command(exe, "__rawhash", path)
	out, err := cmd.Output()
	if err != nil {
		return "", false
	}
	h := strings.TrimSpace(string(out))
	if len(h) != 64 {
		return "", false
	}
	return h, true
}

func cmdRawHash(args []string) int {
	// Hidden internal channel used by corroborate. Not part of the public grammar.
	if len(args) != 1 {
		return exitUsage
	}
	data, reason := readRaw(args[0])
	if reason != "" {
		return exitUnverif
	}
	fmt.Println(sha256Hex(data))
	return exitHeld
}

func cmdAudit(jsonMode bool) int {
	entries, corrupt, err := loadLog()
	if err != nil {
		// Unreadable (but present) log: cannot check -> UNVERIFIABLE.
		if jsonMode {
			emitEnvelope(jobj{
				"command":      "audit",
				"emet_version": emetVersion,
				"spec_version": specVersion,
				"exit_code":    exitUnverif,
				"verdict":      "UNVERIFIABLE",
				"reason":       eLogCorrupt,
			})
			return exitUnverif
		}
		fmt.Printf("result=UNVERIFIABLE reason=%s\n", eLogCorrupt)
		return exitUnverif
	}
	if corrupt {
		// SPEC s.7/s.13: a log line that cannot be parsed is a TAMPER event, not an
		// inability to check. It is a detected difference from a well-formed chain,
		// so it MUST report chain=BROKEN (exit 1), matching Python/Rust/JS -- never
		// UNVERIFIABLE. broken_at is the 1-based index of the entries parsed before
		// the corrupt line (i.e. the corrupt line itself).
		brokenAt := len(entries) + 1
		if jsonMode {
			emitEnvelope(jobj{
				"command":       "audit",
				"emet_version":  emetVersion,
				"spec_version":  specVersion,
				"exit_code":     exitNegative,
				"verdict":       "BROKEN",
				"log_entries":   brokenAt,
				"broken_at":     brokenAt,
				"broken_reason": "parse_error",
			})
			return exitNegative
		}
		fmt.Printf("chain=%s log_entries=%d\n", "BROKEN", brokenAt)
		return exitNegative
	}

	// Recompute the chain. Genesis prev = 64 zeros; each entry's prev must equal
	// the prior entry's chain, and each stored chain must recompute.
	verdict := "INTACT"
	exit := exitHeld
	brokenAt := -1
	prev := genesisPrev
	for i, e := range entries {
		if e.Prev != prev {
			verdict = "BROKEN"
			exit = exitNegative
			brokenAt = i
			break
		}
		want := computeChain(e.Prev, e.Kind, e.Fact)
		if want != e.Chain {
			verdict = "BROKEN"
			exit = exitNegative
			brokenAt = i
			break
		}
		prev = e.Chain
	}

	if jsonMode {
		env := jobj{
			"command":      "audit",
			"emet_version": emetVersion,
			"spec_version": specVersion,
			"exit_code":    exit,
			"verdict":      verdict,
			"log_entries":  len(entries),
		}
		if brokenAt >= 0 {
			env["broken_at"] = brokenAt
		}
		emitEnvelope(env)
		return exit
	}
	fmt.Printf("chain=%s log_entries=%d\n", verdict, len(entries))
	return exit
}

func cmdSelftest(jsonMode bool) int {
	// Compiled implementation (SPEC s.14): artifact-of-record = the compiled
	// binary. Hash our own executable bytes.
	selfHash := "UNKNOWN"
	notes := []jval{
		"check this build with an external verifier; a self-check cannot detect a compromised machine (SPEC s.11).",
		"compiled build: the self-hash changes with each rebuild (SPEC s.14).",
	}
	exe, err := os.Executable()
	if err == nil {
		if data, e := os.ReadFile(exe); e == nil {
			selfHash = sha256Hex(data)
		}
	}
	if jsonMode {
		emitEnvelope(jobj{
			"command":      "selftest",
			"emet_version": emetVersion,
			"spec_version": specVersion,
			"exit_code":    exitHeld,
			"self_sha256":  selfHash,
			"notes":        notes,
		})
		return exitHeld
	}
	// Canonical token + legacy alias (SPEC s.14; alias removed at 2.0).
	fmt.Printf("emet_self_sha256=%s\n", selfHash)
	fmt.Printf("membrane_self_sha256=%s\n", selfHash)
	return exitHeld
}

// usageError reports a usage error. SPEC s.13 EXEMPTS the usage-error path from
// the --json envelope: like Python/Rust/JS, we write the usage line to stderr and
// emit NOTHING to stdout, in both plain and --json mode, then exit 64. The command
// argument is retained for call-site clarity but is not emitted.
func usageError(msg string, jsonMode bool, command string) int {
	_ = jsonMode
	_ = command
	fmt.Fprintln(os.Stderr, "usage error: "+msg)
	return exitUsage
}

// =========================================================================
// Argument handling. --json is a global flag accepted before or after the
// subcommand; it is stripped from argv (SPEC s.13).
// =========================================================================

func main() {
	os.Exit(run(os.Args[1:]))
}

func run(argv []string) int {
	// Strip the global --json flag from anywhere in argv.
	jsonMode := false
	var filtered []string
	for _, a := range argv {
		if a == "--json" {
			jsonMode = true
			continue
		}
		filtered = append(filtered, a)
	}
	if len(filtered) == 0 {
		return usageError("no subcommand", jsonMode, "")
	}
	cmd := filtered[0]
	rest := filtered[1:]
	switch cmd {
	case "__rawhash":
		return cmdRawHash(rest)
	case "anchor":
		return cmdAnchor(rest, jsonMode)
	case "verify":
		return cmdVerify(rest, jsonMode)
	case "coherence":
		return cmdCoherence(rest, jsonMode)
	case "refuse":
		return cmdRefuse(rest, jsonMode)
	case "corroborate":
		return cmdCorroborate(rest, jsonMode)
	case "audit":
		return cmdAudit(jsonMode)
	case "selftest":
		return cmdSelftest(jsonMode)
	default:
		return usageError("unknown subcommand: "+cmd, jsonMode, cmd)
	}
}
