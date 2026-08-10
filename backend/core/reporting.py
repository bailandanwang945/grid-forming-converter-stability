"""Printable, dependency-free research reports for portable analyses."""

from __future__ import annotations

from html import escape
from math import isfinite, log10
from typing import Iterable


def _number(value: float, digits: int = 6) -> str:
    return f"{value:.{digits}g}"


def _coverage_bands(frequencies: list[float], coverage: list[str]) -> list[tuple[float, float, int]]:
    bands: list[tuple[float, float, int]] = []
    start: int | None = None
    for index, status in enumerate([*coverage, "end"]):
        if status == "uncovered" and start is None:
            start = index
        elif status != "uncovered" and start is not None:
            end = index - 1
            bands.append((frequencies[start], frequencies[end], end - start + 1))
            start = None
    return bands


def _svg_chart(
    frequencies: list[float],
    series: Iterable[tuple[str, list[float | None], str]],
    title: str,
    y_label: str,
) -> str:
    width, height = 820, 270
    left, right, top, bottom = 68, 20, 38, 45
    plot_width = width - left - right
    plot_height = height - top - bottom
    all_values = [
        float(value)
        for _, values, _ in series
        for value in values
        if value is not None and isfinite(float(value))
    ]
    minimum = min([0.0, *all_values])
    maximum = max([0.0, *all_values])
    if maximum == minimum:
        maximum = minimum + 1.0
    padding = 0.06 * (maximum - minimum)
    minimum -= padding
    maximum += padding
    x_min, x_max = log10(frequencies[0]), log10(frequencies[-1])

    def x_position(value: float) -> float:
        return left + (log10(value) - x_min) / (x_max - x_min) * plot_width

    def y_position(value: float) -> float:
        return top + (maximum - value) / (maximum - minimum) * plot_height

    paths: list[str] = []
    legends: list[str] = []
    for series_index, (name, values, color) in enumerate(series):
        segments: list[list[str]] = []
        current: list[str] = []
        for frequency, value in zip(frequencies, values, strict=True):
            if value is None or not isfinite(float(value)):
                if current:
                    segments.append(current)
                    current = []
                continue
            current.append(f"{x_position(frequency):.2f},{y_position(float(value)):.2f}")
        if current:
            segments.append(current)
        paths.extend(
            f'<polyline points="{" ".join(segment)}" fill="none" stroke="{color}" '
            'stroke-width="1.8" stroke-linejoin="round"/>'
            for segment in segments
        )
        legend_x = left + series_index * 180
        legends.append(
            f'<line x1="{legend_x}" y1="20" x2="{legend_x + 24}" y2="20" '
            f'stroke="{color}" stroke-width="2.5"/><text x="{legend_x + 30}" y="24" '
            f'font-size="11" fill="#52616d">{escape(name)}</text>'
        )

    zero_y = y_position(0.0)
    ticks = []
    for exponent in range(int(x_min), int(x_max) + 1):
        x_value = x_position(10**exponent)
        ticks.append(
            f'<line x1="{x_value:.2f}" y1="{top}" x2="{x_value:.2f}" y2="{height-bottom}" '
            'stroke="#edf0f2"/><text x="{:.2f}" y="{}" text-anchor="middle" '
            'font-size="10" fill="#71808c">10^{}</text>'.format(
                x_value, height - 23, exponent
            )
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">'
        f'<text x="{left}" y="13" font-size="13" font-weight="700" fill="#263641">{escape(title)}</text>'
        + "".join(legends)
        + "".join(ticks)
        + f'<line x1="{left}" y1="{zero_y:.2f}" x2="{width-right}" y2="{zero_y:.2f}" '
        'stroke="#c44b4b" stroke-dasharray="5 4"/>'
        + "".join(paths)
        + f'<text x="16" y="{top + plot_height/2:.2f}" transform="rotate(-90 16 {top + plot_height/2:.2f})" '
        f'font-size="10" fill="#71808c">{escape(y_label)}</text>'
        + f'<text x="{left + plot_width/2:.2f}" y="{height-4}" text-anchor="middle" '
        'font-size="10" fill="#71808c">频率 / Hz（对数坐标）</text></svg>'
    )


