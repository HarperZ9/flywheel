// Tests for `claude plugin test` (Claude Code 2.1.287 or later), written to
// the documented test kit. NOT RUN: the machine this was built on has Claude
// Code 2.1.251, which has no mods runtime. The Node suite (tests/*.test.mjs)
// runs the same checks against a stand-in runtime; this file is the version
// to run once a 2.1.287+ build is available.
import { expect, mock, test } from 'claude-code/testing'

const HOLD = {
  exitCode: 2,
  stdout: JSON.stringify({ hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'deny',
    permissionDecisionReason: 'held for owner review (hold_id=h_0123456789abcdef); continue with other work or wait' } }),
  stderr: '',
}
const PASS = { exitCode: 0, stdout: '', stderr: '' }

function stubSession(on: any, runStub: () => unknown, ran: string[]) {
  mock.clock(on)
  on('session.start', () => ({ cwd: '/work' }))
  on('session.cwd', () => ({ value: '/work' }))
  on('session.id', () => ({ value: 'sess-1' }))
  on('process.run', runStub)
  on('fs.exists', () => ({ value: false }))
  on('fs.read', () => ({ value: '' }))
  on('fs.write', () => ({ value: undefined }))
  on('ui.log', () => ({ value: undefined }))
  on('ui.status', () => ({ value: undefined }))
  on('turn.complete', () => ({ text: '' }))
  on('tool.call', ($: any, e: any) => {
    ran.push(e.tool_use_id)
    return { result: 'ok' }
  })
}

test('a monitor hold becomes { deny } and the tool never runs', async ($, on) => {
  const ran: string[] = []
  stubSession(on, () => ({ value: HOLD }), ran)
  await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/work' })
  const out: any = await $.tool.call({ tool: 'Bash', tool_use_id: 'toolu_1', command: 'rm -rf build' })
  expect(typeof out.deny).toBe('string')
  expect(out.deny).toMatch(/^Flywheel held this call and did not run it/)
  expect(ran).toEqual([])
})

test('a monitor pass runs the tool and returns its result', async ($, on) => {
  const ran: string[] = []
  stubSession(on, () => ({ value: PASS }), ran)
  await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/work' })
  const out: any = await $.tool.call({ tool: 'Bash', tool_use_id: 'toolu_2', command: 'rm -rf build' })
  expect(out.deny).toBeUndefined()
  expect(ran).toEqual(['toolu_2'])
})

test('the mod never approves at tool.check: the engine decision passes through unchanged', async ($, on) => {
  const ran: string[] = []
  stubSession(on, () => ({ value: PASS }), ran)
  on('tool.check', () => ({ decision: 'ask', reason: 'engine' }))
  await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/work' })
  const out: any = await $.tool.check({ tool: 'Bash', input: { command: 'rm -rf build' } })
  expect(out.decision).toBe('ask')
})

test('a monitor that cannot start fails closed', async ($, on) => {
  const ran: string[] = []
  stubSession(on, () => ({ deny: 'spawn python ENOENT' }), ran)
  await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/work' })
  const out: any = await $.tool.call({ tool: 'Bash', tool_use_id: 'toolu_3', command: 'rm -rf build' })
  expect(out.deny).toMatch(/the mod fails closed/)
  expect(ran).toEqual([])
})
