import type { IdealConnection } from './networkIdealConnections'

export type ConnectionInputBinding = {
  sourceTopologyId: string
  sourceTopologyName: string
  originalBusIds: string[]
  idealConnections: IdealConnection[]
  busMap: Record<string, string>
}

const escapeHtml = (value: string) => value.replace(/[&<>"']/g, character => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
})[character]!)

/** The backend report remains about the compiled model; retain its source wiring. */
export function appendConnectionInputBinding(html: string, binding: ConnectionInputBinding | null): string {
  if (!binding?.idealConnections.length) return html
  const rows = binding.originalBusIds.map(id => `<tr><td>${escapeHtml(id)}</td><td>${escapeHtml(binding.busMap[id] ?? id)}</td></tr>`).join('')
  const wires = binding.idealConnections.map(wire => `<li>${escapeHtml(wire.name)}（${escapeHtml(wire.id)}）：${escapeHtml(wire.from_bus_id)} — ${escapeHtml(wire.to_bus_id)}</li>`).join('')
  const section = `<section class="connection-input-binding" style="margin:1rem 0;padding:1rem;border:1px solid #dce5eb;break-inside:avoid"><h2>原始接线与计算节点</h2><p>原始案例：${escapeHtml(binding.sourceTopologyName)}（${escapeHtml(binding.sourceTopologyId)}）。普通导线按理想等电位连接处理，不以零电抗或极小电抗线路代替。下文的分析针对合并后的计算网络，不是对任意工程主接线的通用分析。</p><ul>${wires}</ul><table style="border-collapse:collapse;width:100%"><thead><tr><th>原始母线编号</th><th>计算节点编号</th></tr></thead><tbody>${rows}</tbody></table><p>该转换未增加开关动作、变压器、潮流或短路计算能力；原分析方法的假设与适用范围仍然有效。</p></section>`
  return /<body\b[^>]*>/i.test(html) ? html.replace(/<body\b[^>]*>/i, opening => opening + section) : section + html
}
