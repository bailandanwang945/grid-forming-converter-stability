export type DiagramPosition = { x: number; y: number }

export type DiagramLayout = {
  schema_version: 'gfm-network-diagram-layout/1.0' | 'gfm-network-diagram-layout/1.1'
  node_positions: Record<string, DiagramPosition>
  bus_widths?: Record<string, number>
}

export const DEFAULT_BUS_WIDTH = 176
export const MIN_BUS_WIDTH = 128
export const MAX_BUS_WIDTH = 1200

export function diagramBusWidth(layout: DiagramLayout, busId: string): number {
  const widths = layout.bus_widths
  const width = widths && Object.prototype.hasOwnProperty.call(widths, busId) ? widths[busId] : undefined
  return typeof width === 'number' && Number.isFinite(width) && width >= MIN_BUS_WIDTH && width <= MAX_BUS_WIDTH ? width : DEFAULT_BUS_WIDTH
}

/** Width changes affect only the drawing, and merge against the newest layout. */
export function mergeDiagramBusWidth(layout: DiagramLayout, busId: string, width: number): DiagramLayout {
  if (!Number.isFinite(width)) return layout
  const nextWidth = Math.min(MAX_BUS_WIDTH, Math.max(MIN_BUS_WIDTH, Math.round(width)))
  if (diagramBusWidth(layout, busId) === nextWidth) return layout
  return { ...layout, schema_version: 'gfm-network-diagram-layout/1.1', bus_widths: { ...layout.bus_widths, [busId]: nextWidth } }
}

export type DiagramPositionChange = { id: string; position?: DiagramPosition }
export type DiagramNodeDimensions = Record<string, { width: number; height: number }>
export type DiagramDimensionChange = { id: string; dimensions?: { width: number; height: number } }

export function isFiniteDiagramPosition(position: DiagramPosition | undefined): position is DiagramPosition {
  return position != null && Number.isFinite(position.x) && Number.isFinite(position.y)
}

/** Merge only moved nodes into the latest layout, never a stale full-node snapshot. */
export function mergeDiagramPositions(
  layout: DiagramLayout,
  changes: readonly DiagramPositionChange[],
  allowedNodeIds: ReadonlySet<string>,
): DiagramLayout {
  let nextPositions: DiagramLayout['node_positions'] | undefined
  for (const { id, position } of changes) {
    // Drag-start/end notifications may have no position. A removed node can
    // also have an in-flight notification; neither should recreate it.
    if (!allowedNodeIds.has(id) || !isFiniteDiagramPosition(position)) continue
    const previous = (nextPositions ?? layout.node_positions)[id]
    if (previous?.x === position.x && previous?.y === position.y) continue
    nextPositions ??= { ...layout.node_positions }
    nextPositions[id] = { x: position.x, y: position.y }
  }
  return nextPositions ? { ...layout, node_positions: nextPositions } : layout
}

/** Keep real measured sizes across controlled-node rebuilds; not part of case data. */
export function mergeDiagramDimensions(
  measured: DiagramNodeDimensions,
  changes: readonly DiagramDimensionChange[],
  allowedNodeIds: ReadonlySet<string>,
): DiagramNodeDimensions {
  let next: DiagramNodeDimensions | undefined
  for (const { id, dimensions } of changes) {
    if (!allowedNodeIds.has(id) || !dimensions
      || !Number.isFinite(dimensions.width) || dimensions.width <= 0
      || !Number.isFinite(dimensions.height) || dimensions.height <= 0) continue
    const previous = (next ?? measured)[id]
    if (previous?.width === dimensions.width && previous?.height === dimensions.height) continue
    next ??= { ...measured }
    next[id] = { width: dimensions.width, height: dimensions.height }
  }
  return next ?? measured
}
