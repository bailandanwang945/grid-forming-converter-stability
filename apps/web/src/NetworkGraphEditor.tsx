import { useMemo, useState } from 'react'
import {
  Background,
  ConnectionMode,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Activity, Network, Power, Zap } from 'lucide-react'
import type { ACLine, NetworkTopology } from './api'

export type DiagramPosition = { x: number; y: number }

export type DiagramLayout = {
  schema_version: 'gfm-network-diagram-layout/1.0'
  node_positions: Record<string, DiagramPosition>
}

export type TopologySummary = {
  componentCount: number
  cycleRank: number
  isolatedBusIds: string[]
  invalidLineIds: string[]
  ready: boolean
}

type GraphNodeData = {
  label: string
  subtitle: string
  kind: 'bus' | 'gfm' | 'grid'
}

type NetworkGraphEditorProps = {
  topology: NetworkTopology
  layout: DiagramLayout
  onLayoutChange: (layout: DiagramLayout) => void
  onLayoutCheckpoint: () => void
  onTopologyChange: (topology: NetworkTopology) => void
  onMessage: (message: string) => void
}

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value))
const busNodeId = (id: string) => `bus:${id}`
const gfmNodeId = (id: string) => `gfm:${id}`
const gridNodeId = (id: string) => `grid:${id}`

function entityId(nodeId: string, kind: string) {
  const prefix = `${kind}:`
  return nodeId.startsWith(prefix) ? nodeId.slice(prefix.length) : null
}

function fallbackPosition(kind: GraphNodeData['kind'], index: number, busIndex = index): DiagramPosition {
  if (kind === 'bus') return { x: 90 + (index % 4) * 230, y: 170 + Math.floor(index / 4) * 220 }
  if (kind === 'gfm') return { x: 90 + (busIndex % 4) * 230, y: 35 + Math.floor(busIndex / 4) * 220 }
  return { x: 90 + (busIndex % 4) * 230, y: 300 + Math.floor(busIndex / 4) * 220 }
}

function graphNode({ data, selected }: NodeProps<Node<GraphNodeData>>) {
  return <div className={`power-node ${data.kind} ${selected ? 'selected' : ''}`}>
    {data.kind === 'bus' && <>
      <Handle id="north" type="target" position={Position.Top}/>
      <Handle id="east" type="source" position={Position.Right}/>
      <Handle id="south" type="source" position={Position.Bottom}/>
      <Handle id="west" type="target" position={Position.Left}/>
    </>}
    {data.kind === 'gfm' && <Handle className="attachment-handle" type="source" position={Position.Bottom}/>}
    {data.kind === 'grid' && <Handle className="attachment-handle" type="source" position={Position.Top}/>}
    <span className="power-node-icon">
      {data.kind === 'bus' ? <Network size={16}/> : data.kind === 'gfm' ? <Activity size={16}/> : <Power size={16}/>}
    </span>
    <span><b>{data.label}</b><small>{data.subtitle}</small></span>
  </div>
}

export function emptyDiagramLayout(): DiagramLayout {
  return { schema_version: 'gfm-network-diagram-layout/1.0', node_positions: {} }
}

export function parseDiagramLayout(value: unknown): DiagramLayout {
  if (!value || typeof value !== 'object') throw new Error('案例缺少图形版面数据。')
  const candidate = value as { schema_version?: unknown; node_positions?: unknown }
  if (candidate.schema_version !== 'gfm-network-diagram-layout/1.0'
      || !candidate.node_positions || typeof candidate.node_positions !== 'object') {
    throw new Error('图形版面版本或节点坐标字段无效。')
  }
  const positions: Record<string, DiagramPosition> = {}
  Object.entries(candidate.node_positions).forEach(([id, position]) => {
    if (!position || typeof position !== 'object') throw new Error(`图元 ${id} 的坐标无效。`)
    const point = position as { x?: unknown; y?: unknown }
    if (typeof point.x !== 'number' || !Number.isFinite(point.x)
        || typeof point.y !== 'number' || !Number.isFinite(point.y)) {
      throw new Error(`图元 ${id} 的坐标必须是有限数值。`)
    }
    positions[id] = { x: point.x, y: point.y }
  })
  return { schema_version: 'gfm-network-diagram-layout/1.0', node_positions: positions }
}

