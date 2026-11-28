import type { EngineInterface, Register } from 'claude-code'

/** STATUS-07: `/beacon switch` opens the session switcher in the band. */
export const COMMAND = 'beacon'
// COLOR_PALETTE in scripts/beacon, for the band's list of sessions. The panel takes the palette directly, as the badge and sessions view do.
const HUE: Record<string, string> = { idle: '#8b8fa0', working: '#ffb86c', blocked: '#ff5555' }
// The branch's color by its sync state (#20): the default branch recedes, a feature branch reads by how it sits against its upstream.
const BRANCH_HUE: Record<string, string> = { default: '#8d98c4', clean: '#8be9fd', diverged: '#f1fa8c', untracked: '#ffb86c' }
// THEME-03's action hues: one for the project page, one for the editor.
const WEB_HUE = '#8be9fd'
const CODE_HUE = '#ff79c6'
// The arrows the iTerm2 status bar's `↖ web` and `↗ code` carried, each on its button's outer side, so the pair bookends the row's end.
const WEB_GLYPH = '↖'
const CODE_GLYPH = '↗'
// The slab's text over a mode's `band` hue, which MODE_SPECS keeps dark so one light foreground reads on every mode; the hint color carries the note, a step below the names and the task.
const RIBBON_TEXT = '#f8f8f2'
const RIBBON_HINT = '#bfbfd0'
// A button's chip with no mode: a step above the terminal's ground, so the label reads as a control at rest.
const CHIP_GROUND = '#343746'

// A button's chip on the slab: the band lifted toward white, so it stays one family with the mode's hue.
function lift(hex: string, by = 0.18): string {
  const n = parseInt(hex.slice(1), 16)
  const ch = (shift: number) => {
    const v = (n >> shift) & 0xff
    return Math.round(v + (255 - v) * by).toString(16).padStart(2, '0')
  }
  return `#${ch(16)}${ch(8)}${ch(0)}`
}

// Terminal cells a short label takes, so the mode's label and the project can share a column: an emoji past U+1F000 (💤 🚀 🏁) takes two, a variation selector none.
function cells(text: string): number {
  let n = 0
  for (const ch of text) {
    const cp = ch.codePointAt(0)!
    n += cp === 0xfe0f ? 0 : cp >= 0x1f000 ? 2 : 1
  }
  return n
}

// What changes without an event in this session (a push from a shell, a forge read landing) shows within this.
const POLL_MS = 15_000
const TIMEOUT_MS = 5_000

type Mode = {
  name: string
  note: string | null
  glyph: string
  /** The word Claude Code's footer of modes shows (`paused`). */
  label: string
  /** The ribbon's hue; null for a mode that marks itself by its glyph alone. */
  band: string | null
  /** The note with its emphasis as SGR, for the ribbon. */
  note_line: string | null
} | null
type Head = {
  project: string | null
  task: string | null
  branch: string | null
  mode: Mode
  color_state: string | null
  anchor_cwd: string | null
  /** The ahead/behind glyphs (`↑2↓1`), empty when in step or untracked. */
  branch_sync: string
  branch_slot: 'default' | 'clean' | 'diverged' | 'untracked' | null
  branch_url: string | null
  /** The project page's host by name (`github`), the web button's label; null with no remote. */
  forge: string | null
  /** The editor the code button runs, by its program's name (`code`). */
  code_label: string
  /** STATUS-04: a held review, drawn as the slab's first row; null with none. */
  review?: { glyph: string; label: string; band: string; target: string; href: string | null } | null
  /** STATUS-01's lines, with their SGR and OSC-8 sequences. */
  lines: string[]
}
type Style = { bold?: boolean; dim?: boolean; italic?: boolean; strike?: boolean; color?: string }
type Run = { text: string; style: Style }
type Segment = Run | { href: string; label: string; runs: Run[] }

let head: Head | null = null
let statusLines: Segment[][] = []
let lastError = ''
// FOCUS-08: the other sessions `/beacon switch` lists, or null while no picker is open.
let picker: { hash: string; label: string; color_state: string | null }[] | null = null
let collapsed = false

