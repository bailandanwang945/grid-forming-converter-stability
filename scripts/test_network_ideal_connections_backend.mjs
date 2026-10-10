// Cross-language boundary regression; no HTTP service, browser or temporary data files.
// This verifies the existing reduced-order model for one fixture, not a new research method.
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('../', import.meta.url))
const require = createRequire(new URL('../apps/web/package.json', import.meta.url))
const ts = require('typescript')
const source = await readFile(new URL('../apps/web/src/networkIdealConnections.ts', import.meta.url), 'utf8')
const compiledSource = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext }, reportDiagnostics: true,
})
assert.deepEqual((compiledSource.diagnostics ?? []).filter(item => item.category === ts.DiagnosticCategory.Error), [])
const { compileIdealConnections } = await import(
  `data:text/javascript;base64,${Buffer.from(compiledSource.outputText).toString('base64')}`
)

const raw = {
  schema_version: '1.0', id: 'ideal-wire-backend-boundary', name: 'Three-bus drawing fixture',
  frame_convention_id: 'global-synchronous-angle-v1', reference_bus_id: 'bus-b',
  base_values: { apparent_power_va: 1e6, voltage_v: 690, frequency_hz: 50 },
  buses: ['bus-a', 'bus-b', 'bus-c'].map(id => ({ id, name: id, nominal_voltage_v: 690 })),
  lines: [
    { id: 'line-ab', name: 'A-B', from_bus_id: 'bus-a', to_bus_id: 'bus-b', resistance_pu: 0.02, reactance_pu: 0.2, in_service: true },
    { id: 'line-cb', name: 'C-B', from_bus_id: 'bus-c', to_bus_id: 'bus-b', resistance_pu: 0.03, reactance_pu: 0.3, in_service: true },
  ],
  grid_forming_converters: [{ id: 'gfm-a', name: 'VSM A', bus_id: 'bus-a',
    rated_apparent_power_va: 1e6, control_mode: 'virtual_synchronous_machine', virtual_inertia_s: 2,
    damping_coefficient_pu: 60, active_power_measurement_time_constant_s: 0.1 }],
  infinite_buses: [{ id: 'grid-b', name: 'Grid B', bus_id: 'bus-b', voltage_magnitude_pu: 1, voltage_angle_deg: 0 }],
  loads: [],
}
const wires = [{ id: 'wire-1', name: 'Ordinary ideal A-C wire', from_bus_id: 'bus-a', to_bus_id: 'bus-c' }]
const rawBefore = structuredClone(raw)
const wiresBefore = structuredClone(wires)
const result = compileIdealConnections(raw, wires)
assert.equal(result.ok, true)
assert.deepEqual(raw, rawBefore)
assert.deepEqual(wires, wiresBefore)
assert.deepEqual(result.busMap, { 'bus-a': 'bus-a', 'bus-b': 'bus-b', 'bus-c': 'bus-a' })

// Hand-built reference: the same two original impedances, now in parallel A-B.
// It is intentionally not constructed using the compiler's busMap or output lines.
const reference = {
  ...structuredClone(raw),
  buses: [
    { id: 'bus-a', name: 'bus-a', nominal_voltage_v: 690 },
    { id: 'bus-b', name: 'bus-b', nominal_voltage_v: 690 },
  ],
  lines: [
    { id: 'line-ab', name: 'A-B', from_bus_id: 'bus-a', to_bus_id: 'bus-b', resistance_pu: 0.02, reactance_pu: 0.2, in_service: true },
    { id: 'line-cb', name: 'C-B', from_bus_id: 'bus-a', to_bus_id: 'bus-b', resistance_pu: 0.03, reactance_pu: 0.3, in_service: true },
  ],
}
assert.deepEqual(result.topology, reference)
assert.equal(result.topology.lines.length, 2, 'Wires must not create an artificial X=0 or tiny-X branch')

function pythonExecutable() {
  const local = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts' : 'bin', process.platform === 'win32' ? 'python.exe' : 'python')
  if (existsSync(local)) return local
  if (process.platform === 'win32') {
    return execFileSync('powershell.exe', [
      '-NoProfile', '-NonInteractive', '-Command',
      '(Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source',
    ], { cwd: root, encoding: 'utf8', timeout: 10000, windowsHide: true }).trim()
  }
  return execFileSync('python3', ['-c', 'import sys; print(sys.executable)'], {
    cwd: root, encoding: 'utf8', timeout: 10000,
  }).trim()
}

const python = String.raw`
import json
import sys
import numpy as np
from backend.domain.network_models import NetworkTopology
from backend.core.reduced_order_model import build_reduced_order_model

payload = json.load(sys.stdin)
models = {
    key: build_reduced_order_model(NetworkTopology.model_validate(value))
    for key, value in payload.items()
}
actual = models['compiled']
expected = models['reference']
raw = models['raw']
assert actual.vsm_ids == expected.vsm_ids == ('gfm-a',)
assert actual.state_labels == expected.state_labels
np.testing.assert_allclose(actual.state_matrix, expected.state_matrix, rtol=1e-12, atol=1e-12)
np.testing.assert_allclose(actual.synchronous_stiffness_matrix, expected.synchronous_stiffness_matrix, rtol=1e-12, atol=1e-12)
np.testing.assert_allclose(actual.poles_per_s, expected.poles_per_s, rtol=1e-12, atol=1e-12)
np.testing.assert_allclose(actual.synchronous_stiffness_matrix, [[1 / 0.2 + 1 / 0.3]], rtol=1e-12, atol=1e-12)
np.testing.assert_allclose(raw.synchronous_stiffness_matrix, [[1 / 0.2]], rtol=1e-12, atol=1e-12)
assert not np.allclose(actual.state_matrix, raw.state_matrix), 'The regression must distinguish compiled and uncompiled models.'
print(json.dumps({
    'vsm_ids': actual.vsm_ids,
    'compiled_stiffness_pu': actual.synchronous_stiffness_matrix.tolist(),
    'raw_stiffness_pu': raw.synchronous_stiffness_matrix.tolist(),
    'max_state_matrix_error': float(np.max(np.abs(actual.state_matrix - expected.state_matrix))),
    'max_stiffness_error': float(np.max(np.abs(actual.synchronous_stiffness_matrix - expected.synchronous_stiffness_matrix))),
    'max_pole_error': float(np.max(np.abs(actual.poles_per_s - expected.poles_per_s))),
    'poles_per_s': [[float(p.real), float(p.imag)] for p in actual.poles_per_s],
}))
`

let output
try {
  output = execFileSync(pythonExecutable(), ['-c', python], {
    cwd: root, input: JSON.stringify({ raw, compiled: result.topology, reference }),
    encoding: 'utf8', timeout: 30000, maxBuffer: 128 * 1024, windowsHide: true,
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
  })
} catch (error) {
  if (/ModuleNotFoundError|No module named/.test(String(error.stderr ?? ''))) {
    console.error('BACKEND_DEPENDENCIES_UNAVAILABLE: existing Python lacks required packages; no installation or service mutation attempted.')
  }
  throw error
}
const summary = JSON.parse(output)
assert.deepEqual(summary.vsm_ids, ['gfm-a'])
assert.equal(summary.max_state_matrix_error, 0)
assert.equal(summary.max_stiffness_error, 0)
assert.equal(summary.max_pole_error, 0)
console.log(`PASS frontend compiled topology matches hand-built backend reference: ${JSON.stringify(summary)}`)
console.log('GFM_NETWORK_IDEAL_CONNECTIONS_BACKEND_OK (one finite fixture; formal domain/model, no service dependency or continuous-theorem claim)')
