import type { NetworkTopology } from './api'

/** Drawing-level equipotential constraints, not AC lines with an impedance. */
export type IdealConnection = {
  id: string
  name: string
  from_bus_id: string
  to_bus_id: string
}

export type IdealConnectionOperationResult =
  | { ok: true; connection: IdealConnection; connections: IdealConnection[]; message: string }
  | { ok: false; message: string }

export type IdealConnectionCompileResult =
  | { ok: true; topology: NetworkTopology; busMap: Record<string, string>; groups: string[][] }
  | { ok: false; issues: string[] }

function topologyIds(topology: NetworkTopology): Set<string> {
  return new Set([
    ...topology.buses, ...topology.lines, ...topology.grid_forming_converters,
    ...topology.infinite_buses, ...topology.loads,
  ].map(item => item.id))
}

function endpointIssue(topology: NetworkTopology, from: string, to: string): string | null {
  const first = topology.buses.find(bus => bus.id === from)
  const second = topology.buses.find(bus => bus.id === to)
  if (!first || !second) return `普通导线端点不存在：${!first ? from || '未选起点' : to || '未选终点'}；两端必须是当前网络中的母线。`
  if (from === to) return `普通导线不能连接同一母线（${from}），请选择另一母线。`
  if (![first.nominal_voltage_v, second.nominal_voltage_v].every(value => Number.isFinite(value) && value > 0)) {
    return `普通导线 ${from} — ${to} 的两端必须具有有效的正标称电压。`
  }
  if (first.nominal_voltage_v !== second.nominal_voltage_v) {
    return `普通导线不能直接连接 ${from} 与 ${to}：电压等级不同，导线不能代替变压器。`
  }
  return null
}

function pairKey(from: string, to: string): string {
  return JSON.stringify(from < to ? [from, to] : [to, from])
}

/** Strict import validation; analysis-model limitations are checked at compilation only. */
export function parseIdealConnections(value: unknown, topology: NetworkTopology): IdealConnection[] {
  if (!Array.isArray(value)) throw new Error('普通导线数据必须是数组。')
  const occupied = topologyIds(topology)
  const pairs = new Set<string>()
  const fields = ['id', 'name', 'from_bus_id', 'to_bus_id'] as const
  return value.map((item: unknown, index) => {
    const label = `第 ${index + 1} 条普通导线`
    if (item === null || typeof item !== 'object' || Array.isArray(item)) throw new Error(`${label}必须是对象。`)
    const record = item as Record<string, unknown>
    const unknownFields = Object.keys(record).filter(key => !fields.includes(key as typeof fields[number]))
    if (unknownFields.length) throw new Error(`${label}包含不支持的字段：${unknownFields.join('、')}；普通导线不具有 R/X 参数。`)
    for (const field of fields) {
      if (typeof record[field] !== 'string' || !(record[field] as string).trim()) throw new Error(`${label}的 ${field} 必须是非空字符串。`)
    }
    const connection: IdealConnection = {
      id: record.id as string, name: record.name as string,
      from_bus_id: record.from_bus_id as string, to_bus_id: record.to_bus_id as string,
    }
    if (occupied.has(connection.id)) throw new Error(`普通导线 ID 重复或与拓扑设备冲突：${connection.id}。`)
    const issue = endpointIssue(topology, connection.from_bus_id, connection.to_bus_id)
    if (issue) throw new Error(`普通导线 ${connection.id}：${issue}`)
    const pair = pairKey(connection.from_bus_id, connection.to_bus_id)
    if (pairs.has(pair)) throw new Error(`普通导线 ${connection.id} 重复连接 ${connection.from_bus_id} 与 ${connection.to_bus_id}；反向连接也视为重复。`)
    occupied.add(connection.id)
    pairs.add(pair)
    return connection
  })
}

export function createIdealConnection(
  topology: NetworkTopology, connections: IdealConnection[], from: string, to: string,
): IdealConnectionOperationResult {
  const issue = endpointIssue(topology, from, to)
  if (issue) return { ok: false, message: issue }
  let checked: IdealConnection[]
  try {
    checked = parseIdealConnections(connections, topology)
  } catch (error) {
    return { ok: false, message: error instanceof Error ? error.message : '现有普通导线数据无效。' }
  }
  if (checked.some(item => pairKey(item.from_bus_id, item.to_bus_id) === pairKey(from, to))) {
    return { ok: false, message: `普通导线已连接 ${from} 与 ${to}，无需重复或反向连接。` }
  }
  const occupied = topologyIds(topology)
  checked.forEach(item => occupied.add(item.id))
  let index = 1
  while (occupied.has(`wire-${index}`)) index += 1
  const connection: IdealConnection = { id: `wire-${index}`, name: `普通导线 ${index}`, from_bus_id: from, to_bus_id: to }
  return {
    ok: true, connection, connections: [...checked, connection],
    message: `已连接 ${from} 与 ${to}；普通导线无 R/X，分析时按等电位节点合并。`,
  }
}