// An SGR, or an OSC 8 opening (a URL) or closing (empty) a link.
const TOKEN = /\x1b\[([0-9;]*)m|\x1b\]8;;([^\x07\x1b]*)(?:\x07|\x1b\\)/g
// The SGR colors the status line uses, as the Dracula hexes the rest of the band draws in.
const ANSI: Record<string, string> = {
  '31': '#ff5555', '32': '#50fa7b', '33': '#f1fa8c', '34': '#bd93f9',
  '35': '#ff79c6', '36': '#8be9fd', '37': '#f8f8f2', '90': '#6272a4',
}

// xterm's 256-color cube and gray ramp, for the roles the status line sets past the 16 ANSI colors (THEME-04).
function xterm256(n: number): string | undefined {
  if (n < 16 || n > 255) return undefined
  const hex = (v: number) => v.toString(16).padStart(2, '0')
  if (n >= 232) {
    const v = 8 + 10 * (n - 232)
    return `#${hex(v)}${hex(v)}${hex(v)}`
  }
  const step = [0, 95, 135, 175, 215, 255]
  const i = n - 16
  return `#${hex(step[Math.floor(i / 36)]!)}${hex(step[Math.floor(i / 6) % 6]!)}${hex(step[i % 6]!)}`
}

function withSgr(style: Style, params: string): Style {
  let next = { ...style }
  const codes = (params === '' ? '0' : params).split(';')
  for (let i = 0; i < codes.length; i++) {
    const code = codes[i]!
    if (code === '0') next = {}
    else if (code === '1') next.bold = true
    else if (code === '2') next.dim = true
    else if (code === '22') next.bold = next.dim = false
    else if (code === '3') next.italic = true
    else if (code === '23') next.italic = false
    else if (code === '9') next.strike = true
    else if (code === '29') next.strike = false
    else if (code === '39') delete next.color
    else if (code === '38' && codes[i + 1] === '5') {
      const color = xterm256(Number(codes[i + 2]))
      if (color) next.color = color
      i += 2
    } else if (ANSI[code]) next.color = ANSI[code]
  }
  return next
}

// The status line's own styling carries through: its roles (a CR bold, an issue dim, a delivery struck green) are the contract, not ours to restate.
function segmentsOf(line: string): Segment[] {
  const out: Segment[] = []
  let style: Style = {}
  let link: { href: string; runs: Run[] } | null = null
  let at = 0
  const emit = (text: string) => {
    if (text === '') return
    const run = { text, style: { ...style } }
    if (link) link.runs.push(run)
    else out.push(run)
  }
  const close = () => {
    if (link) out.push({ href: link.href, label: link.runs.map(r => r.text).join(''), runs: link.runs })
    link = null
  }
  for (const m of line.matchAll(TOKEN)) {
    emit(line.slice(at, m.index))
    at = m.index! + m[0].length
    if (m[1] !== undefined) style = withSgr(style, m[1])
    else if (m[2]) link = { href: m[2], runs: [] }
    else close()
  }
  emit(line.slice(at))
  close()
  return out
}

// Unstyled text stays dim, as the band drew all of it before: the styled roles are what should stand out.
const styleOf = (s: Style) => ({
  bold: s.bold,
  italic: s.italic,
  dimColor: s.dim || (!s.bold && !s.color && !s.strike),
  strikethrough: s.strike,
  color: s.color,
})

// The whole hook env, so beacon keys on the session its hooks key on (the pane's ITERM_SESSION_ID, or CLAUDE_CODE_SESSION_ID).
async function beacon($: EngineInterface, args: string[], options: { stdin?: string; timeoutMs?: number } = {}) {
  const env = await $.process.hookEnv()
  return $.process.run(['python3', `${env.CLAUDE_PLUGIN_ROOT}/scripts/beacon`, ...args], {
    env,
    stdin: options.stdin,
    timeoutMs: options.timeoutMs ?? TIMEOUT_MS,
  })
}

// STATUS-06: the head row and the status lines under it, from one process. Read while collapsed too: the footer's mode label still shows.
async function refresh($: EngineInterface): Promise<void> {
  try {
    const row = await beacon($, ['status-panel'])
    head = row.exitCode === 0 && row.stdout.trim() !== '' ? (JSON.parse(row.stdout) as Head) : null
    statusLines = (head?.lines ?? []).map(segmentsOf)
    lastError = ''
    $.ui.invalidate('ui.render')
  } catch (err) {
    lastError = String(err)
  }
}

