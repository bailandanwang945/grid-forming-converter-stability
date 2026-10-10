import type { ACLine, NetworkTopology } from './api'

export type LineOperationResult = { ok: true; topology: NetworkTopology; line: ACLine } | { ok: false; message: string }

export function validateLineEndpoints(topology: NetworkTopology, fromBusId: string, toBusId: string): { ok: true } | { ok: false; message: string } {
  const from = topology.buses.find(bus => bus.id === fromBusId)
  const to = topology.buses.find(bus => bus.id === toBusId)
  if (!from || !to) return { ok: false, message: '接线未完成：首末端必须是当前网络中存在的母线。' }
  if (from.id === to.id) return { ok: false, message: `线路首末端不能为同一母线（${from.id}）；请选择另一条母线。` }
  if (![from.nominal_voltage_v, to.nominal_voltage_v].every(value => Number.isFinite(value) && value > 0)) {
    return { ok: false, message: '接线未完成：请先为两端母线填写有效的正标称电压。' }
  }
  if (Math.abs(from.nominal_voltage_v - to.nominal_voltage_v) / Math.max(from.nominal_voltage_v, to.nominal_voltage_v) > 1e-9) {
    return { ok: false, message: `不能直接连接 ${from.id} 与 ${to.id}：电压等级不同，普通线路不能代替变压器。` }
  }
  return { ok: true }
}

function nextLineId(topology: NetworkTopology) {
  const occupied = new Set([
    ...topology.buses.map(item => item.id), ...topology.lines.map(item => item.id),
    ...topology.grid_forming_converters.map(item => item.id), ...topology.infinite_buses.map(item => item.id),
    ...topology.loads.map(item => item.id),
  ])
  let index = 1
  while (occupied.has(`line-${index}`)) index += 1
  return `line-${index}`
}

export function createNetworkLine(topology: NetworkTopology, fromBusId: string, toBusId: string): LineOperationResult {
  const checked = validateLineEndpoints(topology, fromBusId, toBusId)
  if (!checked.ok) return checked
  const id = nextLineId(topology)
  const line: ACLine = { id, name: `线路 ${id.split('-').pop()}`, from_bus_id: fromBusId, to_bus_id: toBusId,
    resistance_pu: 0.01, reactance_pu: 0.2, shunt_susceptance_pu: 0, in_service: true }
  const next = JSON.parse(JSON.stringify(topology)) as NetworkTopology
  next.lines.push(line)
  return { ok: true, topology: next, line }
}

/** A refused or unfinished reconnection never removes or changes the original line. */
export function reconnectNetworkLine(topology: NetworkTopology, lineId: string, fromBusId: string, toBusId: string): LineOperationResult {
  const checked = validateLineEndpoints(topology, fromBusId, toBusId)
  if (!checked.ok) return checked
  if (!topology.lines.some(line => line.id === lineId)) return { ok: false, message: `线路 ${lineId} 已不存在，未修改接线。` }
  const next = JSON.parse(JSON.stringify(topology)) as NetworkTopology
  const line = next.lines.find(item => item.id === lineId)!
  line.from_bus_id = fromBusId
  line.to_bus_id = toBusId
  return { ok: true, topology: next, line }
}
