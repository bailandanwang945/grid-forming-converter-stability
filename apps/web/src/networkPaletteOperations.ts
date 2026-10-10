import type { Bus, GridFormingConverter, InfiniteBus, NetworkTopology } from './api'

export type CanvasElementKind = 'bus' | 'gfm' | 'grid'
export type CanvasPosition = { x: number; y: number }
export type CanvasNodeId = `${CanvasElementKind}:${string}`
export type CanvasPositions = Record<CanvasNodeId, CanvasPosition>

export type CanvasInsertionResult =
  | { ok: true; topology: NetworkTopology; positions: CanvasPositions; selectedElement: CanvasNodeId; message: string }
  | { ok: false; message: string }

export type CanvasRemovalResult =
  | { ok: true; topology: NetworkTopology; removedNodeIds: CanvasNodeId[]; message: string }
  | { ok: false; message: string }

function occupiedIds(topology: NetworkTopology) {
  return new Set([
    ...topology.buses.map(item => item.id),
    ...topology.lines.map(item => item.id),
    ...topology.grid_forming_converters.map(item => item.id),
    ...topology.infinite_buses.map(item => item.id),
    ...topology.loads.map(item => item.id),
  ])
}

function nextId(prefix: CanvasElementKind, occupied: Set<string>) {
  let index = 1
  while (occupied.has(`${prefix}-${index}`)) index += 1
  const id = `${prefix}-${index}`
  occupied.add(id)
  return id
}

function finitePosition(position: CanvasPosition) {
  return position != null && Number.isFinite(position.x) && Number.isFinite(position.y)
}

function busVoltage(topology: NetworkTopology) {
  return topology.buses.find(bus => bus.id === topology.reference_bus_id)?.nominal_voltage_v
    ?? topology.base_values.voltage_v
}

function newBus(topology: NetworkTopology, id: string): Bus {
  return { id, name: `母线 ${id.split('-').pop()}`, nominal_voltage_v: busVoltage(topology) }
}

/** Position is an already-snapped top-left canvas coordinate, not a symbol centre. */
export function insertCanvasElement(
  topology: NetworkTopology,
  kind: CanvasElementKind,
  position: CanvasPosition,
  targetBusId?: string,
): CanvasInsertionResult {
  if (!['bus', 'gfm', 'grid'].includes(kind)) return { ok: false, message: '无法放置：不支持的元件类型。' }
  if (!finitePosition(position)) return { ok: false, message: '无法放置：画布坐标必须是有限数值。' }

  const createsBus = kind === 'bus' || targetBusId === undefined
  if (createsBus && !(Number.isFinite(busVoltage(topology)) && busVoltage(topology) > 0)) {
    return { ok: false, message: '无法放置：请先填写有效的参考母线标称电压或基准电压。' }
  }
  if (kind === 'gfm' && !(Number.isFinite(topology.base_values.apparent_power_va) && topology.base_values.apparent_power_va > 0)) {
    return { ok: false, message: '无法放置 VSM：基准视在功率必须是有效的正数。' }
  }
  if (kind !== 'bus' && targetBusId !== undefined) {
    if (!topology.buses.some(bus => bus.id === targetBusId)) {
      return { ok: false, message: `无法放置：接入母线 ${targetBusId || '（未指定）'} 已不存在。` }
    }
    if (topology.grid_forming_converters.some(gfm => gfm.bus_id === targetBusId)
      || topology.infinite_buses.some(grid => grid.bus_id === targetBusId)) {
      return { ok: false, message: `无法放置：母线 ${targetBusId} 已接入 VSM 或无限大母线；当前低频模型一个母线端口只能接入一个电源。` }
    }
  }

  const occupied = occupiedIds(topology)
  const next = structuredClone(topology)
  const positions: CanvasPositions = {}
  if (kind === 'bus') {
    const id = nextId('bus', occupied)
    const bus = newBus(topology, id)
    next.buses.push(bus)
    const selectedElement: CanvasNodeId = `bus:${id}`
    positions[selectedElement] = { ...position }
    return { ok: true, topology: next, positions, selectedElement,
      message: `已放置 ${bus.name}；未自动添加线路，请用接线工具连接母线。` }
  }

  const id = nextId(kind, occupied)
  let busId = targetBusId
  if (busId === undefined) {
    busId = nextId('bus', occupied)
    const busPosition = { x: position.x - 24, y: position.y + (kind === 'gfm' ? 144 : -132) }
    if (!finitePosition(busPosition)) return { ok: false, message: '无法放置：新接入母线的坐标超出有限数值范围。' }
    next.buses.push(newBus(topology, busId))
    positions[`bus:${busId}`] = busPosition
  }
  let name: string
  if (kind === 'gfm') {
    const gfm: GridFormingConverter = {
      id, name: `VSM ${id.split('-').pop()}`, bus_id: busId,
      rated_apparent_power_va: topology.base_values.apparent_power_va,
      control_mode: 'virtual_synchronous_machine',
      active_power_setpoint_pu: 0, reactive_power_setpoint_pu: 0, voltage_setpoint_pu: 1,
      virtual_inertia_s: 2, damping_coefficient_pu: 60,
      active_power_measurement_time_constant_s: 0.1,
    }
    next.grid_forming_converters.push(gfm)
    name = gfm.name
  } else {
    const grid: InfiniteBus = {
      id, name: `无限大母线 ${id.split('-').pop()}`, bus_id: busId,
      voltage_magnitude_pu: 1, voltage_angle_deg: 0,
    }
    if (next.infinite_buses.length === 0) next.reference_bus_id = busId
    next.infinite_buses.push(grid)
    name = grid.name
  }
  const selectedElement: CanvasNodeId = `${kind}:${id}`
  positions[selectedElement] = { ...position }
  const attachment = targetBusId === undefined
    ? `并新增接入母线 ${busId}；未自动添加线路，请用接线工具连接母线。`
    : `，接入母线 ${busId}。`
  const defaults = kind === 'gfm' ? ' VSM 参数为示例初值，请核对实际参数。' : ' 电压初值为 1 p.u.、相角初值为 0°，请核对实际参数。'
  return { ok: true, topology: next, positions, selectedElement, message: `已放置 ${name}${attachment}${defaults}` }
}