// `open-code` / `open-url` resolve the command beacon-side, since a hooks module's process has no login PATH.
async function openWith($: EngineInterface, verb: 'open-code' | 'open-url'): Promise<void> {
  const dir = head?.anchor_cwd
  if (!dir) {
    $.ui.toast('beacon: no working directory resolved for this session.', { timeoutMs: 4000 })
    return
  }
  const r = await beacon($, [verb, dir], { timeoutMs: 25_000 })
  if (r.exitCode !== 0) $.ui.toast(`beacon: ${(r.stderr || r.stdout).trim()}`, { timeoutMs: 4000 })
}

// Uncollapsed, the band catches up at once rather than at the next poll.
function setCollapsed($: EngineInterface, value: boolean): void {
  if (value === collapsed) return
  collapsed = value
  if (!collapsed) void refresh($)
}

// FOCUS-08: the other sessions in `beacon pick`'s order, opened in the band. It reads them only when asked, so the band stays this session's otherwise.
async function openPicker($: EngineInterface): Promise<string> {
  const r = await beacon($, ['pick', '--json'], { timeoutMs: 20_000 })
  if (r.exitCode !== 0) return `beacon: ${(r.stderr || r.stdout).trim()}`
  const sessions = JSON.parse(r.stdout) as NonNullable<typeof picker>
  if (sessions.length === 0) return 'beacon: no other beacon session to switch to.'
  picker = sessions.slice(0, 9)
  $.ui.invalidate('ui.render')
  return 'beacon: pick a session above the prompt (ctrl+x tab, then its number).'
}

async function pick($: EngineInterface, hash: string): Promise<void> {
  picker = null
  $.ui.invalidate('ui.render')
  const r = await beacon($, ['focus', hash], { timeoutMs: 10_000 })
  if (r.exitCode !== 0) $.ui.toast(`beacon: ${(r.stderr || r.stdout).trim()}`, { timeoutMs: 4000 })
}

