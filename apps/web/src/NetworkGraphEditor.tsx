import { useEffect, useMemo, useRef, useState, type PointerEvent } from 'react'
import {
  Background,
  ConnectionMode,
  BaseEdge,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  getSmoothStepPath,
  useUpdateNodeInternals,
  type Connection,
  type Edge,
  type EdgeChange,
  type EdgeProps,
  type Node,
  type NodeChange,
  type NodeProps,
  type ReactFlowInstance,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Hand, Keyboard as KeyboardIcon, Maximize, MousePointer2, Network, RotateCcw, Trash2, Waypoints, X, Zap, ZoomIn, ZoomOut } from 'lucide-react'
import type { NetworkTopology } from './api'
import ElectricalSymbol from './ElectricalSymbol'
import { createNetworkLine, reconnectNetworkLine, validateLineEndpoints } from './networkEditorOperations'
import { compileIdealConnections, createIdealConnection, parseIdealConnections, removeIdealConnection, type IdealConnection } from './networkIdealConnections'
import { insertCanvasElement, removeCanvasElement, type CanvasElementKind } from './networkPaletteOperations'
import { DEFAULT_NETWORK_SHORTCUTS, LOCAL_STORAGE_KEY, NETWORK_SHORTCUT_LABELS, parseStoredNetworkShortcuts, validateNetworkShortcuts, type NetworkShortcuts, type ShortcutAction } from './networkEditorShortcuts'
import { summarizeTopology } from './networkTopologyChecks'
import { DEFAULT_BUS_WIDTH, MIN_BUS_WIDTH, MAX_BUS_WIDTH, diagramBusWidth, mergeDiagramBusWidth, isFiniteDiagramPosition, mergeDiagramDimensions, mergeDiagramPositions, type DiagramLayout, type DiagramPosition, type DiagramNodeDimensions } from './networkDiagramPositions'
export { summarizeTopology } from './networkTopologyChecks'
export type { TopologySummary } from './networkTopologyChecks'
export type { DiagramLayout, DiagramPosition } from './networkDiagramPositions'

type GraphNodeData = {
  entityId: string
  label: string
  subtitle: string
  kind: 'bus' | 'gfm' | 'grid'
  connecting?: boolean
  voltageLabel?: string
  busWidth?: number
  onResizeStart?: (event: PointerEvent<HTMLButtonElement>, busId: string) => void
  onResizeMove?: (event: PointerEvent<HTMLButtonElement>) => void
  onResizeEnd?: (event: PointerEvent<HTMLButtonElement>) => void
}

type EditorMode = 'select' | 'connect' | 'pan'
export type PlacementKind = CanvasElementKind | 'line' | 'wire'
export type PlacementRequest = { kind: PlacementKind; sequence: number }

type NetworkGraphEditorProps = {
  topology: NetworkTopology
  idealConnections: IdealConnection[]
  onIdealConnectionsChange: (connections: IdealConnection[], message: string) => void
  layout: DiagramLayout
  onLayoutChange: (update: DiagramLayout | ((current: DiagramLayout) => DiagramLayout)) => void
  onLayoutCheckpoint: () => void
  onTopologyChange: (topology: NetworkTopology) => void
  onDiagramChange: (topology: NetworkTopology, layout: DiagramLayout, message: string) => void
  onMessage: (message: string) => void
  placementRequest?: PlacementRequest | null
  resetRevision?: number
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
  if (kind === 'gfm') return { x: 114 + (busIndex % 4) * 230, y: 25 + Math.floor(busIndex / 4) * 220 }
  return { x: 114 + (busIndex % 4) * 230, y: 300 + Math.floor(busIndex / 4) * 220 }
}

function graphNode({ id, data, selected, isConnectable }: NodeProps<Node<GraphNodeData>>) {
  const updateNodeInternals = useUpdateNodeInternals()
  useEffect(() => { updateNodeInternals(id) }, [id, data.busWidth, updateNodeInternals])
  const label = <div className="electrical-node-label"><b title={`${data.label} · ${data.entityId}`}>{data.label}</b></div>
  const subtitle = <small className="electrical-node-subtitle" title={data.subtitle}>{data.kind === 'bus' ? data.voltageLabel : data.subtitle}</small>
  const terminalClass = `electrical-terminal ${isConnectable ? 'terminal-active' : 'terminal-idle'}`
  return <div data-testid={`network-node-${data.entityId}`} style={data.kind === 'bus' ? { width: data.busWidth, minWidth: data.busWidth } : undefined} className={`power-node electrical-node ${data.kind} ${selected ? 'selected' : ''} ${data.connecting ? 'connection-origin' : ''}`}>
    {data.kind !== 'grid' && label}
    {(data.kind === 'gfm' || data.kind === 'bus') && subtitle}
    <div className="electrical-node-symbol" style={data.kind === 'bus' ? { width: (data.busWidth ?? DEFAULT_BUS_WIDTH) - 16 } : undefined}>
      <ElectricalSymbol kind={data.kind} deviceId={data.entityId} busSymbolWidth={(data.busWidth ?? DEFAULT_BUS_WIDTH) - 16}/>
      {data.kind === 'bus' && <>
        <Handle className={terminalClass} id="north" type="target" position={Position.Top} isConnectable={isConnectable} isConnectableStart={isConnectable} isConnectableEnd={isConnectable}/>
        <Handle className={terminalClass} id="east" type="source" position={Position.Right} isConnectable={isConnectable} isConnectableStart={isConnectable} isConnectableEnd={isConnectable}/>
        <Handle className={terminalClass} id="south" type="source" position={Position.Bottom} isConnectable={isConnectable} isConnectableStart={isConnectable} isConnectableEnd={isConnectable}/>
        <Handle className={terminalClass} id="west" type="target" position={Position.Left} isConnectable={isConnectable} isConnectableStart={isConnectable} isConnectableEnd={isConnectable}/>
        {selected && <button type="button" data-testid={`network-bus-resize-${data.entityId}`} className="network-bus-resize nodrag nopan" aria-label={`调整母线 ${data.label} 长度`} title="拖动调整母线长度（仅版面）" onPointerDown={event => data.onResizeStart?.(event, data.entityId)} onPointerMove={data.onResizeMove} onPointerUp={data.onResizeEnd} onPointerCancel={data.onResizeEnd} onClick={event => event.stopPropagation()}>↔</button>}
      </>}
      {data.kind === 'gfm' && <Handle id="output" className={`attachment-handle ${terminalClass}`} type="source" position={Position.Bottom} isConnectable={isConnectable}/>}
      {data.kind === 'grid' && <Handle id="output" className={`attachment-handle ${terminalClass}`} type="source" position={Position.Top} isConnectable={isConnectable}/>}
    </div>
    {data.kind === 'grid' && <>{label}{subtitle}</>}
  </div>
}

function electricalEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, label, style, data }: EdgeProps) {
  let [path, labelX, labelY] = getSmoothStepPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, borderRadius: 4 })
  // Separate parallel branches visually only. This is not obstacle-avoiding
  // routing and never changes the branch endpoints or electrical parameters.
  if (data?.parallel === true && typeof data.laneOffset === 'number') {
    const horizontal = sourcePosition === Position.Left || sourcePosition === Position.Right
    const gap = horizontal ? Math.abs(targetX - sourceX) : Math.abs(targetY - sourceY)
    const stub = Math.max(12, Math.min(24, gap / 4))
    if (horizontal) {
      const sourceStub = sourceX + (sourcePosition === Position.Right ? stub : -stub)
      const targetStub = targetX + (targetPosition === Position.Right ? stub : -stub)
      labelX = (sourceStub + targetStub) / 2
      labelY = (sourceY + targetY) / 2 + data.laneOffset
      path = `M ${sourceX},${sourceY} L ${sourceStub},${sourceY} L ${sourceStub},${labelY} L ${targetStub},${labelY} L ${targetStub},${targetY} L ${targetX},${targetY}`
    } else {
      const sourceStub = sourceY + (sourcePosition === Position.Bottom ? stub : -stub)
      const targetStub = targetY + (targetPosition === Position.Bottom ? stub : -stub)
      labelX = (sourceX + targetX) / 2 + data.laneOffset
      labelY = (sourceStub + targetStub) / 2
      path = `M ${sourceX},${sourceY} L ${sourceX},${sourceStub} L ${labelX},${sourceStub} L ${labelX},${targetStub} L ${targetX},${targetStub} L ${targetX},${targetY}`
    }
  }
  return <g data-testid={`network-edge-${String(data?.entityId ?? id)}`}>
    <title>{String(data?.description ?? label ?? '')}</title>
    <BaseEdge id={id} path={path} label={label} labelX={labelX} labelY={labelY} style={style} interactionWidth={24} labelBgPadding={[5, 3]} labelBgBorderRadius={3}/>
  </g>
}