def render_fig8_report(result: dict) -> str:
    """Render one self-contained HTML report suitable for browser PDF printing."""

    summary = result["summary"]
    scan = result["frequency_scan"]
    provenance = result["provenance"]
    bands = _coverage_bands(scan["frequencies_hz"], scan["coverage"])
    band_rows = "".join(
        f"<tr><td>{index + 1}</td><td>{_number(start)}</td><td>{_number(end)}</td><td>{count}</td></tr>"
        for index, (start, end, count) in enumerate(bands)
    ) or '<tr><td colspan="4">当前 1000 点频率网格没有“增益与相位同时未覆盖”的频点。</td></tr>'
    gain_chart = _svg_chart(
        scan["frequencies_hz"],
        [("小增益裕度", scan["gain_margin"], "#167d70")],
        "小增益条件裕度",
        "σmin(Ynet) − σmax(Yc)",
    )
    phase_chart = _svg_chart(
        scan["frequencies_hz"],
        [
            ("上相位裕度", scan["upper_phase_margin"], "#3c6fa3"),
            ("下相位裕度", scan["lower_phase_margin"], "#b77824"),
        ],
        "严格扇形相位裕度",
        "相位裕度 / rad",
    )
    stable_text = "参考稳定" if summary["closed_loop_reference"] == "stable" else "参考失稳"
    counts = summary["screening_counts"]
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>构网型变流器稳定性分析报告</title>
<style>
@page {{ size: A4; margin: 15mm; }}
body {{ font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; color:#202b33; margin:0; font-size:12px; line-height:1.65; }}
h1 {{ font-size:22px; margin:0 0 4px; }} h2 {{ font-size:15px; margin:22px 0 9px; border-left:4px solid #176e64; padding-left:9px; }}
.sub {{ color:#697884; }} .notice {{ padding:10px 13px; background:#fff5df; border:1px solid #edd7a8; border-radius:7px; }}
.grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin:14px 0; }}
.metric {{ padding:10px; background:#f3f7f7; border-radius:7px; }} .metric b {{ display:block; margin-top:4px; font-size:14px; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:6px 8px; border:1px solid #dce3e7; text-align:left; }} th {{ background:#f2f5f6; }}
svg {{ width:100%; height:auto; border:1px solid #e0e6e9; border-radius:7px; margin:5px 0 10px; }}
dl {{ display:grid; grid-template-columns:150px 1fr; }} dt,dd {{ margin:0; padding:4px 0; border-bottom:1px solid #edf0f2; }} dt {{ color:#687884; }}
.footer {{ margin-top:24px; padding-top:10px; border-top:1px solid #dfe5e8; color:#75838d; font-size:10px; }}
@media print {{ .print-tip {{ display:none; }} }}
</style></head><body>
<h1>构网型变流器稳定性分析报告</h1>
<div class="sub">论文 Fig. 8 固定作者夹具 · 便携式 Python 复算 · {escape(result['run_id'])}</div>
<p class="print-tip"><button onclick="window.print()">打印或另存为 PDF</button></p>
<div class="grid">
  <div class="metric">闭环特征根参考<b>{stable_text}</b></div>
  <div class="metric">主导极点<b>{summary['dominant_pole_hz']['real']:+.6f} ± j{summary['dominant_pole_hz']['imag']:.6f} Hz</b></div>
  <div class="metric">有限网格未覆盖<b>{summary['uncovered_points']} / {summary['frequency_points']}</b></div>
  <div class="metric">论文/工作簿振荡频率<b>{summary['paper_reported_oscillation_hz']:.1f} / {summary['reproduced_dominant_oscillation_hz']:.6f} Hz</b></div>
</div>
<div class="notice"><b>结论边界：</b>{escape(provenance['interpretation'])} 论文正文的 1.2 Hz 与作者工作簿模型的 0.578113 Hz 差异尚未闭合。</div>
<h2>频率筛查结果</h2>
<p>小增益：{counts['gain']['pass']} 通过、{counts['gain']['fail']} 未通过、{counts['gain']['indeterminate']} 待定；
严格扇形相位：{counts['phase']['pass']} 通过、{counts['phase']['fail']} 未通过、{counts['phase']['indeterminate']} 待定。</p>
{gain_chart}{phase_chart}
<h2>离散未覆盖频带</h2>
<table><thead><tr><th>序号</th><th>起点 / Hz</th><th>终点 / Hz</th><th>频点数</th></tr></thead><tbody>{band_rows}</tbody></table>
<h2>来源与复现信息</h2>
<dl>
<dt>固定夹具</dt><dd>{escape(provenance['fixture_id'])}</dd>
<dt>作者代码</dt><dd>{escape(provenance['author_tag'])} · {escape(provenance['author_commit'])}</dd>
<dt>原工作簿 SHA-256</dt><dd>{escape(provenance['source_workbook_sha256'])}</dd>
<dt>夹具导出环境</dt><dd>MATLAB {escape(provenance['matlab_release_used_to_export_fixture'])}</dd>
<dt>便携计算方法</dt><dd>{escape(provenance['python_method'])}</dd>
<dt>定理状态</dt><dd>{escape(summary['theorem_status'])}</dd>
</dl>
<div class="footer">本报告由本地分析平台生成。它记录有限网格筛查和闭环特征根参考结果，不构成对论文全频定理的独立证明。</div>
</body></html>"""


def _linear_svg_chart(
    x_values: list[float],
    series: Iterable[tuple[str, list[float], str]],
    title: str,
    x_label: str,
    y_label: str,
) -> str:
    """Render a compact linear-axis chart without a browser-side dependency."""

    width, height = 820, 300
    left, right, top, bottom = 72, 22, 54, 48
    plot_width = width - left - right
    plot_height = height - top - bottom
    prepared = list(series)
    finite_values = [
        float(value)
        for _, values, _ in prepared
        for value in values
        if isfinite(float(value))
    ]
    if not x_values or not finite_values:
        return '<p class="notice">线性时域响应没有可绘制的有限数值。</p>'

    x_min, x_max = min(x_values), max(x_values)
    if x_max == x_min:
        x_max = x_min + 1.0
    y_min, y_max = min([0.0, *finite_values]), max([0.0, *finite_values])
    if y_max == y_min:
        y_max = y_min + 1.0
    y_padding = 0.08 * (y_max - y_min)
    y_min -= y_padding
    y_max += y_padding

    def x_position(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * plot_width

    def y_position(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_height

    paths: list[str] = []
    legends: list[str] = []
    for index, (name, values, color) in enumerate(prepared):
        points = [
            f"{x_position(x):.2f},{y_position(float(y)):.2f}"
            for x, y in zip(x_values, values, strict=True)
            if isfinite(float(y))
        ]
        if points:
            paths.append(
                f'<polyline points="{" ".join(points)}" fill="none" '
                f'stroke="{color}" stroke-width="1.7" stroke-linejoin="round"/>'
            )
        column = index % 3
        row = index // 3
        legend_x = left + column * 242
        legend_y = 22 + row * 16
        legends.append(
            f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 21}" '
            f'y2="{legend_y}" stroke="{color}" stroke-width="2.4"/>'
            f'<text x="{legend_x + 27}" y="{legend_y + 4}" font-size="9" '
            f'fill="#52616d">{escape(name)}</text>'
        )

    grid: list[str] = []
    for index in range(6):
        fraction = index / 5
        x_value = x_min + fraction * (x_max - x_min)
        x_pixel = x_position(x_value)
        grid.append(
            f'<line x1="{x_pixel:.2f}" y1="{top}" x2="{x_pixel:.2f}" '
            f'y2="{height-bottom}" stroke="#edf0f2"/>'
            f'<text x="{x_pixel:.2f}" y="{height-25}" text-anchor="middle" '
            f'font-size="9" fill="#71808c">{_number(x_value, 4)}</text>'
        )
    zero_y = y_position(0.0)
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">'
        f'<text x="{left}" y="13" font-size="13" font-weight="700" '
        f'fill="#263641">{escape(title)}</text>'
        + "".join(legends)
        + "".join(grid)
        + f'<line x1="{left}" y1="{zero_y:.2f}" x2="{width-right}" '
        f'y2="{zero_y:.2f}" stroke="#aeb8bf" stroke-dasharray="4 4"/>'
        + "".join(paths)
        + f'<text x="16" y="{top + plot_height/2:.2f}" '
        f'transform="rotate(-90 16 {top + plot_height/2:.2f})" font-size="10" '
        f'fill="#71808c">{escape(y_label)}</text>'
        + f'<text x="{left + plot_width/2:.2f}" y="{height-4}" '
        f'text-anchor="middle" font-size="10" fill="#71808c">{escape(x_label)}</text>'
        + "</svg>"
    )


def _matrix_table(matrix: list[list[float]], labels: list[str]) -> str:
    header = "".join(f"<th>{escape(label)}</th>" for label in labels)
    rows = "".join(
        "<tr>"
        f"<th>{escape(labels[row_index])}</th>"
        + "".join(f"<td>{_number(float(value))}</td>" for value in row)
        + "</tr>"
        for row_index, row in enumerate(matrix)
    )
    return f"<table><thead><tr><th>变流器</th>{header}</tr></thead><tbody>{rows}</tbody></table>"


def render_reduced_order_report(result: dict) -> str:
    """Render a complete, printable report for one reduced-order analysis."""

    topology = result["input_topology"]
    analysis = result["result"]
    scope = result["model_scope"]
    provenance = result["provenance"]
    response = analysis["time_response"]
    palette = (
        "#176e64",
        "#3c6fa3",
        "#b77824",
        "#9a4d67",
        "#6754a3",
        "#52763a",
        "#a64a3f",
        "#397b86",
        "#716458",
    )
    state_columns = list(zip(*response["states"], strict=True))
    time_chart = _linear_svg_chart(
        response["time_s"],
        [
            (label, list(values), palette[index % len(palette)])
            for index, (label, values) in enumerate(
                zip(response["state_labels"], state_columns, strict=True)
            )
        ],
        "线性零输入响应（初始条件扰动）",
        "时间 / s",
        "状态增量（各量纲见图例）",
    )

    bus_rows = "".join(
        f"<tr><td>{escape(bus['id'])}</td><td>{escape(bus['name'])}</td>"
        f"<td>{_number(bus['nominal_voltage_v'])}</td></tr>"
        for bus in topology["buses"]
    )
    line_rows = "".join(
        f"<tr><td>{escape(line['id'])}</td><td>{escape(line['from_bus_id'])}</td>"
        f"<td>{escape(line['to_bus_id'])}</td><td>{_number(line['resistance_pu'])}</td>"
        f"<td>{_number(line['reactance_pu'])}</td>"
        f"<td>{_number(line['shunt_susceptance_pu'])}</td></tr>"
        for line in topology["lines"]
    ) or '<tr><td colspan="6">无交流线路。</td></tr>'
    converter_rows = "".join(
        f"<tr><td>{escape(item['id'])}</td><td>{escape(item['bus_id'])}</td>"
        f"<td>{escape(item['control_mode'])}</td>"
        f"<td>{_number(item['virtual_inertia_s'])}</td>"
        f"<td>{_number(item['damping_coefficient_pu'])}</td>"
        f"<td>{_number(item['active_power_measurement_time_constant_s'])}</td>"
        f"<td>{_number(item['active_power_setpoint_pu'])}</td></tr>"
        for item in topology["grid_forming_converters"]
    )
    source_rows = "".join(
        f"<tr><td>{escape(item['id'])}</td><td>{escape(item['bus_id'])}</td>"
        f"<td>{_number(item['voltage_magnitude_pu'])}</td>"
        f"<td>{_number(item['voltage_angle_deg'])}</td></tr>"
        for item in topology["infinite_buses"]
    )
    load_rows = "".join(
        f"<tr><td>{escape(item['id'])}</td><td>{escape(item['bus_id'])}</td>"
        f"<td>{escape(item['load_model'])}</td><td>{_number(item['active_power_pu'])}</td>"
        f"<td>{_number(item['reactive_power_pu'])}</td></tr>"
        for item in topology["loads"]
    ) or '<tr><td colspan="5">无静态负荷。</td></tr>'
    pole_rows = "".join(
        f"<tr><td>{index + 1}</td><td>{pole['real_per_s']:+.7g}</td>"
        f"<td>{pole['imag_per_s']:+.7g}</td><td>{pole['real_hz']:+.7g}</td>"
        f"<td>{pole['imag_hz']:+.7g}</td></tr>"
        for index, pole in enumerate(analysis["poles"])
    )
    assumptions = "".join(f"<li>{escape(item)}</li>" for item in scope["assumptions"])
    exclusions = "".join(
        f"<li><code>{escape(item)}</code></li>" for item in scope["excluded_dynamics"]
    )
    dominant = analysis["dominant_mode"]
    damping_ratio = dominant["damping_ratio"]
    damping_text = "不适用" if damping_ratio is None else _number(damping_ratio)
    stability_names = {"stable": "稳定", "marginal": "临界", "unstable": "失稳"}
    initial_state_text = "、".join(_number(value) for value in response["initial_state"])
    stiffness_table = _matrix_table(
        analysis["synchronous_stiffness_matrix"], analysis["vsm_ids"]
    )
    base = topology["base_values"]
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>低频构网型变流器降阶模型分析报告</title>
<style>
@page {{ size: A4; margin: 14mm; }}
body {{ font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif; color:#202b33; margin:0; font-size:11px; line-height:1.6; }}
h1 {{ font-size:21px; margin:0 0 4px; }} h2 {{ font-size:15px; margin:20px 0 8px; border-left:4px solid #176e64; padding-left:9px; }}
h3 {{ font-size:12px; margin:14px 0 6px; }} .sub {{ color:#697884; }}
.notice {{ padding:10px 13px; background:#fff5df; border:1px solid #edd7a8; border-radius:7px; }}
.grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin:13px 0; }}
.metric {{ padding:9px; background:#f3f7f7; border-radius:7px; }} .metric b {{ display:block; margin-top:3px; font-size:13px; }}
table {{ width:100%; border-collapse:collapse; margin-bottom:8px; }} th,td {{ padding:5px 7px; border:1px solid #dce3e7; text-align:left; }} th {{ background:#f2f5f6; }}
svg {{ width:100%; height:auto; border:1px solid #e0e6e9; border-radius:7px; margin:5px 0 10px; }}
code {{ font-family:Consolas,monospace; font-size:10px; }} .footer {{ margin-top:22px; padding-top:9px; border-top:1px solid #dfe5e8; color:#75838d; font-size:9px; }}
@media print {{ .print-tip {{ display:none; }} h2 {{ break-after:avoid; }} table,svg,.notice {{ break-inside:avoid; }} }}
</style></head><body>
<h1>低频构网型变流器降阶模型分析报告</h1>
<div class="sub">相角—频率—有功功率模型 · {escape(result['run_id'])} · 拓扑契约 {escape(topology['schema_version'])}</div>
<p class="print-tip"><button onclick="window.print()">打印或另存为 PDF</button></p>
<div class="notice"><b>适用边界：</b>{escape(scope['statement'])} 本报告给出的“稳定、临界或失稳”仅指该线性降阶状态矩阵的特征根分类；它不是完整 dq 模型结论，也没有评价论文的小增益—小相位定理。</div>
<div class="grid">
 <div class="metric">稳定性类别<b>{stability_names.get(analysis['stability'], escape(analysis['stability']))}</b></div>
 <div class="metric">主导极点<b>{dominant['real_hz']:+.6f} ± j{abs(dominant['imag_hz']):.6f} Hz</b></div>
 <div class="metric">主导振荡频率<b>{dominant['oscillation_frequency_hz']:.6f} Hz</b></div>
 <div class="metric">主导模态阻尼比<b>{damping_text}</b></div>
</div>
<h2>输入拓扑与参数</h2>
<p><b>{escape(topology['name'])}</b>（ID：<code>{escape(topology['id'])}</code>）；参考节点 <code>{escape(topology['reference_bus_id'])}</code>；坐标约定 <code>{escape(topology['frame_convention_id'])}</code>。基准容量 {_number(base['apparent_power_va'])} VA，基准电压 {_number(base['voltage_v'])} V，额定频率 {_number(base['frequency_hz'])} Hz。</p>
<p class="notice"><b>字段使用说明：</b>当前数值内核使用基频、线路 X、VSM 的 M/D/Tp、连接关系、无限大母线接地点和参考节点。P/Q 设定、负荷 P/Q、线路 R/B、无限大母线幅值与相角等字段仅完成契约校验和报告留痕，不进入本次状态矩阵。</p>
<h3>节点</h3><table><thead><tr><th>ID</th><th>名称</th><th>额定电压 / V</th></tr></thead><tbody>{bus_rows}</tbody></table>
<h3>交流线路</h3><table><thead><tr><th>ID</th><th>首端</th><th>末端</th><th>R / p.u.</th><th>X / p.u.</th><th>B / p.u.</th></tr></thead><tbody>{line_rows}</tbody></table>
<h3>构网型变流器</h3><table><thead><tr><th>ID</th><th>节点</th><th>控制</th><th>M / s</th><th>D / p.u.</th><th>Tp / s</th><th>P* / p.u.</th></tr></thead><tbody>{converter_rows}</tbody></table>
<h3>无限大母线</h3><table><thead><tr><th>ID</th><th>节点</th><th>电压 / p.u.</th><th>相角 / °</th></tr></thead><tbody>{source_rows}</tbody></table>
<h3>静态负荷</h3><table><thead><tr><th>ID</th><th>节点</th><th>模型</th><th>P / p.u.</th><th>Q / p.u.</th></tr></thead><tbody>{load_rows}</tbody></table>
<h2>模型假设</h2><ol>{assumptions}</ol><p>未纳入的动态或耦合：</p><ul>{exclusions}</ul>
<h2>同步刚度</h2><p>下表为无穷大母线接地并对无动态节点实施 Kron 消元后得到的同步刚度矩阵，单位按本算例的标幺与弧度约定解释。</p>{stiffness_table}
<h2>极点与主导模态</h2>
<table><thead><tr><th>序号</th><th>实部 / s⁻¹</th><th>虚部 / s⁻¹</th><th>实部 / Hz</th><th>虚部 / Hz</th></tr></thead><tbody>{pole_rows}</tbody></table>
<p>分类容差为 {_number(analysis['stability_tolerance_per_s'])} s⁻¹。主导模态实部 {dominant['real_per_s']:+.7g} s⁻¹，虚部 {dominant['imag_per_s']:+.7g} s⁻¹，振荡频率 {dominant['oscillation_frequency_hz']:.7g} Hz，阻尼比 {damping_text}。</p>
<h2>线性时域响应</h2><p>响应类型：零输入、初始条件扰动；初始状态向量为 [{initial_state_text}]；共 {len(response['time_s'])} 个采样点。该曲线由同一状态矩阵直接计算，不代表开关模型或非线性电磁暂态。</p>{time_chart}
<h2>来源与可追溯性</h2>
<table><tbody><tr><th>输入来源</th><td>{escape(provenance['source_kind'])}</td></tr><tr><th>预设 ID</th><td>{escape(str(provenance.get('preset_id') or '自定义拓扑'))}</td></tr><tr><th>实现</th><td><code>{escape(provenance['implementation'])}</code></td></tr><tr><th>拓扑契约</th><td><code>{escape(provenance['topology_contract'])}</code></td></tr><tr><th>与 Fig. 8 夹具隔离</th><td>{'是' if provenance['separated_from_fig8_fixture'] else '否'}</td></tr></tbody></table>
<div class="footer">本报告由本地分析平台根据请求中的完整拓扑与参数即时生成。报告保留模型假设、排除项和证据边界，不能替代完整平均值 dq 模型、非线性时域仿真或论文定理的独立验证。</div>
</body></html>"""