export const register: Register = on => {
  head = null
  statusLines = []
  collapsed = false

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: COMMAND,
      description: 'Switch to another beacon session',
      argumentHint: 'switch',
      immediate: true,
    })
    const r = await next(e)
    void refresh($)
    $.clock.every(POLL_MS, () => void refresh($))
    return r
  })
  on('turn.start', async ($, e, next) => {
    const r = await next(e)
    void refresh($)
    return r
  })
  on('turn.complete', async ($, e, next) => {
    const r = await next(e)
    void refresh($)
    return r
  })
  on('command.run', { command: COMMAND }, async ($, e) => {
    const text = ['', 'switch'].includes(e.args.trim().toLowerCase())
      ? await openPicker($).catch((err: unknown) => `beacon: ${String(err)}`)
      : 'usage: /beacon [switch]'
    return { text, isTextDisplayOnly: true }
  })

  // The declared mode beside Claude Code's own (`memory paused`), so it reads with the band collapsed.
  on('ui.render', { component: 'SessionMode' }, ($, e, next) => {
    const label = head?.mode?.label
    if (!label || e.props.modes.includes(label)) return next(e)
    return next({ ...e, props: { ...e.props, modes: [...e.props.modes, label] } })
  })

  on('ui.render', { component: 'AbovePrompt' }, ($, e, next) => {
    setCollapsed($, e.props.isCollapsed)
    if (e.props.hasSurvey) return next(e)
    const { Box, Text, Button, Link } = $.ui.resolve(e)

    const pickerRows = !picker ? [] : [
      <Box key="picker" flexDirection="column" paddingLeft={2} marginTop={1}>
        {picker.map((s, i) => (
          <Box key={`pk-${s.hash}`} flexDirection="row" gap={1}>
            <Text color={HUE[s.color_state ?? 'idle'] ?? HUE.idle}>■</Text>
            <Button key={`pk-${s.hash}`} hotkey={String(i + 1)} plain label={s.label} onPress={() => void pick($, s.hash)}>{s.label}</Button>
          </Box>
        ))}
        <Button key="pk-close" hotkey="x" plain label="close" onPress={() => { picker = null; $.ui.invalidate('ui.render') }}>close</Button>
      </Box>,
    ]
    // A task derived from the branch, and a link labeled with it, all name one thing: say it once, as the link.
    const links = new Map<string, string>()
    for (const segs of statusLines) for (const s of segs) if ('href' in s && !links.has(s.label)) links.set(s.label, s.href)
    const parts = [...new Set([head?.project, head?.branch, head?.task].filter((p): p is string => !!p))]
    const used = new Set(parts.filter(p => links.has(p)))
    const rest = statusLines
      .map(segs => segs.filter(s => !('href' in s && used.has(s.label))))
      .filter(segs => segs.some(s => 'href' in s || s.text.replace(/[\s·]/g, '') !== ''))
    // A session that has written no state yet (its first hook still running) draws nothing, rather than saying so.
    if (parts.length === 0 && rest.length === 0) return pickerRows.length ? <Box flexDirection="column">{pickerRows}</Box> : next(e)

    // STATUS-09: a declared mode turns the whole panel into one slab of its hue, so any terminal shows the mode as a surface rather than a line.
    // Every Text on it names the hue too: one drawn without it shows the terminal's ground through the slab.
    // STATUS-04: a held review's label sits above the mode's, as its glyph leads the tab, and the slab takes its hue.
    const mode = head?.mode
    const review = head?.review ?? null
    const band = review?.band ?? mode?.band ?? undefined
    // The task is the session's headline, so on the slab it takes the names' color and the default branch recedes behind it.
    const taskColor = band ? RIBBON_TEXT : undefined
    const labels = [review ? `${review.glyph} ${review.label}` : null, mode?.band ? `${mode.glyph} ${mode.label}` : null].filter((l): l is string => !!l)
    // One gutter column holds the project and, under it, the review's and mode's labels, so the branch, a note, and every status line start together.
    const column = Math.max(cells(parts[0] ?? ''), ...labels.map(cells))
    // A mode with no band of its own (retro) keeps its glyph ahead of the project, so the gutter starts past it.
    const headGlyph = mode?.glyph && !mode.band ? mode.glyph : null
    const gutter = (headGlyph ? cells(headGlyph) + 2 : 0) + column
    // The slab's top and bottom edges are whole rows of its background, not half-block glyphs (▄ ▀): a terminal draws a glyph a few
    // pixels narrower than it fills a background cell, so glyph edges leave the ground showing at the slab's corners.

    // The ahead/behind glyphs first, in the branch's color; linked only when it has an upstream to open.
    // It never shrinks: squeezed, a branch wraps mid-name onto a second row. The task beside it truncates instead.
    const branchOf = (p: string) => {
      const text = <Text backgroundColor={band} color={BRANCH_HUE[head?.branch_slot ?? ''] ?? undefined}>{head?.branch_sync ? `${head.branch_sync} ${p}` : p}</Text>
      const href = links.get(p) ?? head?.branch_url
      return <Box key="branch" flexShrink={0}>{href ? <Link href={href}>{text}</Link> : text}</Box>
    }

    // Plain, so the terminal draws no brackets of its own: the chip is the whole control, and under the pointer it inverts as one block in the button's hue.
    // The label carries a cell of padding each side, so the inverted block doesn't hug the text.
    const chip = band ? lift(band) : CHIP_GROUND
    // No hotkey: one answers only once ctrl+x tab has moved the focus into the band, and a plain button prints it as `w:` outside the chip.
    const button = (key: string, text: string, color: string, verb: 'open-url' | 'open-code') => (
      <Button key={key} plain label={text} onPress={() => void openWith($, verb)}>
        <Text color={color} backgroundColor={chip}>{` ${text} `}</Text>
      </Button>
    )

    // Only once the anchor is known: before it, a press could only answer that there is no directory.
    // Docked at the end of the head row, the panel's top right, so they hold one place whatever the slab carries under it.
    const actions = !head?.anchor_cwd ? [] : [
      <Box key="actions" flexDirection="row" gap={2} flexShrink={0}>
        {/* Labeled by what they open: the forge and the editor, each with its status bar arrow on the outer side. */}
        {head.forge ? [button('web', `${WEB_GLYPH} ${head.forge}`, WEB_HUE, 'open-url')] : []}
        {button('code', `${head.code_label} ${CODE_GLYPH}`, CODE_HUE, 'open-code')}
      </Box>,
    ]

    // What sits right of the gutter, row by row: the review's target, the mode's note, then the status lines.
    // Each label pairs with the row at its index, so a label with nothing of its own to say shares its row with the next status line.
    const lineOf = (segs: Segment[], i: number) => segs.flatMap((s, j) => {
      const key = `sl-${i}-${j}`
      // A ref (`!45`) never shrinks: squeezed, it wraps mid-token onto a second row. The titles beside it truncate instead.
      if ('href' in s) return [<Box key={key} flexShrink={0}><Link href={s.href}>{s.runs.map((r, k) => <Text key={`${key}-${k}`} {...styleOf(r.style)} backgroundColor={band} wrap="truncate-end">{r.text}</Text>)}</Link></Box>]
      // Nor does the spacing around one: a ` · ` or a title's leading space squeezed to nothing runs one ref into the next title.
      const fixed = (k: string, text: string) => <Box key={k} flexShrink={0}><Text {...styleOf(s.style)} backgroundColor={band}>{text}</Text></Box>
      if (!/[\p{L}\p{N}]/u.test(s.text)) return [fixed(key, s.text)]
      const [, before = '', body = '', after = ''] = /^(\s*)([\s\S]*?)(\s*)$/.exec(s.text) ?? []
      return [
        ...(before ? [fixed(`${key}-b`, before)] : []),
        <Text key={key} {...styleOf(s.style)} backgroundColor={band} wrap="truncate-end">{body}</Text>,
        ...(after ? [fixed(`${key}-a`, after)] : []),
      ]
    })
    const contents = [
      // The target is the question the review answers (which changeset, which CR), so it wraps rather than truncating.
      ...(review ? [[<Text key="rv-t" backgroundColor={band} color={RIBBON_HINT}>{review.href ? <Link href={review.href}>{review.target}</Link> : review.target}</Text>]] : []),
      ...(mode?.band && mode.note_line ? [segmentsOf(mode.note_line).flatMap((s, i) => 'href' in s ? [] : [
        <Text key={`rb-${i}`} backgroundColor={band} color={s.style.bold ? RIBBON_TEXT : RIBBON_HINT} bold={s.style.bold} italic={s.style.italic} wrap="truncate-end">{s.text}</Text>,
      ])] : []),
      ...rest.map(lineOf),
    ]
    const hung = Array.from({ length: Math.max(labels.length, contents.length) }, (_, i) => (
      <Box key={`g-${i}`} flexDirection="row" gap={2}>
        <Box width={gutter} flexShrink={0}>{labels[i] ? [<Text key="label" backgroundColor={band} color={RIBBON_TEXT} bold>{labels[i]}</Text>] : []}</Box>
        <Box flexDirection="row" flexShrink={1}>{contents[i] ?? []}</Box>
      </Box>
    ))

    return (
      <Box flexDirection="column" paddingRight={5} marginTop={1}>
        <Box flexDirection="column" backgroundColor={band} paddingX={band ? 1 : 0} paddingY={band ? 1 : 0}>
          <Box flexDirection="row" justifyContent="space-between" gap={2}>
            <Box flexDirection="row" gap={2} flexShrink={1}>
              {headGlyph ? [<Text key="glyph" backgroundColor={band}>{headGlyph}</Text>] : []}
              {parts.map((p, i) =>
                // No activity here: the band only ever shows the session in front of you, whose spinner and prompts already say it.
                i === 0
                  ? <Box key="p-0" width={column} flexShrink={0}><Text backgroundColor={band} bold>{p}</Text></Box>
                  : p === head?.branch
                    ? branchOf(p)
                    : links.has(p)
                      ? <Link key={`p-${i}`} href={links.get(p)!}><Text backgroundColor={band} color={taskColor} wrap="truncate-end">{p}</Text></Link>
                      : <Text key={`p-${i}`} backgroundColor={band} color={taskColor} wrap="truncate-end">{p}</Text>,
              )}
            </Box>
            {actions}
          </Box>
          {hung}
        </Box>
        {pickerRows}
        {lastError === '' ? [] : [<Text key="err" color="#ff5555" wrap="truncate-end">{lastError}</Text>]}
      </Box>
    )
  })
}
