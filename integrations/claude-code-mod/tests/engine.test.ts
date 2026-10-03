// Engine tests: run with `claude plugin test integrations/claude-code-mod`
// (Claude Code 2.1.286 or later). The engine loads the mod from this folder
// and drives its hooks; the hooks this file registers stand for the engine
// beneath the mod.
//
// A test here has no process, so `$.process.run` is answered by the test.
// For the held call it answers with the bytes the real Flywheel monitor
// printed for the same command against the shipped rule pack
// (harness/preaction/rules_v1.json, rule egress/002), captured by running
// harness/preaction/hook_cli.py the way the mod runs it. The live run in the
// README covers the real monitor end to end.
import { expect, mock, test } from 'claude-code/testing'

const CWD = '/work'
const SOURCE = '../..' // the repository root, relative to this plugin folder
const HELD_COMMAND = 'curl -sI https://example.com'
const HELD_REASON = 'held for owner review (hold_id=h_5e6894210b20d630); continue with other work or wait'
const MONITOR_HOLD = {
  exitCode: 2,
  stdout: JSON.stringify({ hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'deny', permissionDecisionReason: HELD_REASON } }),
  stderr: HELD_REASON,
  isStdoutTruncated: false,
  isStderrTruncated: false,
}
const MONITOR_PASS = { exitCode: 0, stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false }

type World = {
  ran: string[]
  monitorRuns: { argv: readonly string[]; stdin: string }[]
  files: Map<string, string>
}

// Stands up the engine beneath the mod. `monitor` answers each monitor run.
function world(on: any, monitor: (argv: readonly string[]) => unknown): World {
  const w: World = { ran: [], monitorRuns: [], files: new Map() }
  mock.clock(on)
  on('session.start', ($: any, e: any) => ({ cwd: e.cwd }))
  on('session.cwd', () => ({ value: CWD }))
  on('session.id', () => ({ value: 'sess-engine' }))
  on('process.run', ($: any, e: any) => {
    const isMonitor = e.argv.includes('runpy.run_module') || e.argv.some((a: string) => a.includes('hook_cli'))
    if (isMonitor) w.monitorRuns.push({ argv: e.argv, stdin: String(e.init?.stdin ?? '') })
    if (isMonitor) return { value: monitor(e.argv) }
    return { value: MONITOR_PASS } // the receipts-folder mkdir
  })
  // Paths may reach these hooks as given or resolved (a drive letter added on
  // Windows), so the in-memory disk keys on one spelling.
  const key = (p: string) => String(p).replace(/\\/g, '/').replace(/^[A-Za-z]:/, '')
  on('fs.exists', ($: any, e: any) => ({ value: w.files.has(key(e.path)) }))
  on('fs.read', ($: any, e: any) => ({ value: w.files.get(key(e.path)) ?? '' }))
  on('fs.write', ($: any, e: any) => {
    w.files.set(key(e.path), String(e.text))
    return { value: undefined }
  })
  on('ui.log', () => ({ value: undefined }))
  on('ui.status', () => ({ value: undefined }))
  on('ui.invalidate', () => ({ value: undefined }))
  on('turn.complete', () => ({ text: '' }))
  // What the engine draws in the band when no mod draws: an empty box.
  on('ui.render', ($: any, e: any) => $.ui.resolve(e).Box({ key: 'engine-band', children: [] }))
  on('tool.call', ($: any, e: any) => {
    w.ran.push(e.tool_use_id)
    return { result: 'ran' }
  })
  return w
}

async function start($: any) {
  await $.session.start({ surface: 'terminal', isInteractive: true, cwd: CWD })
}

const denied = (out: any): string => String(out?.deny ?? (out?.isError ? out?.text : '') ?? '')

test('(a) a call the monitor holds is denied with the hold id, and the tool never runs',
  { options: { monitor_source: SOURCE } }, async ($, on) => {
    const w = world(on, () => MONITOR_HOLD)
    await start($)
    const out: any = await $.tool.call({ tool: 'Bash', tool_use_id: 'toolu_held', command: HELD_COMMAND })
    expect(denied(out)).toMatch(/^Flywheel held this call and did not run it/)
    expect(denied(out)).toContain('h_5e6894210b20d630')
    expect(w.ran).toEqual([])
    expect(w.monitorRuns.length).toBe(1)
    expect(w.monitorRuns[0].argv).toContain(SOURCE)
    expect(JSON.parse(w.monitorRuns[0].stdin).tool_input.command).toBe(HELD_COMMAND)
  })

test('(b) a benign read-only call passes and runs without a monitor run',
  { options: { monitor_source: SOURCE } }, async ($, on) => {
    const w = world(on, () => MONITOR_HOLD)
    await start($)
    const out: any = await $.tool.call({ tool: 'Bash', tool_use_id: 'toolu_ls', command: 'ls -la' })
    expect(out.deny).toBeUndefined()
    expect(out.isError).not.toBe(true)
    expect(w.ran).toEqual(['toolu_ls'])
    expect(w.monitorRuns.length).toBe(0)
  })