/** Caller confirms bus cascade deletion before committing topology/layout together. */
export function removeCanvasElement(topology: NetworkTopology, selection: string | null): CanvasRemovalResult {
  if (!selection) return { ok: false, message: '请先选择要删除的元件。' }
  const separator = selection.indexOf(':')
  const kind = selection.slice(0, separator)
  const id = selection.slice(separator + 1)
  if (separator < 1 || !id || !['bus', 'gfm', 'grid', 'line'].includes(kind)) {
    return { ok: false, message: '无法删除：所选元件类型无效。' }
  }
  const entity = kind === 'bus' ? topology.buses.find(item => item.id === id)
    : kind === 'gfm' ? topology.grid_forming_converters.find(item => item.id === id)
      : kind === 'grid' ? topology.infinite_buses.find(item => item.id === id)
        : topology.lines.find(item => item.id === id)
  if (!entity) return { ok: false, message: `无法删除：元件 ${id} 已不存在。` }
  if (kind === 'bus' && topology.buses.length <= 2) return { ok: false, message: '当前网络至少需要保留两条母线。' }
  if (kind === 'grid' && topology.infinite_buses.length <= 1) {
    return { ok: false, message: '当前低频模型至少需要保留一个无限大母线。' }
  }
  if (kind === 'bus' && topology.infinite_buses.length > 0
    && topology.infinite_buses.every(grid => grid.bus_id === id)) {
    return { ok: false, message: '当前低频模型至少需要保留一个无限大母线；请先新增或迁移无限大母线。' }
  }

  const next = structuredClone(topology)
  const removedNodeIds: CanvasNodeId[] = []
  if (kind === 'line') {
    next.lines = next.lines.filter(line => line.id !== id)
  } else if (kind === 'gfm') {
    next.grid_forming_converters = next.grid_forming_converters.filter(gfm => gfm.id !== id)
    removedNodeIds.push(`gfm:${id}`)
  } else if (kind === 'grid') {
    const removedBusId = next.infinite_buses.find(grid => grid.id === id)!.bus_id
    next.infinite_buses = next.infinite_buses.filter(grid => grid.id !== id)
    removedNodeIds.push(`grid:${id}`)
    if (next.reference_bus_id === removedBusId) next.reference_bus_id = next.infinite_buses[0]?.bus_id ?? next.buses[0].id
  } else {
    removedNodeIds.push(`bus:${id}`,
      ...next.grid_forming_converters.filter(gfm => gfm.bus_id === id).map(gfm => `gfm:${gfm.id}` as CanvasNodeId),
      ...next.infinite_buses.filter(grid => grid.bus_id === id).map(grid => `grid:${grid.id}` as CanvasNodeId))
    next.buses = next.buses.filter(bus => bus.id !== id)
    next.lines = next.lines.filter(line => line.from_bus_id !== id && line.to_bus_id !== id)
    next.grid_forming_converters = next.grid_forming_converters.filter(gfm => gfm.bus_id !== id)
    next.infinite_buses = next.infinite_buses.filter(grid => grid.bus_id !== id)
    next.loads = next.loads.filter(load => load.bus_id !== id)
    if (next.reference_bus_id === id) next.reference_bus_id = next.infinite_buses[0]?.bus_id ?? next.buses[0].id
  }
  return { ok: true, topology: next, removedNodeIds,
    message: `已删除 ${entity.name}${kind === 'bus' ? '及其关联线路、设备和负荷' : ''}。` }
}