export function summarizeTopology(topology: NetworkTopology): TopologySummary {
  const busIds = new Set(topology.buses.map(bus => bus.id))
  const entityIds = [
    ...topology.buses.map(item => item.id), ...topology.lines.map(item => item.id),
    ...topology.grid_forming_converters.map(item => item.id), ...topology.infinite_buses.map(item => item.id),
    ...topology.loads.map(item => item.id),
  ]
  const globallyUniqueIds = new Set(entityIds).size === entityIds.length
  const invalidLineIds = topology.lines
    .filter(line => line.from_bus_id === line.to_bus_id || !busIds.has(line.from_bus_id) || !busIds.has(line.to_bus_id))
    .map(line => line.id)
  const adjacency = new Map(topology.buses.map(bus => [bus.id, new Set<string>()]))
  topology.lines.forEach(line => {
    if (line.in_service === false || !busIds.has(line.from_bus_id) || !busIds.has(line.to_bus_id) || line.from_bus_id === line.to_bus_id) return
    adjacency.get(line.from_bus_id)?.add(line.to_bus_id)
    adjacency.get(line.to_bus_id)?.add(line.from_bus_id)
  })
  const visited = new Set<string>()
  let componentCount = 0
  topology.buses.forEach(bus => {
    if (visited.has(bus.id)) return
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
  })
  const isolatedBusIds = topology.buses.filter(bus => (adjacency.get(bus.id)?.size ?? 0) === 0).map(bus => bus.id)
  const validLineCount = topology.lines.filter(line => line.in_service !== false && !invalidLineIds.includes(line.id)).length
  const cycleRank = Math.max(0, validLineCount - topology.buses.length + componentCount)
  const devicesUseExistingBuses = [
    ...topology.grid_forming_converters.map(item => item.bus_id),
    ...topology.infinite_buses.map(item => item.bus_id),
    ...topology.loads.map(item => item.bus_id),
  ].every(id => busIds.has(id))
  const groundedBusIds = new Set(topology.infinite_buses.map(item => item.bus_id))
  const ready = topology.buses.length > 0
    && invalidLineIds.length === 0
    && globallyUniqueIds
    && devicesUseExistingBuses
    && componentCount === 1
    && topology.infinite_buses.length > 0
    && topology.grid_forming_converters.length > 0
    && groundedBusIds.has(topology.reference_bus_id)
  return { componentCount, cycleRank, isolatedBusIds, invalidLineIds, ready }
}

function nextLineId(topology: NetworkTopology) {
  const occupied = new Set(topology.lines.map(line => line.id))
  let index = 1
  while (occupied.has(`line-${index}`)) index += 1
  return `line-${index}`
}

