type ElectricalSymbolProps = { kind: 'bus' | 'gfm' | 'grid'; deviceId: string; busSymbolWidth?: number }

/** Simplified single-line symbols; drawings do not add unsupported electrical models. */
export default function ElectricalSymbol({ kind, deviceId, busSymbolWidth = 160 }: ElectricalSymbolProps) {
  if (kind === 'bus') return <svg className="electrical-symbol bus-symbol" viewBox={`0 0 ${busSymbolWidth} 44`} style={{ width: busSymbolWidth }} role="img" aria-label="母线单线图符号" data-testid={`network-symbol-${deviceId}`}>
    <title>母线：横向粗线及连接端子</title>
    <g fill="none" stroke="currentColor" strokeLinecap="square">
      <path d={`M 0 22 H ${busSymbolWidth}`} strokeWidth="4"/>
      <path d={`M ${busSymbolWidth / 2} 0 V 44`} strokeWidth="1.8"/>
    </g>
    <circle cx={busSymbolWidth / 2} cy="22" r="3.5" fill="currentColor"/>
  </svg>
  if (kind === 'gfm') return <svg className="electrical-symbol converter-symbol" viewBox="0 0 84 66" role="img" aria-label="构网型变流器单线图符号" data-testid={`network-symbol-${deviceId}`}>
    <title>构网型变流器：直流—交流变换器简图，不表示同步发电机</title>
    <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="17" y="3" width="50" height="48" rx="1"/>
      <path d="M 17 51 L 67 3 M 26 14 H 44 M 26 19 H 31 M 35 19 H 40 M 44 19 H 47"/>
      <path d="M 43 35 C 47 25 51 25 55 35 S 63 45 64 35 M 42 51 V 66"/>
    </g>
  </svg>
  return <svg className="electrical-symbol grid-symbol" viewBox="0 0 84 66" role="img" aria-label="外部电网等值交流电压源符号" data-testid={`network-symbol-${deviceId}`}>
    <title>外部电网：无限大母线等值交流电压源</title>
    <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M 42 0 V 10"/>
      <circle cx="42" cy="33" r="23"/>
      <path d="M 27 33 C 32 20 37 20 42 33 S 52 46 57 33"/>
    </g>
  </svg>
}
