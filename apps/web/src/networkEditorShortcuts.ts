/** Pure shortcut configuration: no browser storage, DOM or external dependencies. */
export type ShortcutAction = 'select' | 'connect' | 'pan' | 'bus' | 'gfm' | 'grid' | 'fit'
export type NetworkShortcuts = Record<ShortcutAction, string>

export const LOCAL_STORAGE_KEY = 'gfm-network-editor-shortcuts/1.0'

export const DEFAULT_NETWORK_SHORTCUTS: Readonly<NetworkShortcuts> = Object.freeze({
  select: 'V', connect: 'C', pan: 'H', bus: 'B', gfm: 'G', grid: 'E', fit: 'F',
})

export const NETWORK_SHORTCUT_LABELS: Readonly<Record<ShortcutAction, string>> = Object.freeze({
  select: '选择', connect: '接线', pan: '平移', bus: '放置母线',
  gfm: '放置构网型变流器', grid: '放置等值电源', fit: '适配画布',
})

const actions = Object.keys(DEFAULT_NETWORK_SHORTCUTS) as ShortcutAction[]

type ShortcutValidation =
  | { ok: true; shortcuts: NetworkShortcuts }
  | { ok: false; message: string }

/** Require exactly seven own fields, each containing one ASCII letter.
 * Whitespace, inherited fields, accessors, symbols and extra fields are rejected.
 * Success returns a new uppercase record and never modifies the input.
 */
export function validateNetworkShortcuts(value: unknown): ShortcutValidation {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return { ok: false, message: '快捷键配置必须包含全部七个动作。' }
  }
  const keys = Reflect.ownKeys(value)
  if (keys.length !== actions.length || keys.some(key => typeof key !== 'string' || !actions.includes(key as ShortcutAction))) {
    return { ok: false, message: '快捷键配置必须完整且不能包含额外字段。' }
  }
  const shortcuts = {} as NetworkShortcuts
  const assigned = new Map<string, ShortcutAction>()
  for (const action of actions) {
    const descriptor = Object.getOwnPropertyDescriptor(value, action)
    const key = descriptor && 'value' in descriptor ? descriptor.value : undefined
    if (typeof key !== 'string' || !/^[A-Za-z]$/.test(key)) {
      return { ok: false, message: `「${NETWORK_SHORTCUT_LABELS[action]}」的快捷键必须是单个英文字母。` }
    }
    const normalized = key.toUpperCase()
    const conflict = assigned.get(normalized)
    if (conflict) {
      return { ok: false, message: `「${NETWORK_SHORTCUT_LABELS[action]}」和「${NETWORK_SHORTCUT_LABELS[conflict]}」不能共用快捷键 ${normalized}。` }
    }
    assigned.set(normalized, action)
    shortcuts[action] = normalized
  }
  return { ok: true, shortcuts }
}

/** Parse only a strict v1.0 {schema_version, bindings} envelope.
 * Missing/invalid storage always returns an independent default copy.
 */
export function parseStoredNetworkShortcuts(raw: string | null): NetworkShortcuts {
  try {
    if (typeof raw === 'string' && raw.length > 0) {
      const stored: unknown = JSON.parse(raw)
      if (typeof stored === 'object' && stored !== null && !Array.isArray(stored)) {
        const envelope = stored as Record<string, unknown>
        const keys = Object.keys(envelope)
        if (keys.length === 2 && keys.includes('schema_version') && keys.includes('bindings')
          && envelope.schema_version === '1.0') {
          const result = validateNetworkShortcuts(envelope.bindings)
          if (result.ok) return result.shortcuts
        }
      }
    }
  } catch {
    // Invalid JSON is an expected recoverable storage condition.
  }
  return { ...DEFAULT_NETWORK_SHORTCUTS }
}
