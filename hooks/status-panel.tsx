import type { EngineInterface, Register } from 'claude-code'

/** STATUS-07: `/beacon switch` opens the session switcher in the band. */
export const COMMAND = 'beacon'
// COLOR_PALETTE in scripts/beacon, for the switcher's list. The panel takes the palette directly, as the badge and sessions view do.
const HUE: Record<string, string> = { idle: '#8b8fa0', working: '#ffb86c', blocked: '#ff5555' }
// The branch's color by its sync state (#20): the default branch recedes, a feature branch reads by how it sits against its upstream.
const BRANCH_HUE: Record<string, string> = { default: '#8d98c4', clean: '#8be9fd', diverged: '#f1fa8c', untracked: '#ffb86c' }
// THEME-03's action hues: one for the project page, one for the editor.
const WEB_HUE = '#8be9fd'
const CODE_HUE = '#ff79c6'
// The arrows the iTerm2 status bar's `↖ web` and `↗ code` carried, each on its button's outer side, so the pair bookends the row's end.
const WEB_GLYPH = '↖'
const CODE_GLYPH = '↗'
// The ribbon's text over a mode's `band` hue, which MODE_SPECS keeps dark so one light foreground reads on every mode.
const RIBBON_TEXT = '#f8f8f2'
const RIBBON_HINT = '#bfbfd0'

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
  /** STATE-04: the next prompt leaves this mode, so the ribbon says how to. */
  resumes_on_prompt: boolean
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

// FOCUS-08: the switcher's list, opened in the band. It reads the other sessions only when asked, so the band stays this session's otherwise.
async function openPicker($: EngineInterface): Promise<string> {
  const r = await beacon($, ['switch', '--list'], { timeoutMs: 20_000 })
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

    // The mode's pane cue, drawn in the band so any terminal shows it: a bar in the mode's hue carrying its glyph, label and note.
    // A row of hue above and below the text makes it read as a bar rather than a highlighted line.
    const mode = head?.mode
    const band = mode?.band
    const ribbon = !mode || !band ? [] : [
      <Box key="ribbon" flexDirection="row" justifyContent="space-between" gap={2} paddingX={1} paddingY={1} backgroundColor={band}>
        <Box flexDirection="row" flexShrink={1}>
          <Text backgroundColor={band} color={RIBBON_TEXT} bold>{`${mode.glyph} ${mode.label}`}</Text>
          {mode.note_line ? [
            <Text key="rb-sep" backgroundColor={band} color={RIBBON_HINT}>{' · '}</Text>,
            ...segmentsOf(mode.note_line).flatMap((s, i) => 'href' in s ? [] : [
              <Text key={`rb-${i}`} backgroundColor={band} color={RIBBON_TEXT} bold={s.style.bold} italic={s.style.italic} wrap="truncate-end">{s.text}</Text>,
            ]),
          ] : []}
        </Box>
        {mode.resumes_on_prompt ? [<Text key="rb-hint" backgroundColor={band} color={RIBBON_HINT} italic>type to resume</Text>] : []}
      </Box>,
    ]

    // The ahead/behind glyphs first, in the branch's color; linked only when it has an upstream to open.
    const branchOf = (p: string) => {
      const text = <Text key="branch" color={BRANCH_HUE[head?.branch_slot ?? ''] ?? undefined} wrap="truncate-end">{head?.branch_sync ? `${head.branch_sync} ${p}` : p}</Text>
      const href = links.get(p) ?? head?.branch_url
      return href ? <Link key="branch" href={href}>{text}</Link> : text
    }

    return (
      <Box flexDirection="column" paddingRight={5} marginTop={1}>
        {ribbon}
        <Box flexDirection="row" justifyContent="space-between" gap={2}>
          <Box flexDirection="row" gap={1} flexShrink={1}>
            {head?.mode?.glyph && !band ? [<Text key="glyph">{head.mode.glyph}</Text>] : []}
            {parts.flatMap((p, i) => [
                ...(i === 0 ? [] : [<Text key={`sep-${i}`} dimColor>·</Text>]),
                // No activity here: the band only ever shows the session in front of you, whose spinner and prompts already say it.
                i === 0
                  ? <Text key="p-0" bold wrap="truncate-end">{p}</Text>
                  : p === head?.branch
                    ? branchOf(p)
                    : links.has(p)
                      ? <Link key={`p-${i}`} href={links.get(p)!} label={p} />
                      : <Text key={`p-${i}`} wrap="truncate-end">{p}</Text>,
              ])}
          </Box>
          {/* Only once the anchor is known: before it, a press could only answer that there is no directory. */}
          {head?.anchor_cwd ? [
            <Box key="actions" flexDirection="row" gap={1} flexShrink={0}>
              {/* Labeled by what they open: the forge and the editor, each with its status bar arrow on the outer side. */}
              {head.forge ? [<Button key="web" hotkey="w" label={`${WEB_GLYPH} ${head.forge}`} onPress={() => void openWith($, 'open-url')}><Text color={WEB_HUE}>{`${WEB_GLYPH} ${head.forge}`}</Text></Button>] : []}
              <Button key="code" hotkey="c" label={`${head.code_label} ${CODE_GLYPH}`} onPress={() => void openWith($, 'open-code')}><Text color={CODE_HUE}>{`${head.code_label} ${CODE_GLYPH}`}</Text></Button>
            </Box>,
          ] : []}
        </Box>
        {rest.map((segs, i) => (
          <Box key={`sl-${i}`} flexDirection="row" paddingLeft={2}>
            {segs.map((s, j) =>
              'href' in s
                ? <Link key={`sl-${i}-${j}`} href={s.href}>{s.runs.map((r, k) => <Text key={`sl-${i}-${j}-${k}`} {...styleOf(r.style)}>{r.text}</Text>)}</Link>
                : <Text key={`sl-${i}-${j}`} {...styleOf(s.style)} wrap="truncate-end">{s.text}</Text>,
            )}
          </Box>
        ))}
        {pickerRows}
        {lastError === '' ? [] : [<Text key="err" color="#ff5555" wrap="truncate-end">{lastError}</Text>]}
      </Box>
    )
  })
}
