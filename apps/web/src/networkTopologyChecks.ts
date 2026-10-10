import type { NetworkTopology } from './api'

export type TopologySummary = {
  componentCount: number
  cycleRank: number
  isolatedBusIds: string[]
  invalidLineIds: string[]
  wiringValid: boolean
  wiringIssues: string[]
  lowFrequencyApplicable: boolean
  lowFrequencyIssues: string[]
}

/** Connection checks do not infer energization or applicability of a controller model.
 * This is an early UI check; the backend still validates its full input contract.
 */
export function summarizeTopology(topology: NetworkTopology): TopologySummary {
  const busesById = new Map(topology.buses.map(bus => [bus.id, bus]))
  const entityIds = [
    ...topology.buses.map(item => item.id), ...topology.lines.map(item => item.id),
    ...topology.grid_forming_converters.map(item => item.id), ...topology.infinite_buses.map(item => item.id),
    ...topology.loads.map(item => item.id),
  ]
  const wiringIssues: string[] = []
  if (!topology.buses.length) wiringIssues.push('接线至少需要一条母线。')
  if (new Set(entityIds).size !== entityIds.length) wiringIssues.push('设备与母线编号存在重复，请使用唯一编号。')
  const invalidLineIds: string[] = []
  for (const line of topology.lines) {
    const from = busesById.get(line.from_bus_id)
    const to = busesById.get(line.to_bus_id)
    let issue = ''
    if (!from || !to) issue = '引用了不存在的母线'
    else if (from.id === to.id) issue = '首末端是同一母线'
    else if (Math.abs(from.nominal_voltage_v - to.nominal_voltage_v)
      / Math.max(from.nominal_voltage_v, to.nominal_voltage_v) > 1e-9) {
      issue = '连接了不同电压等级；不能以线路代替变压器'
    }
    if (issue) {
      invalidLineIds.push(line.id)
      wiringIssues.push(`线路 ${line.id} ${issue}。`)
    }
  }
  for (const device of [...topology.grid_forming_converters, ...topology.infinite_buses, ...topology.loads]) {
    if (!busesById.has(device.bus_id)) wiringIssues.push(`设备 ${device.id} 引用了不存在的母线 ${device.bus_id}。`)
  }
  const adjacency = new Map(topology.buses.map(bus => [bus.id, new Set<string>()]))
  for (const line of topology.lines) {
    if (line.in_service === false || invalidLineIds.includes(line.id)) continue
    adjacency.get(line.from_bus_id)?.add(line.to_bus_id)
    adjacency.get(line.to_bus_id)?.add(line.from_bus_id)
  }
  const visited = new Set<string>()
  let componentCount = 0
  for (const bus of topology.buses) {
    if (visited.has(bus.id)) continue
    componentCount += 1
    const pending = [bus.id]
    while (pending.length) {
      const current = pending.pop() as string
      if (visited.has(current)) continue
      visited.add(current)
      adjacency.get(current)?.forEach(neighbor => {
        if (!visited.has(neighbor)) pending.push(neighbor)
      })
    }
  }
  const isolatedBusIds = topology.buses.filter(bus => (adjacency.get(bus.id)?.size ?? 0) === 0).map(bus => bus.id)
  const validLineCount = topology.lines.filter(line => line.in_service !== false && !invalidLineIds.includes(line.id)).length
  const cycleRank = Math.max(0, validLineCount - busesById.size + componentCount)
  const wiringValid = wiringIssues.length === 0
  const lowFrequencyIssues: string[] = []
  if (!wiringValid) lowFrequencyIssues.push('请先修正接线关系中的问题。')
  if (componentCount !== 1) lowFrequencyIssues.push(`当前有 ${componentCount} 个连通分量；低频模型要求所分析网络连通。`)
  if (!topology.grid_forming_converters.length) lowFrequencyIssues.push('缺少构网型变流器；当前低频模型不能分析无变流器的网络。')
  const unsupported = topology.grid_forming_converters.filter(item => item.control_mode !== 'virtual_synchronous_machine')
  if (unsupported.length) lowFrequencyIssues.push(`当前低频模型仅支持 VSM 控制；不支持的设备：${unsupported.map(item => item.id).join('、')}。`)
  const gfmBusIds = topology.grid_forming_converters.map(item => item.bus_id)
  if (new Set(gfmBusIds).size !== gfmBusIds.length) lowFrequencyIssues.push('当前低频模型不支持多个构网型变流器接入同一母线。')
  const idealSourceBusIds = new Set(topology.infinite_buses.map(item => item.bus_id))
  if (gfmBusIds.some(id => idealSourceBusIds.has(id))) lowFrequencyIssues.push('当前低频模型不支持构网型变流器与理想等值电源接入同一母线。')
  if (!topology.infinite_buses.length) {
    lowFrequencyIssues.push('缺少无限大母线；当前低频模型不支持纯孤岛系统。')
  } else {
    const referenceBusIds = topology.infinite_buses.map(item => item.bus_id)
    if (!referenceBusIds.includes(topology.reference_bus_id)) lowFrequencyIssues.push('相角参考母线须连接无限大母线。')
    if (new Set(referenceBusIds).size !== referenceBusIds.length) lowFrequencyIssues.push('同一母线不能并联多个理想等值电源。')
  }
  return { componentCount, cycleRank, isolatedBusIds, invalidLineIds, wiringValid, wiringIssues,
    lowFrequencyApplicable: lowFrequencyIssues.length === 0, lowFrequencyIssues }
}