export function emptyDiagramLayout(): DiagramLayout {
  return { schema_version: 'gfm-network-diagram-layout/1.0', node_positions: {} }
}

export function parseDiagramLayout(value: unknown): DiagramLayout {
  if (!value || typeof value !== 'object') throw new Error('案例缺少图形版面数据。')
  const candidate = value as { schema_version?: unknown; node_positions?: unknown; bus_widths?: unknown }
  if ((candidate.schema_version !== 'gfm-network-diagram-layout/1.0' && candidate.schema_version !== 'gfm-network-diagram-layout/1.1')
      || !candidate.node_positions || typeof candidate.node_positions !== 'object' || Array.isArray(candidate.node_positions)) {
    throw new Error('图形版面版本或节点坐标字段无效。')
  }
  const positions: Record<string, DiagramPosition> = Object.create(null)
  Object.entries(candidate.node_positions).forEach(([id, position]) => {
    if (!position || typeof position !== 'object') throw new Error(`图元 ${id} 的坐标无效。`)
    const point = position as { x?: unknown; y?: unknown }
    if (typeof point.x !== 'number' || !Number.isFinite(point.x)
        || typeof point.y !== 'number' || !Number.isFinite(point.y)) {
      throw new Error(`图元 ${id} 的坐标必须是有限数值。`)
    }
    positions[id] = { x: point.x, y: point.y }
  })
  let busWidths: Record<string, number> | undefined
  if (candidate.bus_widths !== undefined) {
    if (candidate.schema_version !== 'gfm-network-diagram-layout/1.1') throw new Error('母线长度数据须使用图形版面版本 1.1，不能混入旧版本。')
    if (!candidate.bus_widths || typeof candidate.bus_widths !== 'object' || Array.isArray(candidate.bus_widths)) throw new Error('母线长度字段必须是对象。')
    busWidths = Object.create(null) as Record<string, number>
    for (const [id, width] of Object.entries(candidate.bus_widths)) {
      if (!id || typeof width !== 'number' || !Number.isFinite(width) || width < MIN_BUS_WIDTH || width > MAX_BUS_WIDTH) throw new Error(`母线 ${id} 的长度必须为 ${MIN_BUS_WIDTH}–${MAX_BUS_WIDTH} 的有限数值。`)
      busWidths[id] = width
    }
  }
  return { schema_version: candidate.schema_version as DiagramLayout['schema_version'], node_positions: positions, ...(busWidths ? { bus_widths: busWidths } : {}) }
}

