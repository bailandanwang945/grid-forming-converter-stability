// Report-source binding only; never call a solver or fabricate a stability result.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
const require = createRequire(new URL('../apps/web/package.json', import.meta.url))
const ts = require('typescript')
const source = await readFile(new URL('../apps/web/src/networkConnectionReport.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: {
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext,
}, reportDiagnostics: true })
assert.deepEqual((compiled.diagnostics ?? []).filter(item => item.category === ts.DiagnosticCategory.Error), [])
const { appendConnectionInputBinding } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString('base64')}`)
const binding = {
  sourceTopologyId: 'raw-1', sourceTopologyName: '<script>bad</script> $&',
  originalBusIds: ['a', 'b', 'c'], idealConnections: [{ id: 'wire-1', name: '<img onerror="bad">', from_bus_id: 'a', to_bus_id: 'c' }],
  busMap: { a: 'a', b: 'b', c: 'a' },
}
const html = '<!doctype html><html><body class="report"><main>ORIGINAL ANALYSIS</main></body></html>'
assert.strictEqual(appendConnectionInputBinding(html, null), html)
assert.strictEqual(appendConnectionInputBinding(html, { ...binding, idealConnections: [] }), html)
const original = structuredClone(binding)
const result = appendConnectionInputBinding(html, binding)
assert.deepEqual(binding, original)
assert.ok(result.includes('<body class="report"><section'))
assert.ok(result.includes('<main>ORIGINAL ANALYSIS</main>'))
assert.ok(result.includes('<td>c</td><td>a</td>'))
assert.ok(result.includes('&lt;script&gt;bad&lt;/script&gt; $&'))
assert.ok(!result.includes('<img onerror='))
assert.ok(result.includes('理想等电位连接'))
assert.ok(appendConnectionInputBinding('<main>FRAGMENT</main>', binding).endsWith('<main>FRAGMENT</main>'))
console.log('GFM_NETWORK_CONNECTION_REPORT_OK (source mapping, original report retention, no mutation, HTML escaping)')
