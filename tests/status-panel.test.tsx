import type { CommandRunInput, On, RenderInput, SessionStartInput } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'

const SESSION_ID = 'sess-1'
const SESSION: SessionStartInput = { surface: 'terminal', isInteractive: true, cwd: '/src/acme' }
const ESC = '\x1b'
// Styled as beacon's status lines style a CR: STATUSLINE_CR_SGR on the ref, STATUSLINE_TITLE_SGR on its title.
const STATUSLINE = `⏸ back after standup · ${ESC}[1;37m${ESC}]8;;https://example.com/acme/pull/7${ESC}\\!7${ESC}[22;2;37m Fix the widget${ESC}]8;;${ESC}\\${ESC}[0m\n`
const PICKER = JSON.stringify([{ hash: 'bbbbbbbbbbbbbbbb', label: 'other: docs (needs you)', color_state: 'blocked' }])
const HEAD = JSON.stringify({ project: 'acme', branch: 'fix-widget', task: 'widgets', mode: null, color_state: 'idle', anchor_cwd: '/src/acme/packages/widget', branch_sync: '↑2', branch_slot: 'diverged', branch_url: 'https://github.com/acme/acme/tree/fix-widget', forge: 'github', code_label: 'code' })

const BAND: RenderInput<'AbovePrompt', 'terminal'> = {
  component: 'AbovePrompt',
  surface: 'terminal',
  requestId: 'band',
  plugin: 'beacon',
  props: { hasSurvey: false, isCollapsed: false, isWorking: false, maxRows: 10, bodyColumns: 100, scroll: { offset: 0, bodyRows: 10 } },
} as RenderInput<'AbovePrompt', 'terminal'>

const PAUSED = JSON.stringify({
  ...JSON.parse(HEAD),
  mode: { name: 'pause', note: 'waiting for the *VPN*', glyph: '⏸', label: 'paused', band: '#44385f', note_line: `waiting for the ${ESC}[3mVPN${ESC}[23m` },
})

const FOOTER: RenderInput<'SessionMode', 'terminal'> = {
  component: 'SessionMode',
  surface: 'terminal',
  requestId: 'footer',
  props: { modes: ['memory paused'] },
} as RenderInput<'SessionMode', 'terminal'>

/** The modes the footer is handed once beacon's hook has run, read by a hook beneath it. */
function footerOf(on: On) {
  const footer = { modes: [] as readonly string[] }
  on('ui.render', { component: 'SessionMode' }, ($, e) => {
    footer.modes = e.props.modes
    return { type: 'engine', ref: 0 }
  })
  return footer
}

const commandOf = (args = ''): CommandRunInput => ({
  command: 'beacon',
  args,
  origin: { kind: 'composer' },
  presentation: { isFullscreen: true, columns: 160 },
})

type Reply = { exitCode: number; stdout: string; stderr: string; isStdoutTruncated: boolean; isStderrTruncated: boolean }
const ok = (stdout: string): Reply => ({ exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false })