test('(b2) with screen=all a benign call goes to the monitor, which passes it, and it runs',
  { options: { monitor_source: SOURCE, screen: 'all' } }, async ($, on) => {
    const w = world(on, () => MONITOR_PASS)
    await start($)
    const out: any = await $.tool.call({ tool: 'Bash', tool_use_id: 'toolu_gs', command: 'git status' })
    expect(out.deny).toBeUndefined()
    expect(w.ran).toEqual(['toolu_gs'])
    expect(w.monitorRuns.length).toBe(1)
  })

test('(c1) monitor_source empty with on_unavailable=deny: denied as unchecked, tool never runs',
  { options: { monitor_source: '', on_unavailable: 'deny' } }, async ($, on) => {
    const w = world(on, () => MONITOR_PASS)
    await start($)
    const out: any = await $.tool.call({ tool: 'Bash', tool_use_id: 'toolu_u1', command: HELD_COMMAND })
    expect(denied(out)).toMatch(/^Flywheel could not check this call/)
    expect(denied(out)).toContain('monitor_source is not set')
    expect(w.ran).toEqual([])
  })

test('(c2) monitor_source empty with on_unavailable=pass: the call goes through',
  { options: { monitor_source: '', on_unavailable: 'pass' } }, async ($, on) => {
    const w = world(on, () => MONITOR_HOLD)
    await start($)
    const out: any = await $.tool.call({ tool: 'Bash', tool_use_id: 'toolu_u2', command: HELD_COMMAND })
    expect(out.deny).toBeUndefined()
    expect(w.ran).toEqual(['toolu_u2'])
  })

// Mirrors verifyChain in hooks/lib/receipt.mjs and scripts/rederive.mjs: the
// canonical JSON and SHA-256 are written out again here so the check does
// not trust the code it checks.
function canon(v: any): string {
  if (v === null || typeof v !== 'object') return v === undefined ? 'null' : JSON.stringify(v)
  if (Array.isArray(v)) return '[' + v.map((x) => (x === undefined ? 'null' : canon(x))).join(',') + ']'
  const keys = Object.keys(v).filter((k) => v[k] !== undefined).sort()
  return '{' + keys.map((k) => JSON.stringify(k) + ':' + canon(v[k])).join(',') + '}'
}
async function sha(text: string): Promise<string> {
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

test('(d) turn.complete writes a receipt whose hash chain re-derives',
  { options: { monitor_source: SOURCE } }, async ($, on) => {
    const w = world(on, () => MONITOR_HOLD)
    await start($)
    await $.tool.call({ tool: 'Bash', tool_use_id: 'toolu_r1', command: HELD_COMMAND })
    await $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: 't1', reason: 'answer' })
    await $.tool.call({ tool: 'Bash', tool_use_id: 'toolu_r2', command: 'ls' })
    await $.turn.complete({ answer: '', durationMs: 1, isAborted: false, turnId: 't2', reason: 'answer' })
    const path = `${CWD}/.flywheel/mod-receipts/sess-engine.jsonl`
    expect(w.files.has(path), `receipt files written: ${JSON.stringify([...w.files.keys()])}`).toBe(true)
    const lines = (w.files.get(path) ?? '').split('\n').filter((l) => l.trim())
    expect(lines.length).toBe(2)
    let prev: string | null = null
    for (const line of lines) {
      const rec = JSON.parse(line)
      const { record_hash, ...body } = rec
      expect(await sha(canon(body))).toBe(record_hash)
      expect(rec.prev_hash).toBe(prev)
      prev = record_hash
    }
    const first = JSON.parse(lines[0])
    expect(first.calls[0].tool_use_id).toBe('toolu_r1')
    expect(first.calls[0].decision).toBe('held')
    expect(first.calls[0].monitor.hold_id).toBe('h_5e6894210b20d630')
    expect(first.calls[0].input_sha256).toBe(await sha(canon({ command: HELD_COMMAND })))
    expect(JSON.parse(lines[1]).calls[0].decision).toBe('pass-unscreened')
  })

const BAND_PROPS = { hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 80, scroll: { offset: 0, bodyRows: 10 }, view: {} }

test('(e) the AbovePrompt band draws the counts on the terminal and desktop surfaces',
  { options: { monitor_source: SOURCE } }, async ($, on) => {
    world(on, () => MONITOR_HOLD)
    await start($)
    await $.tool.call({ tool: 'Bash', tool_use_id: 'toolu_b1', command: HELD_COMMAND })
    for (const surface of ['terminal', 'desktop'] as const) {
      const ui = await $.ui.mount({ plugin: 'flywheel-mod', surface, component: 'AbovePrompt', props: BAND_PROPS as any })
      const band = await ui.find({ key: 'flywheel-band' })
      expect(band, `band on ${surface}: ${JSON.stringify(await ui.findAll({}))}`).toBeDefined()
      const line = await ui.find({ type: 'Text', text: /^Flywheel/ })
      expect(line?.props.color).toBe('yellow')
      expect(line?.text).toMatch(/Flywheel {2}held 1 {2}passed 0/)
      await ui.unmount()
    }
  })