export default function NetworkGraphEditor({
  topology,
  idealConnections,
  onIdealConnectionsChange,
  layout,
  onLayoutChange,
  onLayoutCheckpoint,
  onTopologyChange,
  onDiagramChange,
  onMessage,
  placementRequest,
  resetRevision = 0,
}: NetworkGraphEditorProps) {
  const [selectedElement, setSelectedElement] = useState<string | null>(null)
  const [draftName, setDraftName] = useState('')
  const [mode, setMode] = useState<EditorMode>('select')
  const [connectKind, setConnectKind] = useState<'wire' | 'line'>('wire')
  const [connectionOrigin, setConnectionOrigin] = useState<string | null>(null)
  const [snap, setSnap] = useState(true)
  const [showMiniMap, setShowMiniMap] = useState(false)
  const [flow, setFlow] = useState<ReactFlowInstance<Node<GraphNodeData>, Edge> | null>(null)
  const [nodeDimensions, setNodeDimensions] = useState<DiagramNodeDimensions>({})
  const [canvasRevision, setCanvasRevision] = useState(0)
  const [placement, setPlacement] = useState<CanvasElementKind | null>(null)
  const [spacePan, setSpacePan] = useState(false)
  const [dragGhost, setDragGhost] = useState<{ kind: PlacementKind; x: number; y: number } | null>(null)
  const [showShortcuts, setShowShortcuts] = useState(false)
  const [shortcutMessage, setShortcutMessage] = useState('')
  const [shortcuts, setShortcuts] = useState<NetworkShortcuts>(() => {
    try { return parseStoredNetworkShortcuts(window.localStorage.getItem(LOCAL_STORAGE_KEY)) }
    catch { return { ...DEFAULT_NETWORK_SHORTCUTS } }
  })
  const [shortcutDraft, setShortcutDraft] = useState<NetworkShortcuts>(shortcuts)
  const shellRef = useRef<HTMLElement>(null)
  const canvasRef = useRef<HTMLDivElement>(null)
  const paletteDrag = useRef<{ kind: PlacementKind; x: number; y: number; moved: boolean; pointerId: number; element: HTMLButtonElement } | null>(null)
  const busResize = useRef<{ busId: string; x: number; width: number; zoom: number; pointerId: number; element: HTMLButtonElement } | null>(null)
  const keyboardHandler = useRef<(event: globalThis.KeyboardEvent) => void>(() => {})
  keyboardHandler.current = handleCanvasKeyboard
  const effectiveMode = spacePan ? 'pan' : mode
  const nodeTypes = useMemo(() => ({ power: graphNode }), [])
  const edgeTypes = useMemo(() => ({ electrical: electricalEdge }), [])
  const compiled = useMemo(() => compileIdealConnections(topology, idealConnections), [topology, idealConnections])
  const summary = useMemo(() => {
    const checked = summarizeTopology(compiled.ok ? compiled.topology : topology)
    if (compiled.ok) return checked
    let idealWiringIssue: string | null = null
    try { parseIdealConnections(idealConnections, topology) }
    catch (reason) { idealWiringIssue = reason instanceof Error ? reason.message : '普通导线连接关系无效。' }
    return { ...checked, wiringValid: checked.wiringValid && !idealWiringIssue,
      wiringIssues: idealWiringIssue ? [idealWiringIssue, ...checked.wiringIssues] : checked.wiringIssues,
      lowFrequencyApplicable: false, lowFrequencyIssues: [...new Set([...compiled.issues, ...checked.lowFrequencyIssues])] }
  }, [compiled, topology, idealConnections])
  useEffect(() => {
    if (connectionOrigin && !nodes.some(node => node.id === connectionOrigin)) setConnectionOrigin(null)
  }, [topology, connectionOrigin])
  useEffect(() => { if (placementRequest) beginPlacement(placementRequest.kind) }, [placementRequest])
  useEffect(() => { cancelPaletteDrag(); chooseMode('select'); setSelectedElement(null); setSpacePan(false); setShowShortcuts(false) }, [resetRevision])
  useEffect(() => () => {
    const drag = paletteDrag.current
    if (drag?.element.hasPointerCapture(drag.pointerId)) drag.element.releasePointerCapture(drag.pointerId)
    paletteDrag.current = null
  }, [])
  useEffect(() => {
    const host = shellRef.current?.closest('.model-editor') ?? shellRef.current
    const listener = (event: Event) => keyboardHandler.current(event as globalThis.KeyboardEvent)
    host?.addEventListener('keydown', listener)
    return () => { host?.removeEventListener('keydown', listener) }
  }, [])
  useEffect(() => {
    const releaseSpace = (event: globalThis.KeyboardEvent) => { if (event.code === 'Space') setSpacePan(false) }
    const clearPan = () => setSpacePan(false)
    window.addEventListener('keyup', releaseSpace)
    window.addEventListener('blur', clearPan)
    return () => { window.removeEventListener('keyup', releaseSpace); window.removeEventListener('blur', clearPan) }
  }, [])
  const nodes = useMemo<Node<GraphNodeData>[]>(() => {
    const busIndex = new Map(topology.buses.map((bus, index) => [bus.id, index]))
    const busNodes = topology.buses.map((bus, index): Node<GraphNodeData> => ({
      id: busNodeId(bus.id),
      type: 'power',
      position: layout.node_positions[busNodeId(bus.id)] ?? fallbackPosition('bus', index),
      measured: nodeDimensions[busNodeId(bus.id)],
      data: { entityId: bus.id, label: bus.name, subtitle: `${bus.id} · ${(bus.nominal_voltage_v / 1000).toFixed(2)} kV`, voltageLabel: `${(bus.nominal_voltage_v / 1000).toFixed(2)} kV`, kind: 'bus', connecting: connectionOrigin === busNodeId(bus.id), busWidth: diagramBusWidth(layout, bus.id), onResizeStart: startBusResize, onResizeMove: moveBusResize, onResizeEnd: endBusResize },
      deletable: false,
      selected: selectedElement === busNodeId(bus.id),
    }))
    const gfmNodes = topology.grid_forming_converters.map((gfm, index): Node<GraphNodeData> => {
      const hostIndex = busIndex.get(gfm.bus_id) ?? index
      const siblings = topology.grid_forming_converters.filter(item => item.bus_id === gfm.bus_id)
      const siblingOffset = (siblings.findIndex(item => item.id === gfm.id) - (siblings.length - 1) / 2) * 148
      const host = busNodes.find(node => node.id === busNodeId(gfm.bus_id))
      const fallback = host ? { x: host.position.x + diagramBusWidth(layout, gfm.bus_id) / 2 - 64, y: host.position.y - 144 } : fallbackPosition('gfm', index, hostIndex)
      return {
        id: gfmNodeId(gfm.id), type: 'power',
        position: layout.node_positions[gfmNodeId(gfm.id)] ?? { ...fallback, x: fallback.x + siblingOffset },
        measured: nodeDimensions[gfmNodeId(gfm.id)],
        data: { entityId: gfm.id, label: gfm.name, subtitle: gfm.control_mode === 'virtual_synchronous_machine' ? `VSM · D=${gfm.damping_coefficient_pu}` : gfm.control_mode === 'droop' ? '下垂控制' : '自定义控制', kind: 'gfm', connecting: connectionOrigin === gfmNodeId(gfm.id) },
        deletable: false,
        selected: selectedElement === gfmNodeId(gfm.id),
      }
    })
    const gridNodes = topology.infinite_buses.map((grid, index): Node<GraphNodeData> => {
      const hostIndex = busIndex.get(grid.bus_id) ?? index
      const siblings = topology.infinite_buses.filter(item => item.bus_id === grid.bus_id)
      const siblingOffset = (siblings.findIndex(item => item.id === grid.id) - (siblings.length - 1) / 2) * 148
      const host = busNodes.find(node => node.id === busNodeId(grid.bus_id))
      const fallback = host ? { x: host.position.x + diagramBusWidth(layout, grid.bus_id) / 2 - 64, y: host.position.y + 132 } : fallbackPosition('grid', index, hostIndex)
      return {
        id: gridNodeId(grid.id), type: 'power',
        position: layout.node_positions[gridNodeId(grid.id)] ?? { ...fallback, x: fallback.x + siblingOffset },
        measured: nodeDimensions[gridNodeId(grid.id)],
        data: { entityId: grid.id, label: grid.name, subtitle: `${grid.bus_id} · 外部电网等值`, kind: 'grid', connecting: connectionOrigin === gridNodeId(grid.id) },
        deletable: false,
        selected: selectedElement === gridNodeId(grid.id),
      }
    })
    return [...busNodes, ...gfmNodes, ...gridNodes]
  }, [layout, selectedElement, topology, connectionOrigin, nodeDimensions, flow, effectiveMode])

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
    const wireId = entityId(selectedElement, 'wire')
    if (wireId) return { kind: 'wire' as const, value: idealConnections.find(item => item.id === wireId) }
    return null
  }, [selectedElement, topology, idealConnections])
  useEffect(() => { setDraftName(selectedEntity?.value?.name ?? '') }, [selectedElement, selectedEntity?.value?.name])

  const edges = useMemo<Edge[]>(() => {
    const busPositions = new Map(nodes.filter(node => node.data.kind === 'bus').map(node => [node.data.entityId, node.position]))
    const pairKey = (from: string, to: string) => JSON.stringify([from, to].sort())
    const parallelGroups = new Map<string, string[]>()
    topology.lines.forEach(line => {
      const key = pairKey(line.from_bus_id, line.to_bus_id)
      parallelGroups.set(key, [...(parallelGroups.get(key) ?? []), line.id])
    })
    parallelGroups.forEach(ids => ids.sort())
    const lineEdges = topology.lines.map((line): Edge => {
      const from = busPositions.get(line.from_bus_id)
      const to = busPositions.get(line.to_bus_id)
      const dx = (to?.x ?? 0) - (from?.x ?? 0)
      const dy = (to?.y ?? 0) - (from?.y ?? 0)
      const horizontal = Math.abs(dx) >= Math.abs(dy)
      const group = parallelGroups.get(pairKey(line.from_bus_id, line.to_bus_id))!
      return {
      id: `line:${line.id}`,
      source: busNodeId(line.from_bus_id),
      target: busNodeId(line.to_bus_id),
      label: `${line.in_service === false ? '停运 · ' : ''}${line.name}`,
      type: 'electrical',
      sourceHandle: horizontal ? (dx >= 0 ? 'east' : 'west') : (dy >= 0 ? 'south' : 'north'),
      targetHandle: horizontal ? (dx >= 0 ? 'west' : 'east') : (dy >= 0 ? 'north' : 'south'),
      data: { kind: 'line', entityId: line.id, parallel: group.length > 1,
        laneOffset: (group.indexOf(line.id) - (group.length - 1) / 2) * 88,
        description: `${line.name} · ${line.id} · R=${line.resistance_pu} p.u. · X=${line.reactance_pu} p.u. · ${line.in_service === false ? '停运' : '投运'}` },
      selected: selectedElement === `line:${line.id}`,
      className: line.in_service === false ? 'out-of-service-edge' : undefined,
      }
    })
    const attachmentEdges: Edge[] = [
      ...topology.grid_forming_converters.map(gfm => ({
        id: `attachment:gfm:${gfm.id}`, source: gfmNodeId(gfm.id), target: busNodeId(gfm.bus_id),
        sourceHandle: 'output', targetHandle: 'north',
        type: 'straight', selectable: false, deletable: false, reconnectable: false, className: 'attachment-edge',
      })),
      ...topology.infinite_buses.map(grid => ({
        id: `attachment:grid:${grid.id}`, source: gridNodeId(grid.id), target: busNodeId(grid.bus_id),
        sourceHandle: 'output', targetHandle: 'south',
        type: 'straight', selectable: false, deletable: false, reconnectable: false, className: 'attachment-edge',
      })),
    ]
    const wireEdges = idealConnections.map((wire): Edge => {
      const from = busPositions.get(wire.from_bus_id)
      const to = busPositions.get(wire.to_bus_id)
      const dx = (to?.x ?? 0) - (from?.x ?? 0)
      const dy = (to?.y ?? 0) - (from?.y ?? 0)
      const horizontal = Math.abs(dx) >= Math.abs(dy)
      return { id: `wire:${wire.id}`, source: busNodeId(wire.from_bus_id), target: busNodeId(wire.to_bus_id),
        sourceHandle: horizontal ? (dx >= 0 ? 'east' : 'west') : (dy >= 0 ? 'south' : 'north'),
        targetHandle: horizontal ? (dx >= 0 ? 'west' : 'east') : (dy >= 0 ? 'north' : 'south'),
        type: 'electrical', label: wire.name, className: 'ideal-wire', selected: selectedElement === `wire:${wire.id}`,
        data: { kind: 'wire', entityId: wire.id, description: `${wire.name} · 普通导线（无独立阻抗）；计算时合并电气节点，版面保留两条母线。` } }
    })
    return [...lineEdges, ...wireEdges, ...attachmentEdges]
  }, [selectedElement, topology, idealConnections, nodes])

  function startBusResize(event: PointerEvent<HTMLButtonElement>, busId: string) {
    if (event.button !== 0 || effectiveMode === 'pan') return
    event.preventDefault(); event.stopPropagation()
    event.currentTarget.setPointerCapture(event.pointerId)
    onLayoutCheckpoint()
    busResize.current = { busId, x: event.clientX, width: diagramBusWidth(layout, busId), zoom: flow?.getZoom() ?? 1, pointerId: event.pointerId, element: event.currentTarget }
  }

  function moveBusResize(event: PointerEvent<HTMLButtonElement>) {
    const drag = busResize.current
    if (!drag || drag.pointerId !== event.pointerId) return
    event.preventDefault(); event.stopPropagation()
    const width = drag.width + (event.clientX - drag.x) / drag.zoom
    onLayoutChange(current => mergeDiagramBusWidth(current, drag.busId, width))
  }

  function endBusResize(event: PointerEvent<HTMLButtonElement>) {
    const drag = busResize.current
    if (!drag || drag.pointerId !== event.pointerId) return
    event.preventDefault(); event.stopPropagation()
    if (drag.element.hasPointerCapture(drag.pointerId)) drag.element.releasePointerCapture(drag.pointerId)
    busResize.current = null
  }

  function updateNodePositions(changes: NodeChange<Node<GraphNodeData>>[]) {
    const allowedNodeIds = new Set(nodes.map(node => node.id))
    const dimensionChanges = changes.filter(change => change.type === 'dimensions')
    if (dimensionChanges.length) {
      setNodeDimensions(current => mergeDiagramDimensions(current, dimensionChanges, allowedNodeIds))
    }
    if (effectiveMode === 'pan' || placement) return
    const positionChanges = changes.filter(change => change.type === 'position')
    if (positionChanges.some(change => allowedNodeIds.has(change.id) && change.position && !isFiniteDiagramPosition(change.position))) {
      onMessage('已忽略无效的图元坐标，原位置保留；若显示异常，可点击“恢复显示”。')
    }
    const moved = positionChanges.flatMap(change => allowedNodeIds.has(change.id) && isFiniteDiagramPosition(change.position)
      ? [{ id: change.id, position: { ...change.position } }] : [])
    if (!moved.length) return
    onLayoutChange(current => mergeDiagramPositions(current, moved, allowedNodeIds))
  }

  function restoreCanvasDisplay() {
    cancelPaletteDrag()
    chooseMode('select')
    setSpacePan(false)
    setFlow(null)
    setCanvasRevision(value => value + 1)
    onMessage('已重新显示网络；元件、参数与图元位置均未改变。')
  }

  function connect(connection: Connection) {
    if (effectiveMode !== 'connect') return
    if (!connection.source || !connection.target) return
    connectNodes(connection.source, connection.target)
  }

  function connectNodes(fromNode: string, toNode: string) {
    const fromBus = entityId(fromNode, 'bus')
    const toBus = entityId(toNode, 'bus')
    if (fromBus && toBus) {
      if (connectKind === 'line') createLine(fromBus, toBus)
      else {
        const outcome = createIdealConnection(topology, idealConnections, fromBus, toBus)
        if (!outcome.ok) { onMessage(outcome.message); return }
        onIdealConnectionsChange(outcome.connections, outcome.message)
        setSelectedElement(`wire:${outcome.connection.id}`)
        setConnectionOrigin(null)
      }
      return
    }
    if (connectKind === 'line') { onMessage('有阻抗线路只能连接两条母线；电源接入请选择普通导线。'); return }
    const deviceNode = fromBus ? toNode : fromNode
    const targetBus = fromBus ?? toBus
    if (!targetBus || (!entityId(deviceNode, 'gfm') && !entityId(deviceNode, 'grid'))) { onMessage('普通接线需连接两条母线，或一个电源端子与母线。'); return }
    const gfmId = entityId(deviceNode, 'gfm')
    const gridId = entityId(deviceNode, 'grid')
    if (reassignSource(gfmId ? 'gfm' : 'grid', gfmId ?? gridId!, targetBus)) setConnectionOrigin(null)
  }

  function reassignSource(kind: 'gfm' | 'grid', id: string, toBusId: string): boolean {
    const source = (kind === 'gfm' ? topology.grid_forming_converters : topology.infinite_buses).find(item => item.id === id)
    if (!source) { onMessage('电源已不存在，原接线保留。'); return false }
    if (source.bus_id === toBusId) { onMessage(`电源 ${source.name} 已接入母线 ${toBusId}，无需修改。`); return true }
    const checked = validateLineEndpoints(topology, source.bus_id, toBusId)
    if (!checked.ok) { onMessage(checked.message); return false }
    const targetGroup = new Set([toBusId])
    let added = true
    while (added) {
      added = false
      for (const wire of idealConnections) {
        if (targetGroup.has(wire.from_bus_id) && !targetGroup.has(wire.to_bus_id)) { targetGroup.add(wire.to_bus_id); added = true }
        if (targetGroup.has(wire.to_bus_id) && !targetGroup.has(wire.from_bus_id)) { targetGroup.add(wire.from_bus_id); added = true }
      }
    }
    const sameTarget = (busId: string) => targetGroup.has(busId)
    if (topology.grid_forming_converters.some(item => !(kind === 'gfm' && item.id === id) && sameTarget(item.bus_id))
      || topology.infinite_buses.some(item => !(kind === 'grid' && item.id === id) && sameTarget(item.bus_id))) {
      onMessage(`母线 ${toBusId} 的电气端口已接入电源；当前低频模型一个电气节点只能接入一个电源，原接线保留。`)
      return false
    }
    const next = clone(topology)
    const device = (kind === 'gfm' ? next.grid_forming_converters : next.infinite_buses).find(item => item.id === id)!
    device.bus_id = toBusId
    if (kind === 'grid' && next.reference_bus_id === source.bus_id) next.reference_bus_id = toBusId
    onTopologyChange(next)
    setSelectedElement(`${kind}:${id}`)
    onMessage(`已将 ${source.name} 普通接线至母线 ${toBusId}；未新增阻抗线路。`)
    return true
  }

  function updateWire(id: string, patch: Record<string, string | number | boolean>) {
    const previous = idealConnections.find(wire => wire.id === id)
    if (!previous) return
    const candidate = { ...previous, ...patch } as IdealConnection
    if (!candidate.name.trim()) { onMessage('导线名称不能为空。'); return }
    const other = removeIdealConnection(idealConnections, id)
    const checked = createIdealConnection(topology, other, candidate.from_bus_id, candidate.to_bus_id)
    if (!checked.ok) { onMessage(`${checked.message}原导线保持不变。`); return }
    onIdealConnectionsChange(idealConnections.map(wire => wire.id === id ? candidate : wire), `已修改普通导线 ${candidate.name}。`)
  }

  function createLine(fromBus: string, toBus: string) {
    const outcome = createNetworkLine(topology, fromBus, toBus)
    if (!outcome.ok) { onMessage(outcome.message); return }
    onTopologyChange(outcome.topology)
    setSelectedElement(`line:${outcome.line.id}`)
    setConnectionOrigin(null)
    onMessage(`已新增 ${outcome.line.name}；R、X 为示例初值，请核对实际阻抗参数。`)
  }

  function reconnect(edge: Edge, connection: Connection) {
    if (effectiveMode !== 'connect') return
    const lineId = entityId(edge.id, 'line')
    const wireId = entityId(edge.id, 'wire')
    const fromBus = connection.source ? entityId(connection.source, 'bus') : null
    const toBus = connection.target ? entityId(connection.target, 'bus') : null
    if (wireId) {
      if (!fromBus || !toBus) { onMessage('普通导线重接必须为两个母线端口，原导线保持不变。'); return }
      updateWire(wireId, { from_bus_id: fromBus, to_bus_id: toBus })
      return
    }
    if (!lineId || !fromBus || !toBus) { onMessage('接线未完成：线路只能连接两个母线端口，原线路保持不变。'); return }
    const outcome = reconnectNetworkLine(topology, lineId, fromBus, toBus)
    if (!outcome.ok) { onMessage(`${outcome.message}原线路保持不变。`); return }
    onTopologyChange(outcome.topology)
    setSelectedElement(`line:${lineId}`)
    setConnectionOrigin(null)
    onMessage(`已修改线路 ${lineId} 的接线；电气参数保持不变。`)
  }

  function selectNode(node: Node<GraphNodeData>, point: { x: number; y: number }) {
    if (effectiveMode === 'pan') return
    if (placement) { placeAtScreen(placement, point, node.id); return }
    setSelectedElement(node.id)
    if (mode !== 'connect') return
    const busId = entityId(node.id, 'bus')
    if (!busId && connectKind === 'line') { onMessage('阻抗线路只连接母线；电源接入请切换普通导线。'); return }
    if (!connectionOrigin) {
      setConnectionOrigin(node.id)
      onMessage(`起点为 ${node.data.label}；请再点击终点母线${connectKind === 'wire' ? '或电源' : ''}，或取消接线。`)
    } else connectNodes(connectionOrigin, node.id)
  }

  function chooseMode(nextMode: EditorMode) {
    setMode(nextMode)
    setPlacement(null)
    setConnectionOrigin(null)
  }

  function beginPlacement(kind: PlacementKind) {
    setSpacePan(false)
    setConnectionOrigin(null)
    if (kind === 'line' || kind === 'wire') { setConnectKind(kind); setPlacement(null); setMode('connect'); onMessage(kind === 'line' ? '请依次选择阻抗线路的起点与终点母线。' : '请依次选择普通导线端点；可连接母线，或将电源接入母线。'); return }
    setPlacement(kind)
    setMode('select')
    onMessage(`请在画布点击放置${kind === 'bus' ? '母线' : kind === 'gfm' ? '构网型变流器' : '等值电源'}；按 Esc 取消。`)
    shellRef.current?.focus({ preventScroll: true })
  }

  function placeAtScreen(kind: PlacementKind, point: { x: number; y: number }, hitNodeId?: string) {
    if (!flow) return
    const targetBusId = hitNodeId ? entityId(hitNodeId, 'bus') : null
    if (kind === 'line' || kind === 'wire') {
      setConnectKind(kind)
      chooseMode('connect')
      if (targetBusId) setConnectionOrigin(busNodeId(targetBusId))
      onMessage(targetBusId ? `起点为 ${targetBusId}，请点击终点母线。` : '请依次点击两条母线；线路不能悬空放置。')
      return
    }
    if (hitNodeId && !targetBusId && kind !== 'bus') { onMessage('请将设备放到母线上或画布空白处，不能直接接入另一台设备的符号。'); return }
    if (hitNodeId && kind === 'bus') { onMessage('新母线请放在画布空白处；移动已有母线请直接拖动图元。'); return }
    const center = flow.screenToFlowPosition(point, { snapToGrid: false })
    let position = { x: center.x - (kind === 'bus' ? 88 : 64), y: center.y - (kind === 'bus' ? 44 : 64) }
    if (targetBusId && kind !== 'bus') {
      const bus = nodes.find(node => node.id === busNodeId(targetBusId))
      if (!bus) { onMessage('目标母线已不存在，未放置设备。'); return }
      position = { x: bus.position.x + diagramBusWidth(layout, targetBusId) / 2 - 64, y: bus.position.y + (kind === 'gfm' ? -144 : 132) }
    }
    if (snap && !targetBusId) position = { x: Math.round(position.x / 20) * 20, y: Math.round(position.y / 20) * 20 }
    const outcome = insertCanvasElement(topology, kind, position, kind === 'bus' ? undefined : targetBusId ?? undefined)
    if (!outcome.ok) { onMessage(outcome.message); return }
    onDiagramChange(outcome.topology, { ...layout, node_positions: { ...layout.node_positions, ...outcome.positions } }, outcome.message)
    setSelectedElement(outcome.selectedElement)
    setPlacement(null)
    setMode('select')
  }

  function startPaletteDrag(event: PointerEvent<HTMLButtonElement>, kind: PlacementKind) {
    if (event.button !== 0) return
    event.preventDefault()
    event.currentTarget.focus({ preventScroll: true })
    event.currentTarget.setPointerCapture(event.pointerId)
    paletteDrag.current = { kind, x: event.clientX, y: event.clientY, moved: false, pointerId: event.pointerId, element: event.currentTarget }
  }

  function movePaletteDrag(event: PointerEvent<HTMLButtonElement>) {
    const drag = paletteDrag.current
    if (!drag || drag.pointerId !== event.pointerId) return
    if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 4) drag.moved = true
    if (drag.moved) setDragGhost({ kind: drag.kind, x: event.clientX, y: event.clientY })
  }

  function cancelPaletteDrag() {
    const drag = paletteDrag.current
    if (drag?.element.hasPointerCapture(drag.pointerId)) drag.element.releasePointerCapture(drag.pointerId)
    paletteDrag.current = null
    setDragGhost(null)
  }

  function endPaletteDrag(event: PointerEvent<HTMLButtonElement>) {
    const drag = paletteDrag.current
    if (!drag || drag.pointerId !== event.pointerId) return
    const hit = document.elementFromPoint(event.clientX, event.clientY)
    const inCanvas = !!hit && !!canvasRef.current?.contains(hit)
    const nodeId = hit?.closest<HTMLElement>('.react-flow__node')?.dataset.id
    cancelPaletteDrag()
    if (!drag.moved) { beginPlacement(drag.kind); return }
    if (!inCanvas) { onMessage('未放到画布内，没有新增元件。'); return }
    placeAtScreen(drag.kind, { x: event.clientX, y: event.clientY }, nodeId)
  }

  function handleCanvasKeyboard(event: globalThis.KeyboardEvent) {
    if (event.isComposing || event.defaultPrevented) return
    const target = event.target as Element
    if (target.closest('input, textarea, select, [contenteditable="true"], [role="textbox"]')) return
    if (event.ctrlKey || event.metaKey || event.altKey) {
      if ((event.ctrlKey || event.metaKey) && ['z', 'y'].includes(event.key.toLowerCase())) { setPlacement(null); setConnectionOrigin(null) }
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
      cancelPaletteDrag(); setPlacement(null); setConnectionOrigin(null); setSpacePan(false); setShowShortcuts(false)
      onMessage('已取消待放置或接线操作，网络未改变。')
      return
    }
    if (showShortcuts) return
    if (event.code === 'Space') {
      if (target.closest('button, [role="button"], a')) return
      event.preventDefault(); event.stopPropagation(); setSpacePan(true); return
    }
    if (event.key === 'Delete' || event.key === 'Backspace') {
      if (effectiveMode !== 'pan') { event.preventDefault(); event.stopPropagation(); deleteSelectedElement() }
      return
    }
    if (event.repeat || event.shiftKey) return
    const action = (Object.keys(shortcuts) as ShortcutAction[]).find(key => shortcuts[key] === event.key.toUpperCase())
    if (!action) return
    event.preventDefault()
    event.stopPropagation()
    if (action === 'select' || action === 'connect' || action === 'pan') chooseMode(action)
    else if (action === 'fit') { void flow?.fitView({ padding: 0.18, maxZoom: 1.1, duration: 150 }) }
    else beginPlacement(action)
  }

  function saveShortcuts() {
    const outcome = validateNetworkShortcuts(shortcutDraft)
    if (!outcome.ok) { setShortcutMessage(outcome.message); return }
    setShortcuts(outcome.shortcuts); setShortcutDraft(outcome.shortcuts)
    try { window.localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify({ schema_version: '1.0', bindings: outcome.shortcuts })); setShortcutMessage('快捷键已保存到本机浏览器。') }
    catch { setShortcutMessage('快捷键已应用；浏览器未允许本机保存，刷新后不会保留此次更改。') }
  }

  function changeEdges(changes: EdgeChange[]) {
    const removedWireIds = changes.filter(change => change.type === 'remove').map(change => entityId(change.id, 'wire')).filter((id): id is string => id !== null)
    if (removedWireIds.length) {
      onIdealConnectionsChange(idealConnections.filter(wire => !removedWireIds.includes(wire.id)), `已删除 ${removedWireIds.length} 条普通导线。`)
    }
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
    if (selectedEntity.kind === 'wire') { updateWire(selectedEntity.value.id, patch); return }
    if ((selectedEntity.kind === 'gfm' || selectedEntity.kind === 'grid') && typeof patch.bus_id === 'string') {
      reassignSource(selectedEntity.kind, selectedEntity.value.id, patch.bus_id)
      return
    }
    const next = clone(topology)
    const collection = selectedEntity.kind === 'bus' ? next.buses
      : selectedEntity.kind === 'line' ? next.lines
        : selectedEntity.kind === 'gfm' ? next.grid_forming_converters
          : next.infinite_buses
    const target = collection.find(item => item.id === selectedEntity.value?.id)
    if (!target) return
    if (selectedEntity.kind === 'line' && ('from_bus_id' in patch || 'to_bus_id' in patch)) {
      const line = next.lines.find(item => item.id === target.id)!
      const outcome = reconnectNetworkLine(topology, line.id, String(patch.from_bus_id ?? line.from_bus_id), String(patch.to_bus_id ?? line.to_bus_id))
      if (!outcome.ok) { onMessage(`${outcome.message}原线路保持不变。`); return }
      onTopologyChange(outcome.topology)
      return
    }
    if (selectedEntity.kind === 'grid' && typeof patch.bus_id === 'string' && selectedEntity.value.bus_id === next.reference_bus_id) {
      next.reference_bus_id = patch.bus_id
    }
    Object.assign(target, patch)
    onTopologyChange(next)
  }

  function commitName() {
    if (!selectedEntity?.value) return
    if (!draftName.trim()) { setDraftName(selectedEntity.value.name); onMessage('元件名称不能为空。'); return }
    if (draftName !== selectedEntity.value.name) updateSelected({ name: draftName.trim() })
  }

  function deleteSelectedElement() {
    if (selectedEntity?.kind === 'wire' && selectedEntity.value) {
      onIdealConnectionsChange(removeIdealConnection(idealConnections, selectedEntity.value.id), `已删除普通导线 ${selectedEntity.value.name}。`)
      setSelectedElement(null)
      return
    }
    const outcome = removeCanvasElement(topology, selectedElement)
    if (!outcome.ok) { onMessage(outcome.message); return }
    if (selectedEntity?.kind === 'bus' && selectedEntity.value) {
      const busId = selectedEntity.value.id
      const linked = topology.lines.filter(line => line.from_bus_id === busId || line.to_bus_id === busId).length
        + idealConnections.filter(wire => wire.from_bus_id === busId || wire.to_bus_id === busId).length
        + [...topology.grid_forming_converters, ...topology.infinite_buses, ...topology.loads].filter(item => item.bus_id === busId).length
      if (linked && !window.confirm(`删除母线“${selectedEntity.value.name}”将同时删除 ${linked} 个关联元件。是否继续？可通过撤销恢复。`)) return
    }
    const positions = { ...layout.node_positions }
    const widths = { ...layout.bus_widths }
    outcome.removedNodeIds.forEach(id => { delete positions[id] })
    outcome.removedNodeIds.forEach(id => { const busId = entityId(id, 'bus'); if (busId) delete widths[busId] })
    onDiagramChange(outcome.topology, { ...layout, node_positions: positions, ...(layout.bus_widths ? { bus_widths: widths } : {}) }, outcome.message)
    setSelectedElement(null)
    setConnectionOrigin(null)
  }

  const numberValue = (value: string, fallback: number) => {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : fallback
  }

  return <section ref={shellRef} tabIndex={0} className="network-graph-shell" data-testid="network-graph-editor" data-editor-version="palette-1.0" data-mode={effectiveMode} data-placement={placement ?? ''} onPointerDownCapture={event => {
    const target = event.target as Element
    if (target.classList.contains('react-flow__pane')) shellRef.current?.focus({ preventScroll: true })
  }}>
    <header className="network-graph-summary">
      <div><b>网络图</b><small>拖动只调整版面；重新接线会改变计算拓扑</small></div>
      <div className="graph-checks" data-testid="topology-summary">
        <span data-testid="wiring-status" className={summary.wiringValid ? 'passed' : 'failed'}>{summary.wiringValid ? '接线关系有效' : '接线关系需修正'}</span>
        <span data-testid="low-frequency-applicability" className={summary.lowFrequencyApplicable ? 'passed' : 'failed'}>{summary.lowFrequencyApplicable ? '低频模型输入条件满足' : '当前接线不适用低频模型'}</span>
        <span>{summary.componentCount} 个连通分量</span>
        <span>{summary.cycleRank} 个独立环路</span>
        <span>{topology.lines.filter(line => line.in_service !== false).length}/{topology.lines.length} 条线路投运</span>
        <span>{idealConnections.length} 条普通导线</span>
      </div>
    </header>
    <div className="network-editor-toolbar" role="toolbar" aria-label="网络画布操作">
      <div className="network-mode-group" aria-label="操作模式">
        <button type="button" data-testid="network-mode-select" className={effectiveMode === 'select' ? 'active' : ''} aria-pressed={effectiveMode === 'select'} onClick={() => chooseMode('select')} title={`选择、拖动元件（${shortcuts.select}）`}><MousePointer2 size={15}/>选择 <kbd>{shortcuts.select}</kbd></button>
        <button type="button" data-testid="network-mode-connect" className={effectiveMode === 'connect' ? 'active' : ''} aria-pressed={effectiveMode === 'connect'} onClick={() => chooseMode('connect')} title={`接线；也可拖动元件调整版面（${shortcuts.connect}）`}><Waypoints size={15}/>接线 <kbd>{shortcuts.connect}</kbd></button>
        <button type="button" data-testid="network-mode-pan" className={effectiveMode === 'pan' ? 'active' : ''} aria-pressed={effectiveMode === 'pan'} onClick={() => chooseMode('pan')} title={`平移视图（${shortcuts.pan}）；或按住空格临时平移`}><Hand size={15}/>平移 <kbd>{shortcuts.pan}</kbd></button>
      </div>
      <div className="network-connect-kind-group" role="group" aria-label="接线类型">
        <button type="button" data-testid="network-connect-kind-wire" className={connectKind === 'wire' ? 'active' : ''} aria-pressed={connectKind === 'wire'} onClick={() => beginPlacement('wire')}>普通导线</button>
        <button type="button" data-testid="network-connect-kind-line" className={connectKind === 'line' ? 'active' : ''} aria-pressed={connectKind === 'line'} onClick={() => beginPlacement('line')}><span data-testid="network-palette-line">阻抗线路 R–X</span></button>
      </div>
      <div className="network-view-tools">
        <button type="button" data-testid="network-fit" onClick={() => { void flow?.fitView({ padding: 0.18, maxZoom: 1.1, duration: 150 }) }} title="显示完整网络"><Maximize size={15}/>适配画布</button>
        <button type="button" data-testid="network-restore-display" onClick={restoreCanvasDisplay} title="重新绘制当前网络并适配视图；不修改元件、参数和布局坐标"><RotateCcw size={15}/>恢复显示</button>
        <button type="button" data-testid="network-zoom-in" onClick={() => { void flow?.zoomIn({ duration: 150 }) }} title="放大" aria-label="放大网络图"><ZoomIn size={15}/></button>
        <button type="button" data-testid="network-zoom-out" onClick={() => { void flow?.zoomOut({ duration: 150 }) }} title="缩小" aria-label="缩小网络图"><ZoomOut size={15}/></button>
        <label className="network-tool-toggle"><input type="checkbox" data-testid="network-snap" checked={snap} onChange={event => setSnap(event.target.checked)}/><span>网格吸附</span></label>
        <label className="network-tool-toggle"><input type="checkbox" data-testid="network-minimap" checked={showMiniMap} onChange={event => setShowMiniMap(event.target.checked)}/><span>缩略图</span></label>
        <button type="button" data-testid="network-delete-element" disabled={!selectedEntity?.value || effectiveMode === 'pan'} onClick={deleteSelectedElement} title="删除当前选中的元件（Delete）；关联删除前会确认"><Trash2 size={15}/>删除</button>
        <button type="button" data-testid="network-shortcut-settings" aria-expanded={showShortcuts} onClick={() => { setShortcutDraft({ ...shortcuts }); setShortcutMessage(''); setShowShortcuts(value => !value) }}><KeyboardIcon size={15}/>快捷键</button>
      </div>
    </div>
    <div className="network-connect-hint" data-testid="network-editor-hint" role="status">
      {placement ? <><MousePointer2 size={14}/><span>正在放置{placement === 'bus' ? '母线' : placement === 'gfm' ? '构网型变流器' : '等值电源'}：点击目标母线或画布空白处；Esc 取消。</span></>
        : effectiveMode === 'connect' ? <><Waypoints size={14}/><span>{connectKind === 'wire' ? '普通导线（无独立阻抗）' : '阻抗线路（独立 R/X 参数）'}：{connectionOrigin ? `已选起点 ${connectionOrigin}，请点击终点母线${connectKind === 'wire' ? '或电源' : ''}。` : connectKind === 'wire' ? '点击母线或电源，或拖动端子接线；图元位置不决定电气连接。' : '点击两条母线或拖动母线端子接线。'}</span>{connectionOrigin && <button type="button" data-testid="network-connect-cancel" onClick={() => { setConnectionOrigin(null); onMessage('已取消接线，未修改网络。') }}><X size={13}/>取消接线</button>}</>
          : effectiveMode === 'pan' ? <><Hand size={14}/><span>当前只平移视图；按 {shortcuts.select} 返回元件拖动。空格松开后结束临时平移。</span></>
            : <><MousePointer2 size={14}/><span>拖动元件调整位置；从元件库拖入，或选择元件后点击画布放置。按住空格平移。</span></>}
    </div>
    {showShortcuts && <div className="network-shortcut-panel" role="dialog" aria-label="网络编辑快捷键设置" data-testid="network-shortcut-panel">
      <div><b>快捷键设置</b><span>仅在网络编辑区域生效；输入框保留文字编辑。每项使用一个不重复的字母。</span></div>
      <div className="network-shortcut-fields">{(Object.keys(NETWORK_SHORTCUT_LABELS) as ShortcutAction[]).map(action => <label key={action}>{NETWORK_SHORTCUT_LABELS[action]}<input data-testid={`network-shortcut-input-${action}`} aria-label={`${NETWORK_SHORTCUT_LABELS[action]}快捷键`} maxLength={1} value={shortcutDraft[action]} onChange={event => setShortcutDraft(current => ({ ...current, [action]: event.target.value }))}/></label>)}</div>
      <p>固定操作：空格按住平移；Esc 取消；Delete 删除；Ctrl+Z 撤销；Ctrl+Y / Ctrl+Shift+Z 重做。</p>
      <div className="network-shortcut-actions"><button type="button" data-testid="network-shortcut-save" onClick={saveShortcuts}>保存设置</button><button type="button" data-testid="network-shortcut-reset" onClick={() => { setShortcuts({ ...DEFAULT_NETWORK_SHORTCUTS }); setShortcutDraft({ ...DEFAULT_NETWORK_SHORTCUTS }); try { window.localStorage.removeItem(LOCAL_STORAGE_KEY) } catch { /* Session defaults still apply. */ } setShortcutMessage('已恢复默认快捷键。') }}>恢复默认</button><button type="button" onClick={() => setShowShortcuts(false)}>关闭</button></div>
      {shortcutMessage && <p role="alert">{shortcutMessage}</p>}
    </div>}
    <div className="network-element-library" role="group" aria-label="电气元件库">
      <div className="network-library-title"><b>元件库</b><small>拖入或点击放置</small></div>
      {(['bus', 'gfm', 'grid', 'wire'] as const).map(kind => <button type="button" className={`network-palette-item ${placement === kind || (kind === 'wire' && effectiveMode === 'connect' && connectKind === 'wire') ? 'active' : ''}`} data-testid={`network-palette-${kind}`} key={kind} onPointerDown={event => startPaletteDrag(event, kind)} onPointerMove={movePaletteDrag} onPointerUp={endPaletteDrag} onPointerCancel={cancelPaletteDrag} onClick={event => { if (event.detail === 0) beginPlacement(kind) }} title={kind === 'wire' ? '普通导线无独立阻抗；选择端点建立电气连接' : '拖到母线接入，或拖到空白处放置；也可点击后选择位置'}>
        {kind === 'wire' ? <svg className="network-palette-line-symbol" viewBox="0 0 48 38" aria-hidden="true"><path d="M 3 24 H 45" fill="none" stroke="currentColor" strokeWidth="1.8"/><circle cx="3" cy="24" r="2" fill="currentColor"/><circle cx="45" cy="24" r="2" fill="currentColor"/></svg> : <ElectricalSymbol kind={kind} deviceId={`palette-${kind}`}/>}
        <span>{kind === 'bus' ? '母线' : kind === 'gfm' ? '构网型变流器' : kind === 'grid' ? '等值电源' : '接线'} <kbd>{kind === 'wire' ? shortcuts.connect : shortcuts[kind]}</kbd></span>
        <small>{kind === 'bus' ? '可调长汇接节点' : kind === 'gfm' ? 'VSM 低频模型' : kind === 'grid' ? '外部电网等值' : '普通导线 · 无独立阻抗'}</small>
      </button>)}
      <p>母线是汇接节点，长度仅影响版面；普通导线连接等电位母线，计算时合并电气节点，但保留原图元。需要独立阻抗时，在接线类型中选择“阻抗线路”。<br/>电源放到空白处会新建接入母线；拖动图元不改变电气连接，运行参数需按实际工况设置。</p>
    </div>
    {dragGhost && <div className="network-palette-ghost" style={{ left: dragGhost.x + 12, top: dragGhost.y + 12 }} aria-hidden="true">{dragGhost.kind === 'line' || dragGhost.kind === 'wire' ? <Waypoints size={24}/> : <ElectricalSymbol kind={dragGhost.kind} deviceId={`drag-${dragGhost.kind}`}/>}<span>释放以放置</span></div>}
    <div className="network-graph-stage">
    <div ref={canvasRef} className={`network-graph-canvas ${placement ? 'placing-element' : ''}`}>
      <ReactFlow
        key={canvasRevision}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onInit={setFlow}
        connectionMode={ConnectionMode.Loose}
        connectOnClick={false}
        nodesDraggable={effectiveMode !== 'pan' && !placement}
        nodesConnectable={effectiveMode === 'connect'}
        elementsSelectable={effectiveMode !== 'pan'}
        edgesReconnectable={effectiveMode === 'connect'}
        reconnectRadius={18}
        connectionRadius={28}
        snapToGrid={snap}
        snapGrid={[20, 20]}
        panOnDrag={effectiveMode === 'pan' ? true : [1, 2]}
        zoomOnDoubleClick={false}
        onNodesChange={updateNodePositions}
        onNodeDragStart={onLayoutCheckpoint}
        onConnect={connect}
        onReconnect={reconnect}
        onEdgesChange={changeEdges}
        onNodeClick={(event, node) => selectNode(node, { x: event.clientX, y: event.clientY })}
        onEdgeClick={(_, edge) => { if (effectiveMode !== 'pan') setSelectedElement(edge.id) }}
        onPaneClick={event => { if (effectiveMode === 'pan') return; if (placement) placeAtScreen(placement, { x: event.clientX, y: event.clientY }); else if (mode !== 'connect') setSelectedElement(null) }}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1.1 }}
        minZoom={0.35}
        maxZoom={1.8}
        deleteKeyCode={null}
        aria-label="电气网络建模画布"
      >
        <Background color="#d7e0e5" gap={20} size={1}/>
        {showMiniMap && <MiniMap position="bottom-left" style={{ width: 128, height: 90 }} pannable zoomable nodeColor={node => node.data.kind === 'gfm' ? '#169b9b' : node.data.kind === 'grid' ? '#dda53a' : '#334155'}/>}
      </ReactFlow>
    </div>
    <aside className="graph-inspector" data-testid="graph-inspector">
      <div className="network-editor-properties" data-testid="network-editor-properties">
      <div className="graph-inspector-title"><b>元件参数</b><small>点击图元或从列表选择</small></div>
      <label className="network-element-picker">选择元件
        <select aria-label="选择元件" data-testid="network-element-picker" value={selectedEntity?.value ? selectedElement ?? '' : ''} onChange={event => setSelectedElement(event.target.value || null)}>
          <option value="">请选择元件</option>
          <optgroup label="母线">{topology.buses.map(bus => <option key={bus.id} value={busNodeId(bus.id)}>{bus.name} · {bus.id}</option>)}</optgroup>
          <optgroup label="线路">{topology.lines.map(line => <option key={line.id} value={`line:${line.id}`}>{line.name} · {line.id}{line.in_service === false ? ' · 停运' : ''}</option>)}</optgroup>
          <optgroup label="普通导线">{idealConnections.map(wire => <option key={wire.id} value={`wire:${wire.id}`}>{wire.name} · {wire.id}</option>)}</optgroup>
          <optgroup label="构网型变流器">{topology.grid_forming_converters.map(gfm => <option key={gfm.id} value={gfmNodeId(gfm.id)}>{gfm.name} · {gfm.id}</option>)}</optgroup>
          <optgroup label="等值电源">{topology.infinite_buses.map(grid => <option key={grid.id} value={gridNodeId(grid.id)}>{grid.name} · {grid.id}</option>)}</optgroup>
        </select>
      </label>
      {!selectedEntity?.value && <div className="graph-inspector-empty"><Network size={22}/><p>选择母线、导线、阻抗线路或电源，查看与修改参数。</p></div>}
      {selectedEntity?.kind === 'bus' && selectedEntity.value && <div className="graph-fields">
        <small>母线 · {selectedEntity.value.id}</small>
        <label>名称<input value={draftName} onChange={event => setDraftName(event.target.value)} onBlur={commitName} onKeyDown={event => { if (event.key === 'Enter') event.currentTarget.blur() }}/></label>
        <label>标称电压 / V<input type="number" min="1" value={selectedEntity.value.nominal_voltage_v} onChange={event => updateSelected({ nominal_voltage_v: numberValue(event.target.value, selectedEntity.value!.nominal_voltage_v) })}/></label>
        <label>图形长度 / px<input data-testid="network-bus-width" type="number" min={MIN_BUS_WIDTH} max={MAX_BUS_WIDTH} step="1" value={diagramBusWidth(layout, selectedEntity.value.id)} onFocus={onLayoutCheckpoint} onChange={event => { const width = Number(event.target.value); if (event.target.value && Number.isFinite(width)) onLayoutChange(current => mergeDiagramBusWidth(current, selectedEntity.value!.id, width)) }}/></label>
        <p className="graph-parameter-note">长度仅调整单线图版面，不改变接线或分析参数；也可拖动母线右端的 ↔ 手柄。</p>
      </div>}
      {selectedEntity?.kind === 'wire' && selectedEntity.value && <div className="graph-fields">
        <small>普通导线 · {selectedEntity.value.id}</small>
        <label>名称<input value={draftName} onChange={event => setDraftName(event.target.value)} onBlur={commitName} onKeyDown={event => { if (event.key === 'Enter') event.currentTarget.blur() }}/></label>
        <label>首端<select value={selectedEntity.value.from_bus_id} onChange={event => updateSelected({ from_bus_id: event.target.value })}>{topology.buses.map(bus => <option key={bus.id}>{bus.id}</option>)}</select></label>
        <label>末端<select value={selectedEntity.value.to_bus_id} onChange={event => updateSelected({ to_bus_id: event.target.value })}>{topology.buses.map(bus => <option key={bus.id}>{bus.id}</option>)}</select></label>
        <p className="graph-parameter-note">普通导线没有独立 R/X；计算时将同电压等级母线合并为等电位节点。模型不支持的源冲突或阻抗线路自环会明确提示，原稿可保存。</p>
        <button type="button" data-testid="network-wire-delete" className="network-delete-line" onClick={deleteSelectedElement}><Trash2 size={14}/>删除导线</button>
      </div>}
      {selectedEntity?.kind === 'line' && selectedEntity.value && <div className="graph-fields">
        <small>线路 · {selectedEntity.value.id}</small>
        <label>名称<input value={draftName} onChange={event => setDraftName(event.target.value)} onBlur={commitName} onKeyDown={event => { if (event.key === 'Enter') event.currentTarget.blur() }}/></label>
        <label>首端<select value={selectedEntity.value.from_bus_id} onChange={event => updateSelected({ from_bus_id: event.target.value })}>{topology.buses.map(bus => <option key={bus.id}>{bus.id}</option>)}</select></label>
        <label>末端<select value={selectedEntity.value.to_bus_id} onChange={event => updateSelected({ to_bus_id: event.target.value })}>{topology.buses.map(bus => <option key={bus.id}>{bus.id}</option>)}</select></label>
        <div className="graph-field-pair">
          <label>R / p.u.<input type="number" min="0" step="0.01" value={selectedEntity.value.resistance_pu} onChange={event => updateSelected({ resistance_pu: numberValue(event.target.value, selectedEntity.value!.resistance_pu) })}/></label>
          <label>X / p.u.<input type="number" min="0.0001" step="0.01" value={selectedEntity.value.reactance_pu} onChange={event => updateSelected({ reactance_pu: numberValue(event.target.value, selectedEntity.value!.reactance_pu) })}/></label>
        </div>
        <label className="graph-checkbox"><input data-testid="network-line-in-service" type="checkbox" checked={selectedEntity.value.in_service !== false} onChange={event => updateSelected({ in_service: event.target.checked })}/><span>{selectedEntity.value.in_service === false ? '线路停运' : '线路投运'}</span></label>
        <p className="graph-parameter-note">投退作用于整条线路，不代表独立断路器操作。重接仅接受同电压等级的不同母线。</p>
        <button type="button" data-testid="network-line-delete" className="network-delete-line" onClick={deleteSelectedElement}><Trash2 size={14}/>删除线路</button>
      </div>}
      {selectedEntity?.kind === 'gfm' && selectedEntity.value && <div className="graph-fields">
        <small>构网型变流器 · {selectedEntity.value.id}</small>
        <label>名称<input value={draftName} onChange={event => setDraftName(event.target.value)} onBlur={commitName} onKeyDown={event => { if (event.key === 'Enter') event.currentTarget.blur() }}/></label>
        <label>接入母线<select value={selectedEntity.value.bus_id} onChange={event => updateSelected({ bus_id: event.target.value })}>{topology.buses.filter(bus => bus.id === selectedEntity.value!.bus_id || (!topology.infinite_buses.some(grid => grid.bus_id === bus.id) && !topology.grid_forming_converters.some(other => other.id !== selectedEntity.value!.id && other.bus_id === bus.id))).map(bus => <option key={bus.id}>{bus.id}</option>)}</select></label>
        <div className="graph-field-pair">
          <label>惯量 M / s<input type="number" min="0.001" step="0.1" value={selectedEntity.value.virtual_inertia_s} onChange={event => updateSelected({ virtual_inertia_s: numberValue(event.target.value, selectedEntity.value!.virtual_inertia_s) })}/></label>
          <label>阻尼 D / p.u.<input type="number" min="0.0001" step="0.05" value={selectedEntity.value.damping_coefficient_pu} onChange={event => updateSelected({ damping_coefficient_pu: numberValue(event.target.value, selectedEntity.value!.damping_coefficient_pu) })}/></label>
        </div>
        <label>有功测量 Tₚ / s<input type="number" min="0.001" step="0.01" value={selectedEntity.value.active_power_measurement_time_constant_s} onChange={event => updateSelected({ active_power_measurement_time_constant_s: numberValue(event.target.value, selectedEntity.value!.active_power_measurement_time_constant_s) })}/></label>
      </div>}
      {selectedEntity?.kind === 'grid' && selectedEntity.value && <div className="graph-fields">
        <small>等值电源 · {selectedEntity.value.id}</small>
        <label>名称<input value={draftName} onChange={event => setDraftName(event.target.value)} onBlur={commitName} onKeyDown={event => { if (event.key === 'Enter') event.currentTarget.blur() }}/></label>
        <label>接入母线<select value={selectedEntity.value.bus_id} onChange={event => updateSelected({ bus_id: event.target.value })}>{topology.buses.filter(bus => bus.id === selectedEntity.value!.bus_id || (!topology.grid_forming_converters.some(gfm => gfm.bus_id === bus.id) && !topology.infinite_buses.some(other => other.id !== selectedEntity.value!.id && other.bus_id === bus.id))).map(bus => <option key={bus.id}>{bus.id}</option>)}</select></label>
        <label>电压 / p.u.<input type="number" min="0.5" max="1.5" step="0.01" value={selectedEntity.value.voltage_magnitude_pu ?? 1} onChange={event => updateSelected({ voltage_magnitude_pu: numberValue(event.target.value, selectedEntity.value!.voltage_magnitude_pu ?? 1) })}/></label>
      </div>}
      </div>
    </aside>
    </div>
    {summary.wiringIssues.map(issue => <p className="graph-diagnostic" key={issue}><Zap size={14}/><span>接线检查：{issue}</span></p>)}
    {summary.lowFrequencyIssues.map(issue => <p className="graph-diagnostic" key={issue}><Zap size={14}/><span>低频模型适用性：{issue}</span></p>)}
    <p className="scope-note">以上仅预检接线关系与模型范围，不判断网络是否带电；参数与数值条件由分析服务进一步校验。</p>
  </section>
}