/** The engine and the beacon CLI beneath the hooks module, in memory. */
function worldOf(on: On, { head = HEAD, statusline = STATUSLINE } = {}) {
  const world = { runs: [] as string[][], commands: [] as string[], toasts: [] as string[] }
  mock.clock(on)
  on('process.hookEnv', () => ({ value: { CLAUDE_PLUGIN_ROOT: '/plugins/beacon', CLAUDE_CODE_SESSION_ID: SESSION_ID } }))
  on('session.root', () => ({ value: '/src/acme' }))
  on('process.run', ($, e) => {
    const args = e.argv.slice(e.argv.findIndex(arg => arg.endsWith('/scripts/beacon')) + 1)
    world.runs.push([...args])
    if (args[0] === 'status-panel') {
      const lines = statusline.split('\n').filter(l => l !== '')
      return { value: ok(`${JSON.stringify({ ...JSON.parse(head), lines })}\n`) }
    }
    if (args[0] === 'pick' && args[1] === '--json') return { value: ok(PICKER) }
    return { value: ok('') }
  })
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('session.id', () => ({ value: SESSION_ID }))
  on('command.register', ($, e) => {
    world.commands.push(e.name)
    return { value: { command: e.name } }
  })
  on('ui.toast', ($, e) => {
    world.toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.invalidate', () => ({ value: undefined }))
  return world
}

/** The text a drawn tree shows, Button and Link labels included. */
function textOf(tree: unknown): string {
  if (typeof tree === 'string' || typeof tree === 'number') return String(tree)
  if (Array.isArray(tree)) return tree.map(textOf).join('')
  if (typeof tree !== 'object' || !tree) return ''
  const props: unknown = Reflect.get(tree, 'props')
  const prop = (name: string): unknown => (typeof props === 'object' && props ? Reflect.get(props, name) : undefined)
  const text = textOf(Reflect.get(tree, 'children') ?? prop('children') ?? [])
  const label = prop('label')
  return text === '' && typeof label === 'string' ? label : text
}

/** Every Link's href in a drawn tree. */
function hrefsOf(tree: unknown): string[] {
  if (Array.isArray(tree)) return tree.flatMap(hrefsOf)
  if (typeof tree !== 'object' || !tree) return []
  const props: unknown = Reflect.get(tree, 'props')
  const href = typeof props === 'object' && props ? Reflect.get(props, 'href') : undefined
  const children = Reflect.get(tree, 'children') ?? (typeof props === 'object' && props ? Reflect.get(props, 'children') : undefined) ?? []
  return [...(typeof href === 'string' ? [href] : []), ...hrefsOf(children)]
}

/** The props of the Text that draws exactly `text`. */
function propsOf(tree: unknown, text: string): Record<string, unknown> | undefined {
  if (Array.isArray(tree)) return tree.map(t => propsOf(t, text)).find(Boolean)
  if (typeof tree !== 'object' || !tree) return undefined
  const props = Reflect.get(tree, 'props') as Record<string, unknown> | undefined
  const children: unknown = Reflect.get(tree, 'children') ?? props?.children ?? []
  if (Reflect.get(tree, 'type') === 'Text' && textOf(children) === text) return props
  return propsOf(children, text)
}

/** Every fixed-width column in a drawn tree, top to bottom: the project's on the head row, then the gutter of each row under it. */
function gutterOf(tree: unknown): number[] {
  if (Array.isArray(tree)) return tree.flatMap(gutterOf)
  if (typeof tree !== 'object' || !tree) return []
  const props = Reflect.get(tree, 'props') as Record<string, unknown> | undefined
  const children: unknown = Reflect.get(tree, 'children') ?? props?.children ?? []
  const own = Reflect.get(tree, 'type') === 'Box' && typeof props?.width === 'number' ? [props.width] : []
  return [...own, ...gutterOf(children)]
}

/** The props of the outermost Box that paints a background: the slab. */
function slabOf(tree: unknown): Record<string, unknown> | undefined {
  if (Array.isArray(tree)) return tree.map(slabOf).find(Boolean)
  if (typeof tree !== 'object' || !tree) return undefined
  const props = Reflect.get(tree, 'props') as Record<string, unknown> | undefined
  if (Reflect.get(tree, 'type') === 'Box' && props?.backgroundColor) return props
  return slabOf(Reflect.get(tree, 'children') ?? props?.children ?? [])
}

const PAUSED_NO_NOTE = JSON.stringify({ ...JSON.parse(PAUSED), mode: { ...JSON.parse(PAUSED).mode, note: null, note_line: null } })

/** The hover overrides of the Text drawing `text`, which the engine carries beside its props. */
function hoverOf(tree: unknown, text: string): unknown {
  if (Array.isArray(tree)) return tree.map(t => hoverOf(t, text)).find(Boolean)
  if (typeof tree !== 'object' || !tree) return undefined
  const props = Reflect.get(tree, 'props') as Record<string, unknown> | undefined
  const children: unknown = Reflect.get(tree, 'children') ?? props?.children ?? []
  if (Reflect.get(tree, 'type') === 'Text' && textOf(children) === text) return Reflect.get(tree, 'hover')
  return hoverOf(children, text)
}

/** The session's start, and the first read it kicks off without waiting on. */
async function started($: { session: { start: (input: SessionStartInput) => Promise<unknown> } }) {
  await $.session.start(SESSION)
  for (let i = 0; i < 200; i++) await Promise.resolve()
}

const ran = (runs: string[][], ...args: string[]) => runs.some(r => args.every((a, i) => r[i] === a))

describe('status panel', () => {
  test('STATUS-07: the start registers /beacon', async ($, on) => {
    const world = worldOf(on)
    await $.session.start(SESSION)
    expect(world.commands).toEqual(['beacon'])
  })

  test('STATUS-06: the band draws the session and its status lines, with no setting to turn on', async ($, on) => {
    const world = worldOf(on)
    await started($)
    const drawn = textOf(await $.ui.render(BAND))
    expect(drawn).toContain('acme')
    expect(drawn).toContain('back after standup')
    expect(drawn).toContain('fix-widget')
    expect(drawn).toContain('↑2')
    expect(drawn).toContain('!7 Fix the widget')
    expect(world.runs.filter(r => r[0] === 'status-panel').length).toBeGreaterThan(0)
    expect(ran(world.runs, 'statusline')).toBe(false)
    expect(ran(world.runs, 'config')).toBe(false)
  })

  test('STATUS-06: the branch links to its tree, and the web button opens the project page', async ($, on) => {
    const world = worldOf(on)
    await started($)
    expect(hrefsOf(await $.ui.render(BAND))).toEqual(['https://github.com/acme/acme/tree/fix-widget', 'https://example.com/acme/pull/7'])
    const ui = await $.ui.mount({ ...BAND, plugin: 'beacon' })
    await ui.press({ key: 'web' })
    expect(ran(world.runs, 'open-url', '/src/acme/packages/widget')).toBe(true)
  })

  test('STATUS-06: a CR link keeps the status line\'s bold and color', async ($, on) => {
    worldOf(on)
    await started($)
    const drawn = await $.ui.render(BAND)
    expect(propsOf(drawn, '!7')).toMatchObject({ bold: true, color: '#f8f8f2' })
    expect(propsOf(drawn, ' Fix the widget')).toMatchObject({ dimColor: true, color: '#f8f8f2' })
  })

  test('FOCUS-08: /beacon switch lists the other sessions in the band, and a pick raises one', async ($, on) => {
    const world = worldOf(on)
    await started($)
    const { text } = await $.command.run(commandOf('switch'))
    expect(text).toContain('pick a session')
    const ui = await $.ui.mount({ ...BAND, plugin: 'beacon' })
    expect((await ui.find({ key: 'pk-bbbbbbbbbbbbbbbb' }))?.text).toContain('other: docs (needs you)')
    await ui.press({ key: 'pk-bbbbbbbbbbbbbbbb' })
    expect(ran(world.runs, 'focus', 'bbbbbbbbbbbbbbbb')).toBe(true)
    expect(textOf(await $.ui.render(BAND))).not.toContain('other: docs')
  })

  test('STATUS-06: the band reads no other session', async ($, on) => {
    const world = worldOf(on)
    await started($)
    await $.ui.render(BAND)
    expect(ran(world.runs, 'wip')).toBe(false)
    expect(ran(world.runs, 'pick')).toBe(false)
  })

  test('STATUS-06: the code button opens the session\'s directory in the editor', async ($, on) => {
    const world = worldOf(on)
    await started($)
    const ui = await $.ui.mount({ ...BAND, plugin: 'beacon' })
    expect((await ui.find({ key: 'code' }))?.text).toContain('code ↗')
    expect((await ui.find({ key: 'web' }))?.text).toContain('↖ github')
    await ui.press({ key: 'code' })
    expect(ran(world.runs, 'open-code', '/src/acme/packages/widget')).toBe(true)
    expect(world.toasts).toEqual([])
  })

  test('STATUS-06: a session with no state yet draws nothing, rather than saying so', async ($, on) => {
    const empty = JSON.stringify({ project: null, task: null, mode: null, color_state: null, anchor_cwd: null, branch: null, branch_sync: '', branch_slot: null, branch_url: null })
    worldOf(on, { head: empty, statusline: '' })
    await started($)
    expect(textOf(await $.ui.render(BAND))).toBe('')
  })

  test('STATUS-06: the web and code buttons wait for the session\'s directory', async ($, on) => {
    worldOf(on, { head: JSON.stringify({ ...JSON.parse(HEAD), anchor_cwd: null }) })
    await started($)
    const ui = await $.ui.mount({ ...BAND, plugin: 'beacon' })
    expect(await ui.find({ key: 'code' })).toBeUndefined()
    expect(await ui.find({ key: 'web' })).toBeUndefined()
    expect(textOf(await $.ui.render(BAND))).toContain('acme')
  })

  test('the paused mode draws the panel as a slab of its hue, with its note', async ($, on) => {
    worldOf(on, { head: PAUSED, statusline: '' })
    await started($)
    const drawn = await $.ui.render(BAND)
    const text = textOf(drawn)
    expect(text).toContain('⏸ paused')
    expect(text).toContain('waiting for the VPN')
    expect(text).not.toContain('type to resume')
    expect(propsOf(drawn, '⏸ paused')).toMatchObject({ backgroundColor: '#44385f', bold: true })
    expect(propsOf(drawn, 'VPN')).toMatchObject({ italic: true })
    // The ribbon carries the glyph, so the head row doesn't repeat it.
    expect(text.split('⏸').length).toBe(2)
    // The head row sits on the same slab, not on the terminal's ground between two bars.
    expect(propsOf(drawn, 'acme')).toMatchObject({ backgroundColor: '#44385f', bold: true })
    expect(propsOf(drawn, ' ↖ github ')).toMatchObject({ color: '#8be9fd', backgroundColor: '#665c7c' })
    // The task is the headline, in the names' color rather than the note's hint.
    expect(propsOf(drawn, 'widgets')).toMatchObject({ color: '#f8f8f2' })
  })

  test('the slab opens and closes on whole rows of its background, never half-block glyphs', async ($, on) => {
    worldOf(on, { head: PAUSED, statusline: '' })
    await started($)
    const drawn = await $.ui.render(BAND)
    // A glyph edge draws narrower than a background cell fills, so the ground shows at the slab's corners.
    expect(textOf(drawn)).not.toMatch(/[▄▀]/)
    expect(slabOf(drawn)).toMatchObject({ backgroundColor: '#44385f', paddingX: 1, paddingY: 1 })
  })

  test('the mode sits in the gutter under the project, and its note and the status lines start under the branch', async ($, on) => {
    worldOf(on, { head: PAUSED })
    await started($)
    const drawn = await $.ui.render(BAND)
    const text = textOf(drawn)
    // The head row comes first and carries the buttons; the mode's label hangs under it.
    expect(text.indexOf('acme')).toBeLessThan(text.indexOf('⏸ paused'))
    expect(text.indexOf('code ↗')).toBeLessThan(text.indexOf('⏸ paused'))
    expect(text).toContain('⏸ pausedwaiting for the VPN')
    // `⏸ paused` is 8 cells, so `acme`'s column widens to it: the head row, the mode's row, the status line's.
    expect(gutterOf(drawn)).toEqual([8, 8, 8])
  })

  test('a mode with no note shares its gutter row with the first status line', async ($, on) => {
    worldOf(on, { head: PAUSED_NO_NOTE })
    await started($)
    const drawn = await $.ui.render(BAND)
    expect(textOf(drawn)).toContain('⏸ paused⏸ back after standup')
    expect(gutterOf(drawn)).toEqual([8, 8])
  })

  test('the dev cycle draws no slab, and a button is a chip that inverts whole under the pointer', async ($, on) => {
    worldOf(on)
    await started($)
    const drawn = await $.ui.render(BAND)
    expect(propsOf(drawn, 'acme')?.backgroundColor).toBeUndefined()
    expect(slabOf(drawn)).toBeUndefined()
    expect(gutterOf(drawn)).toEqual([4, 4])
    expect(propsOf(drawn, ' ↖ github ')).toMatchObject({ color: '#8be9fd', backgroundColor: '#343746' })
    // No hover of its own: the terminal's inversion of the plain button is the whole effect.
    expect(hoverOf(drawn, ' ↖ github ')).toBeUndefined()
  })

  test('STATUS-04: a held review takes the slab\'s hue, its label in the gutter above the mode\'s, with its target', async ($, on) => {
    const reviewing = JSON.stringify({
      ...JSON.parse(PAUSED),
      review: { glyph: '👀', label: 'in review', band: '#4a3a22', target: 'https://example.com/acme/pull/7', href: 'https://example.com/acme/pull/7' },
    })
    worldOf(on, { head: reviewing, statusline: '' })
    await started($)
    const drawn = await $.ui.render(BAND)
    const text = textOf(drawn)
    expect(text.indexOf('👀 in review')).toBeLessThan(text.indexOf('⏸ paused'))
    expect(propsOf(drawn, '👀 in review')).toMatchObject({ backgroundColor: '#4a3a22', bold: true })
    expect(propsOf(drawn, 'acme')).toMatchObject({ backgroundColor: '#4a3a22' })
    expect(hrefsOf(drawn)).toContain('https://example.com/acme/pull/7')
  })

  test('a status line keeps its separators and a title\'s leading space whole, so only the titles truncate', async ($, on) => {
    const link = (url: string, label: string) => `${ESC}]8;;${url}${ESC}\\${label}${ESC}]8;;${ESC}\\`
    const twoRefs = `${link('https://example.com/a/pull/1', 'a!1')}${ESC}[2;37m Fix the widget${ESC}[0m · ${link('https://example.com/b/pull/2', 'b!2')}${ESC}[2;37m Ship the gadget${ESC}[0m\n`
    worldOf(on, { statusline: twoRefs })
    await started($)
    const drawn = await $.ui.render(BAND)
    expect(propsOf(drawn, ' · ')?.wrap).toBeUndefined()
    expect(propsOf(drawn, ' ')?.wrap).toBeUndefined()
    expect(propsOf(drawn, 'Fix the widget')).toMatchObject({ wrap: 'truncate-end' })
  })

  test('a mode with no band keeps its glyph on the head row and draws no ribbon', async ($, on) => {
    const retro = JSON.stringify({ ...JSON.parse(HEAD), mode: { name: 'retro', note: null, glyph: '📋', label: 'retro', band: null, note_line: null } })
    worldOf(on, { head: retro })
    await started($)
    const drawn = await $.ui.render(BAND)
    expect(textOf(drawn).startsWith('📋')).toBe(true)
    // The glyph leads the head row, so the gutter under it spans the glyph's 2 cells, a gap, and `acme`.
    expect(gutterOf(drawn)).toEqual([4, 8])
  })

  test('the declared mode joins Claude Code\'s footer of modes', async ($, on) => {
    worldOf(on, { head: PAUSED, statusline: '' })
    const footer = footerOf(on)
    await started($)
    await $.ui.render(FOOTER)
    expect(footer.modes).toEqual(['memory paused', 'paused'])
  })

  test('the dev cycle leaves the footer of modes as it is', async ($, on) => {
    worldOf(on)
    const footer = footerOf(on)
    await started($)
    await $.ui.render(FOOTER)
    expect(footer.modes).toEqual(['memory paused'])
  })

  test('STATUS-07: /beacon refuses anything but switch', async ($, on) => {
    worldOf(on)
    await $.session.start(SESSION)
    const { text } = await $.command.run(commandOf('on'))
    expect(text).toContain('usage: /beacon [switch]')
  })
})
