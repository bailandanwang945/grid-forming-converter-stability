// Pure shortcut validation: no browser, build, network or numerical analysis.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'

const require = createRequire(new URL('../apps/web/package.json', import.meta.url))
const ts = require('typescript')
const source = await readFile(new URL('../apps/web/src/networkEditorShortcuts.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext },
  reportDiagnostics: true,
})
assert.deepEqual((compiled.diagnostics ?? []).filter(item => item.category === ts.DiagnosticCategory.Error), [])
const { DEFAULT_NETWORK_SHORTCUTS: defaults, NETWORK_SHORTCUT_LABELS: labels,
  LOCAL_STORAGE_KEY, validateNetworkShortcuts: validate, parseStoredNetworkShortcuts: parse } =
  await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString('base64')}`)

let scenarios = 0
function test(name, run) {
  run()
  scenarios += 1
  console.log(`PASS ${name}`)
}
const copy = () => ({ ...defaults })
const stored = bindings => JSON.stringify({ schema_version: '1.0', bindings })
function rejected(input) {
  const result = validate(input)
  assert.equal(result.ok, false)
  assert.equal(typeof result.message, 'string')
  assert.ok(result.message.length > 0)
  assert.equal('shortcuts' in result, false)
}

test('defaults, labels and storage key expose all seven actions', () => {
  assert.deepEqual(defaults, { select: 'V', connect: 'C', pan: 'H', bus: 'B', gfm: 'G', grid: 'E', fit: 'F' })
  assert.deepEqual(Object.keys(labels).sort(), Object.keys(defaults).sort())
  assert.ok(Object.values(labels).every(value => typeof value === 'string' && /[\u4e00-\u9fff]/.test(value)))
  assert.equal(LOCAL_STORAGE_KEY, 'gfm-network-editor-shortcuts/1.0')
  assert.ok(Object.isFrozen(defaults))
})
test('case normalizes without changing a frozen input', () => {
  const input = Object.freeze({ select: 'v', connect: 'C', pan: 'h', bus: 'B', gfm: 'g', grid: 'e', fit: 'f' })
  const before = structuredClone(input)
  const result = validate(input)
  assert.equal(result.ok, true)
  assert.deepEqual(result.shortcuts, defaults)
  assert.notEqual(result.shortcuts, input)
  assert.deepEqual(input, before)
})
test('alternate unique ASCII letters are accepted', () => {
  const input = { select: 'a', connect: 'S', pan: 'd', bus: 'Q', gfm: 'w', grid: 'R', fit: 't' }
  assert.deepEqual(validate(input), { ok: true,
    shortcuts: { select: 'A', connect: 'S', pan: 'D', bus: 'Q', gfm: 'W', grid: 'R', fit: 'T' } })
})
test('non-record configurations are rejected', () => {
  for (const value of [null, undefined, true, 1, 'V', [], new Date(), new Map()]) rejected(value)
})
test('nonletters, whitespace, multicharacter and nonstring keys are rejected', () => {
  for (const key of ['', ' ', ' v ', 'VV', '1', '-', '中', 'é', 'Ｖ', '😀', '\n', null, undefined, 1, true, [], {}]) {
    const input = { ...copy(), select: key }
    const before = structuredClone(input)
    rejected(input)
    assert.deepEqual(input, before)
  }
})
test('duplicates are rejected case-insensitively without mutation', () => {
  for (const key of ['V', 'v']) {
    const input = { ...copy(), connect: key }
    const before = structuredClone(input)
    const result = validate(input)
    assert.equal(result.ok, false)
    assert.match(result.message, /选择|接线/)
    assert.deepEqual(input, before)
  }
})
test('every missing action is rejected; inherited actions do not count', () => {
  for (const action of Object.keys(defaults)) {
    const input = copy()
    delete input[action]
    rejected(input)
    rejected(Object.assign(Object.create({ [action]: defaults[action] }), input))
  }
})
test('extra string, nonenumerable and symbol fields are strictly rejected', () => {
  rejected({ ...copy(), extra: 'Z' })
  const hiddenExtra = copy()
  Object.defineProperty(hiddenExtra, 'extra', { value: 'Z', enumerable: false })
  rejected(hiddenExtra)
  rejected({ ...copy(), [Symbol('extra')]: 'Z' })
})
test('accessor bindings are rejected without executing their getters', () => {
  const input = copy()
  let calls = 0
  Object.defineProperty(input, 'select', { get() { calls += 1; return 'V' }, enumerable: true })
  rejected(input)
  assert.equal(calls, 0)
})
test('valid v1.0 storage normalizes lowercase bindings', () => {
  const lower = Object.fromEntries(Object.entries(defaults).map(([action, key]) => [action, key.toLowerCase()]))
  assert.deepEqual(parse(stored(lower)), defaults)
})
test('empty, malformed JSON and wrong JSON types restore defaults', () => {
  for (const raw of [null, '', ' ', '{', 'not-json', 'null', '[]', '"V"', 'true', '1']) {
    assert.deepEqual(parse(raw), defaults)
  }
})
test('wrong or missing schema version restores defaults', () => {
  for (const version of [undefined, null, 1, '1', '1.1', '2.0']) {
    assert.deepEqual(parse(JSON.stringify({ schema_version: version, bindings: { ...copy(), select: 'A' } })), defaults)
  }
})
test('invalid bindings and extra envelope fields restore defaults', () => {
  assert.deepEqual(parse(stored({ ...copy(), connect: 'V' })), defaults)
  assert.deepEqual(parse(stored({ select: 'V' })), defaults)
  assert.deepEqual(parse(JSON.stringify({ schema_version: '1.0' })), defaults)
  assert.deepEqual(parse(JSON.stringify({ schema_version: '1.0', bindings: { ...copy(), select: 'A' }, extra: true })), defaults)
  assert.deepEqual(parse(JSON.stringify(copy())), defaults)
})
test('default fallbacks and parsed success are independent mutable copies', () => {
  const first = parse(null), second = parse('{'), valid = parse(stored(defaults))
  assert.notEqual(first, second)
  assert.notEqual(first, defaults)
  assert.notEqual(valid, defaults)
  first.select = 'A'
  valid.connect = 'Z'
  assert.deepEqual(second, defaults)
  assert.equal(defaults.select, 'V')
  assert.equal(defaults.connect, 'C')
  assert.deepEqual(parse(null), defaults)
  assert.deepEqual(parse(stored(defaults)), defaults)
})
console.log(`GFM_NETWORK_EDITOR_SHORTCUTS_OK (${scenarios} pure scenarios)`)