export function removeIdealConnection(connections: IdealConnection[], id: string): IdealConnection[] {
  return connections.some(item => item.id === id) ? connections.filter(item => item.id !== id) : connections
}

/** Compile equipotential groups to the existing NetworkTopology/1.0 API contract. */
export function compileIdealConnections(
  topology: NetworkTopology, connections: IdealConnection[],
): IdealConnectionCompileResult {
  let checked: IdealConnection[]
  try {
    checked = parseIdealConnections(connections, topology)
  } catch (error) {
    return { ok: false, issues: [error instanceof Error ? error.message : '普通导线数据无效。'] }
  }
  const identityMap = Object.fromEntries(topology.buses.map(bus => [bus.id, bus.id]))
  if (!checked.length) return { ok: true, topology, busMap: identityMap, groups: topology.buses.map(bus => [bus.id]) }
  if (new Set(topology.buses.map(bus => bus.id)).size !== topology.buses.length) {
    return { ok: false, issues: ['母线 ID 重复，无法可靠编译普通导线等电位约束。'] }
  }
  const parent = new Map(topology.buses.map(bus => [bus.id, bus.id]))
  const find = (id: string): string => {
    let root = id
    while (parent.get(root) !== root) root = parent.get(root)!
    let current = id
    while (current !== root) {
      const next = parent.get(current)!
      parent.set(current, root)
      current = next
    }
    return root
  }
  for (const wire of checked) parent.set(find(wire.to_bus_id), find(wire.from_bus_id))
  const grouped = new Map<string, string[]>()
  for (const bus of topology.buses) {
    const root = find(bus.id)
    const group = grouped.get(root) ?? []
    group.push(bus.id)
    grouped.set(root, group)
  }
  const groups = [...grouped.values()]
  const busMap: Record<string, string> = Object.fromEntries(groups.flatMap(group => {
    const representative = group.includes(topology.reference_bus_id) ? topology.reference_bus_id : group[0]
    return group.map(id => [id, representative])
  }))
  const issues: string[] = []
  const mapped = (id: string, label: string): string | undefined => {
    const value = Object.prototype.hasOwnProperty.call(busMap, id) ? busMap[id] : undefined
    if (value === undefined) issues.push(`${label}引用不存在的母线 ${id}，未修改或删除任何设备。`)
    return value
  }
  mapped(topology.reference_bus_id, '参考母线')
  for (const line of topology.lines) {
    const from = mapped(line.from_bus_id, `线路 ${line.id} 的首端`)
    const to = mapped(line.to_bus_id, `线路 ${line.id} 的末端`)
    if (from !== undefined && from === to) {
      issues.push(`普通导线将线路 ${line.id}（${line.name}，${line.in_service === false ? '停运' : '投运'}）的两端合并为母线 ${from}，形成线路自环；当前模型不支持，不能自动删除或将 R/X 置零。`)
    }
  }
  const sources = new Map<string, { gfms: string[]; grids: string[] }>()
  for (const [devices, kind] of [[topology.grid_forming_converters, 'gfms'], [topology.infinite_buses, 'grids']] as const) {
    for (const device of devices) {
      const bus = mapped(device.bus_id, `电源 ${device.id}`)
      if (bus === undefined) continue
      const group = sources.get(bus) ?? { gfms: [], grids: [] }
      group[kind].push(device.id)
      sources.set(bus, group)
    }
  }
  for (const load of topology.loads) mapped(load.bus_id, `负荷 ${load.id}`)
  for (const [bus, source] of sources) {
    if (source.gfms.length > 1) issues.push(`母线 ${bus} 汇集多个 GFM（${source.gfms.join('、')}）；物理接线已保留，但当前分析模型不支持多个 GFM 共节点，未自动丢弃电源。`)
    if (source.grids.length > 1) issues.push(`母线 ${bus} 汇集多个理想电网（${source.grids.join('、')}），存在理想电压源冲突；当前模型不支持，未自动丢弃电源。`)
    if (source.gfms.length && source.grids.length) issues.push(`母线 ${bus} 上 GFM（${source.gfms.join('、')}）与理想电网（${source.grids.join('、')}）共节点；当前模型不支持该电源连接，未自动丢弃电源。`)
  }
  if (issues.length) return { ok: false, issues }
  const compiled = structuredClone(topology)
  compiled.buses = compiled.buses.filter(bus => busMap[bus.id] === bus.id)
  compiled.reference_bus_id = busMap[compiled.reference_bus_id]
  compiled.lines = compiled.lines.map(line => ({ ...line, from_bus_id: busMap[line.from_bus_id], to_bus_id: busMap[line.to_bus_id] }))
  compiled.grid_forming_converters = compiled.grid_forming_converters.map(device => ({ ...device, bus_id: busMap[device.bus_id] }))
  compiled.infinite_buses = compiled.infinite_buses.map(device => ({ ...device, bus_id: busMap[device.bus_id] }))
  compiled.loads = compiled.loads.map(device => ({ ...device, bus_id: busMap[device.bus_id] }))
  return { ok: true, topology: compiled, busMap, groups }
}