export default function NetworkGraphEditor({
  topology,
  layout,
  onLayoutChange,
  onLayoutCheckpoint,
  onTopologyChange,
  onMessage,
}: NetworkGraphEditorProps) {
  const [selectedElement, setSelectedElement] = useState<string | null>(null)
  const nodeTypes = useMemo(() => ({ power: graphNode }), [])
  const summary = useMemo(() => summarizeTopology(topology), [topology])
  const nodes = useMemo<Node<GraphNodeData>[]>(() => {
    const busIndex = new Map(topology.buses.map((bus, index) => [bus.id, index]))
    const busNodes = topology.buses.map((bus, index): Node<GraphNodeData> => ({
      id: busNodeId(bus.id),
      type: 'power',
      position: layout.node_positions[busNodeId(bus.id)] ?? fallbackPosition('bus', index),
      data: { label: bus.name, subtitle: `${bus.id} · ${(bus.nominal_voltage_v / 1000).toFixed(2)} kV`, kind: 'bus' },
      deletable: false,
      selected: selectedElement === busNodeId(bus.id),
    }))
    const gfmNodes = topology.grid_forming_converters.map((gfm, index): Node<GraphNodeData> => {
      const hostIndex = busIndex.get(gfm.bus_id) ?? index
      return {
        id: gfmNodeId(gfm.id), type: 'power',
        position: layout.node_positions[gfmNodeId(gfm.id)] ?? fallbackPosition('gfm', index, hostIndex),
        data: { label: gfm.name, subtitle: `VSM · D=${gfm.damping_coefficient_pu}`, kind: 'gfm' },
        deletable: false,
        selected: selectedElement === gfmNodeId(gfm.id),
      }
    })
    const gridNodes = topology.infinite_buses.map((grid, index): Node<GraphNodeData> => {
      const hostIndex = busIndex.get(grid.bus_id) ?? index
      return {
        id: gridNodeId(grid.id), type: 'power',
        position: layout.node_positions[gridNodeId(grid.id)] ?? fallbackPosition('grid', index, hostIndex),
        data: { label: grid.name, subtitle: `${grid.bus_id} · 参考电源`, kind: 'grid' },
        deletable: false,
        selected: selectedElement === gridNodeId(grid.id),
      }
    })
    return [...busNodes, ...gfmNodes, ...gridNodes]
  }, [layout.node_positions, selectedElement, topology])

  const selectedEntity = useMemo(() => {
    if (!selectedElement) return null
    const busId = entityId(selectedElement, 'bus')
    if (busId) return { kind: 'bus' as const, value: topology.buses.find(item => item.id === busId) }
    const gfmId = entityId(selectedElement, 'gfm')
    if (gfmId) return { kind: 'gfm' as const, value: topology.grid_forming_converters.find(item => item.id === gfmId) }
    const gridId = entityId(selectedElement, 'grid')
    if (gridId) return { kind: 'grid' as const, value: topology.infinite_buses.find(item => item.id === gridId) }
    const lineId = entityId(selectedElement, 'line')
    if (lineId) return { kind: 'line' as const, value: topology.lines.find(item => item.id === lineId) }
    return null
  }, [selectedElement, topology])

  const edges = useMemo<Edge[]>(() => {
    const lineEdges = topology.lines.map((line): Edge => ({
      id: `line:${line.id}`,
      source: busNodeId(line.from_bus_id),
      target: busNodeId(line.to_bus_id),
      label: `${line.in_service === false ? '停运 · ' : ''}${line.name}  X=${line.reactance_pu} p.u.`,
      type: 'smoothstep',
      data: { kind: 'line', entityId: line.id },
      selected: selectedElement === `line:${line.id}`,
      className: line.in_service === false ? 'out-of-service-edge' : undefined,
    }))
    const attachmentEdges: Edge[] = [
      ...topology.grid_forming_converters.map(gfm => ({
        id: `attachment:gfm:${gfm.id}`, source: gfmNodeId(gfm.id), target: busNodeId(gfm.bus_id),
        type: 'straight', selectable: false, deletable: false, className: 'attachment-edge',
      })),
      ...topology.infinite_buses.map(grid => ({
        id: `attachment:grid:${grid.id}`, source: gridNodeId(grid.id), target: busNodeId(grid.bus_id),
        type: 'straight', selectable: false, deletable: false, className: 'attachment-edge',
      })),
    ]
    return [...lineEdges, ...attachmentEdges]
  }, [selectedElement, topology])

  function updateNodePositions(changes: NodeChange<Node<GraphNodeData>>[]) {
    const positionChanges = changes.filter(change => change.type === 'position')
    if (positionChanges.length === 0) return
    const moved = applyNodeChanges(positionChanges, nodes)
    const nextPositions = { ...layout.node_positions }
    moved.forEach(node => { nextPositions[node.id] = node.position })
    onLayoutChange({ ...layout, node_positions: nextPositions })
  }

  function connect(connection: Connection) {
    if (!connection.source || !connection.target) return
    const fromBus = entityId(connection.source, 'bus')
    const toBus = entityId(connection.target, 'bus')
    if (!fromBus || !toBus) {
      onMessage('线路只能连接两个母线端口。')
      return
    }
    if (fromBus === toBus) {
      onMessage('线路首端和末端不能是同一母线。')
      return
    }
    const id = nextLineId(topology)
    const next = clone(topology)
    const line: ACLine = {
      id,
      name: `线路 ${id.split('-').pop()}`,
      from_bus_id: fromBus,
      to_bus_id: toBus,
      resistance_pu: 0.01,
      reactance_pu: 0.2,
      shunt_susceptance_pu: 0,
      in_service: true,
    }
    next.lines.push(line)
    onTopologyChange(next)
    onMessage(`已新增 ${line.name}；请在下方核对阻抗参数。`)
  }

  function changeEdges(changes: EdgeChange[]) {
    const removedLineIds = changes
      .filter(change => change.type === 'remove')
      .map(change => entityId(change.id, 'line'))
      .filter((id): id is string => id !== null)
    if (!removedLineIds.length) return
    const next = clone(topology)
    next.lines = next.lines.filter(line => !removedLineIds.includes(line.id))
    onTopologyChange(next)
    onMessage(`已删除 ${removedLineIds.length} 条线路。`)
  }

  function updateSelected(patch: Record<string, string | number | boolean>) {
    if (!selectedEntity?.value) return
    const next = clone(topology)
    const collection = selectedEntity.kind === 'bus' ? next.buses
      : selectedEntity.kind === 'line' ? next.lines
        : selectedEntity.kind === 'gfm' ? next.grid_forming_converters
          : next.infinite_buses
    const target = collection.find(item => item.id === selectedEntity.value?.id)
    if (!target) return
    Object.assign(target, patch)
    onTopologyChange(next)
  }

  const numberValue = (value: string, fallback: number) => {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : fallback
  }

  return <section className="network-graph-shell" data-testid="network-graph-editor">
    <header className="network-graph-summary">
      <div><b>网络图</b><small>拖动只调整版面；重新接线会改变计算拓扑</small></div>
      <div className="graph-checks" data-testid="topology-summary">
        <span className={summary.ready ? 'passed' : 'failed'}>{summary.ready ? '结构校核通过' : `${summary.componentCount} 个连通分量`}</span>
        <span>{summary.cycleRank} 个独立环路</span>
        <span>{topology.lines.filter(line => line.in_service !== false).length}/{topology.lines.length} 条线路投运</span>
      </div>
    </header>
    <div className="network-graph-stage">
    <div className="network-graph-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        connectionMode={ConnectionMode.Loose}
        onNodesChange={updateNodePositions}
        onNodeDragStart={onLayoutCheckpoint}
        onConnect={connect}
        onEdgesChange={changeEdges}
        onNodeClick={(_, node) => setSelectedElement(node.id)}
        onEdgeClick={(_, edge) => setSelectedElement(edge.id)}
        onPaneClick={() => setSelectedElement(null)}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1.1 }}
        minZoom={0.35}
        maxZoom={1.8}
        deleteKeyCode={['Backspace', 'Delete']}
        aria-label="电气网络建模画布"
      >
        <Background color="#d7e0e5" gap={22} size={1}/>
        <MiniMap position="top-right" pannable zoomable nodeColor={node => node.data.kind === 'gfm' ? '#169b9b' : node.data.kind === 'grid' ? '#dda53a' : '#334155'}/>
        <Controls showInteractive={false}/>
      </ReactFlow>
    </div>
    <aside className="graph-inspector" data-testid="graph-inspector">
      <div className="graph-inspector-title"><b>元件参数</b><small>选择图元后就地修改</small></div>
      {!selectedEntity?.value && <div className="graph-inspector-empty"><Network size={22}/><p>选择母线、线路、VSM 或等值电源，查看与修改计算参数。</p></div>}
      {selectedEntity?.kind === 'bus' && selectedEntity.value && <div className="graph-fields">
        <small>母线 · {selectedEntity.value.id}</small>
        <label>名称<input value={selectedEntity.value.name} onChange={event => updateSelected({ name: event.target.value })}/></label>
        <label>额定电压 / V<input type="number" min="1" value={selectedEntity.value.nominal_voltage_v} onChange={event => updateSelected({ nominal_voltage_v: numberValue(event.target.value, selectedEntity.value!.nominal_voltage_v) })}/></label>
      </div>}
      {selectedEntity?.kind === 'line' && selectedEntity.value && <div className="graph-fields">
        <small>线路 · {selectedEntity.value.id}</small>
        <label>名称<input value={selectedEntity.value.name} onChange={event => updateSelected({ name: event.target.value })}/></label>
        <label>首端<select value={selectedEntity.value.from_bus_id} onChange={event => updateSelected({ from_bus_id: event.target.value })}>{topology.buses.map(bus => <option key={bus.id}>{bus.id}</option>)}</select></label>
        <label>末端<select value={selectedEntity.value.to_bus_id} onChange={event => updateSelected({ to_bus_id: event.target.value })}>{topology.buses.map(bus => <option key={bus.id}>{bus.id}</option>)}</select></label>
        <div className="graph-field-pair">
          <label>R / p.u.<input type="number" min="0" step="0.01" value={selectedEntity.value.resistance_pu} onChange={event => updateSelected({ resistance_pu: numberValue(event.target.value, selectedEntity.value!.resistance_pu) })}/></label>
          <label>X / p.u.<input type="number" min="0.0001" step="0.01" value={selectedEntity.value.reactance_pu} onChange={event => updateSelected({ reactance_pu: numberValue(event.target.value, selectedEntity.value!.reactance_pu) })}/></label>
        </div>
        <label className="graph-checkbox"><input type="checkbox" checked={selectedEntity.value.in_service !== false} onChange={event => updateSelected({ in_service: event.target.checked })}/><span>线路投入运行</span></label>
      </div>}
      {selectedEntity?.kind === 'gfm' && selectedEntity.value && <div className="graph-fields">
        <small>构网型变流器 · {selectedEntity.value.id}</small>
        <label>名称<input value={selectedEntity.value.name} onChange={event => updateSelected({ name: event.target.value })}/></label>
        <label>接入母线<select value={selectedEntity.value.bus_id} onChange={event => updateSelected({ bus_id: event.target.value })}>{topology.buses.map(bus => <option key={bus.id}>{bus.id}</option>)}</select></label>
        <div className="graph-field-pair">
          <label>惯量 M / s<input type="number" min="0.001" step="0.1" value={selectedEntity.value.virtual_inertia_s} onChange={event => updateSelected({ virtual_inertia_s: numberValue(event.target.value, selectedEntity.value!.virtual_inertia_s) })}/></label>
          <label>阻尼 D / p.u.<input type="number" min="0.0001" step="0.05" value={selectedEntity.value.damping_coefficient_pu} onChange={event => updateSelected({ damping_coefficient_pu: numberValue(event.target.value, selectedEntity.value!.damping_coefficient_pu) })}/></label>
        </div>
        <label>有功测量 Tₚ / s<input type="number" min="0.001" step="0.01" value={selectedEntity.value.active_power_measurement_time_constant_s} onChange={event => updateSelected({ active_power_measurement_time_constant_s: numberValue(event.target.value, selectedEntity.value!.active_power_measurement_time_constant_s) })}/></label>
      </div>}
      {selectedEntity?.kind === 'grid' && selectedEntity.value && <div className="graph-fields">
        <small>等值电源 · {selectedEntity.value.id}</small>
        <label>名称<input value={selectedEntity.value.name} onChange={event => updateSelected({ name: event.target.value })}/></label>
        <label>接入母线<select value={selectedEntity.value.bus_id} onChange={event => updateSelected({ bus_id: event.target.value })}>{topology.buses.map(bus => <option key={bus.id}>{bus.id}</option>)}</select></label>
        <label>电压 / p.u.<input type="number" min="0.5" max="1.5" step="0.01" value={selectedEntity.value.voltage_magnitude_pu ?? 1} onChange={event => updateSelected({ voltage_magnitude_pu: numberValue(event.target.value, selectedEntity.value!.voltage_magnitude_pu ?? 1) })}/></label>
      </div>}
    </aside>
    </div>
    {!summary.ready && <p className="graph-diagnostic"><Zap size={14}/>请先消除孤岛或无效线路，并确认网络含有 VSM 和等值电源。</p>}
  </section>
}
