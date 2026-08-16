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


def render_fig8_domain_comparison_report(result: dict) -> str:
    """Render the pinned same-domain comparison as a printable report."""

    summary = result["summary"]
    counts = summary["classificationCounts"]
    axes = result["axes"]
    rows = result["rows"]
    palette = {
        "criterion-covered-stable": ("#176e64", "判据覆盖且参考稳定"),
        "stable-not-covered": ("#e0a13a", "参考稳定但判据未覆盖"),
        "unstable-not-covered": ("#c34a4a", "参考失稳且判据未覆盖"),
        "numerical-pending": ("#83909a", "数值待定"),
        "consistency-violation": ("#7b3fa1", "一致性违例"),
    }
    by_point = {
        (
            round(row["impedance_scale_kappa"], 12),
            round(row["damping_d"], 12),
        ): row
        for row in rows
    }
    left, top, cell_width, cell_height = 80, 42, 54, 24
    width = left + cell_width * len(axes["impedance_scale_kappa"]) + 18
    height = top + cell_height * len(axes["damping_d"]) + 58
    cells: list[str] = []
    for row_index, damping in enumerate(reversed(axes["damping_d"])):
        y = top + row_index * cell_height
        cells.append(
            f'<text x="{left-8}" y="{y+16}" text-anchor="end" '
            f'font-size="9" fill="#52616d">{damping:.3g}</text>'
        )
        for column_index, kappa in enumerate(axes["impedance_scale_kappa"]):
            point = by_point[(round(kappa, 12), round(damping, 12))]
            color, label = palette[point["classification"]]
            x = left + column_index * cell_width
            title = (
                f"κ={kappa:.2f}, SCR={point['scr']:.4f}, D={damping:.3g}; "
                f"{label}; max Re(λ)={point['maximum_real_pole_hz']:+.6g} Hz"
            )
            cells.append(
                f'<rect x="{x}" y="{y}" width="{cell_width-2}" '
                f'height="{cell_height-2}" rx="2" fill="{color}">'
                f"<title>{escape(title)}</title></rect>"
            )
    x_labels = "".join(
        f'<text x="{left+index*cell_width+(cell_width-2)/2:.2f}" '
        f'y="{top+cell_height*len(axes["damping_d"])+16}" text-anchor="middle" '
        f'font-size="9" fill="#52616d">{value:.1f}</text>'
        for index, value in enumerate(axes["impedance_scale_kappa"])
    )
    scr_labels = "".join(
        f'<text x="{left+index*cell_width+(cell_width-2)/2:.2f}" '
        f'y="{top+cell_height*len(axes["damping_d"])+29}" text-anchor="middle" '
        f'font-size="7" fill="#82909a">{value:.3f}</text>'
        for index, value in enumerate(axes["scr_by_kappa"])
    )
    heatmap = (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        'aria-label="Fig. 8 D-SCR 同域对照图">'
        '<text x="10" y="18" font-size="12" font-weight="700" '
        'fill="#263641">阻尼 D—电网强度同域稳定性对照</text>'
        + "".join(cells)
        + x_labels
        + scr_labels
        + f'<text x="{left+cell_width*len(axes["impedance_scale_kappa"])/2:.2f}" '
        f'y="{height-5}" text-anchor="middle" font-size="9" fill="#52616d">'
        "线路阻抗缩放 κ（下一行列出对应 SCR）</text>"
        '<text x="14" y="150" transform="rotate(-90 14 150)" '
        'font-size="9" fill="#52616d">VSM 阻尼 D</text></svg>'
    )
    legend = "".join(
        f'<span><i style="background:{color}"></i>{escape(label)}</span>'
        for color, label in palette.values()
    )
    anchor = summary["anchorEvidence"]
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Fig. 8 同域稳定性对照报告</title>
<style>
@page {{ size:A4 landscape; margin:13mm; }}
body {{ font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif; color:#202b33; margin:0; font-size:11px; line-height:1.65; }}
h1 {{ font-size:21px; margin:0 0 4px; }} h2 {{ font-size:14px; margin:18px 0 8px; border-left:4px solid #176e64; padding-left:8px; }}
.sub {{ color:#697884; }} .notice {{ padding:9px 12px; background:#fff5df; border:1px solid #edd7a8; border-radius:7px; }}
.grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin:12px 0; }} .metric {{ padding:9px; background:#f3f7f7; border-radius:7px; }} .metric b {{ display:block; margin-top:3px; font-size:14px; }}
svg {{ width:100%; max-height:520px; border:1px solid #e0e6e9; border-radius:7px; }} .legend {{ display:flex; flex-wrap:wrap; gap:13px; margin:8px 0; }} .legend span {{ display:flex; align-items:center; gap:5px; }} .legend i {{ width:11px; height:11px; border-radius:2px; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:5px 7px; border:1px solid #dce3e7; text-align:left; }} th {{ background:#f2f5f6; }} .footer {{ margin-top:18px; color:#75838d; font-size:9px; }}
@media print {{ .print-tip {{ display:none; }} .notice,svg,table {{ break-inside:avoid; }} }}
</style></head><body>
<h1>Fig. 8 同一参数域稳定性对照报告</h1>
<div class="sub">作者同一模型 · 阻尼 D—线路阻抗缩放 κ / SCR · {summary['parameterPointCount']} 个参数点</div>
<p class="print-tip"><button onclick="window.print()">打印或另存为 PDF</button></p>
<div class="grid">
 <div class="metric">判据覆盖且参考稳定<b>{counts['criterionCoveredStable']}</b></div>
 <div class="metric">参考稳定但判据未覆盖<b>{counts['stableNotCovered']}</b></div>
 <div class="metric">参考失稳且判据未覆盖<b>{counts['unstableNotCovered']}</b></div>
 <div class="metric">数值待定 / 一致性违例<b>{counts['numericalPending']} / {counts['consistencyViolation']}</b></div>
</div>
<div class="notice"><b>解释边界：</b>{escape(result['provenance']['claim_boundary_zh'])} {escape(result['provenance']['interpretation_zh'])} {escape(result['provenance']['closed_loop_boundary_zh'])}</div>
<h2>核心参数域对照</h2><div class="legend">{legend}</div>{heatmap}
<h2>计算与锚点核验</h2>
<table><tbody>
<tr><th>频率样本</th><td>{summary['frequencyPointCountPerParameterPoint']} 点，{summary['frequencyMinimumHz']:.3g}—{summary['frequencyMaximumHz']:.3g} Hz</td><th>相位分类角网格</th><td>{summary['phaseClassifierAngles']}</td></tr>
<tr><th>D=0.05 变流器响应最大误差</th><td>{anchor['damping005ConverterMaxAbsError']:.3g}</td><th>D=0.05 主导极点实部误差</th><td>{anchor['damping005MaximumRealPoleErrorHz']:.3g} Hz</td></tr>
<tr><th>D=0.5 变流器响应最大误差</th><td>{anchor['damping05ConverterMaxAbsError']:.3g}</td><th>D=0.5 主导极点实部误差</th><td>{anchor['damping05MaximumRealPoleErrorHz']:.3g} Hz</td></tr>
</tbody></table>
<h2>答辩口径</h2><p>在本模型和离散参数域内，有限网格充分判据覆盖的 45 个点全部位于闭环特征根参考稳定区内；另有 96 个点虽由特征根参考判为稳定，却未被该充分条件覆盖。这说明该判据在所考察范围内具有可观察的保守性。未覆盖不等于失稳，闭环特征根也只是冻结模型上的有限精度参考，并非物理系统的绝对真值。</p>
<div class="footer">生成器：{escape(result['provenance']['generator'])}。便携软件只读加载已经核验的 MATLAB/作者模型研究证据，运行本报告不要求安装 MATLAB。</div>
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


def render_fig8_sensitivity_report(result: dict) -> str:
    """Render the fixed finite-grid sensitivity experiment."""

    cases = {case["case_id"]: case for case in result["cases"]}
    unstable = cases["fig8_D_0p05"]
    stable = cases["fig8_D_0p5"]
    density = unstable["frequency_density"]
    chart = _linear_svg_chart(
        [float(row["requested_point_count"]) for row in density],
        [
            (
                "D=0.05 检出未覆盖点",
                [float(row["uncovered_count"]) for row in density],
                "#9b6654",
            ),
            (
                "D=0.5 检出未覆盖点",
                [
                    float(row["uncovered_count"])
                    for row in stable["frequency_density"]
                ],
                "#667d7d",
            ),
        ],
        "频率子网格对未覆盖样点的检出能力",
        "子网格点数",
        "检出的未覆盖点数",
    )
    density_rows = "".join(
        "<tr>"
        f"<td>{row['requested_point_count']}</td>"
        f"<td>{row['maximum_log10_frequency_step']:.6g}</td>"
        f"<td>{row['uncovered_count']}</td>"
        f"<td>{_number(row['first_uncovered_frequency_hz']) if row['first_uncovered_frequency_hz'] is not None else '未检出'}</td>"
        f"<td>{_number(row['last_uncovered_frequency_hz']) if row['last_uncovered_frequency_hz'] is not None else '未检出'}</td>"
        f"<td>{row['unobserved_full_grid_uncovered_points']}</td>"
        "</tr>"
        for row in density
    )
    tolerance_rows = "".join(
        "<tr>"
        f"<td>{row['gain_relative_tolerance']:.0e}</td>"
        f"<td>{row['phase_tolerance_rad']:.0e}</td>"
        f"<td>{row['coverage_mismatch_from_default']}</td>"
        f"<td>{row['uncovered_count']}</td>"
        "</tr>"
        for row in unstable["decision_tolerance"]
    )
    scale_rows = "".join(
        "<tr>"
        f"<td>{row['common_post_transformation_matrix_scale']:.0e}</td>"
        f"<td>{row['coverage_mismatch_from_unit_scale']}</td>"
        f"<td>{row['uncovered_count']}</td>"
        "</tr>"
        for row in unstable["common_matrix_scale"]
    )
    scope = result["model_scope"]
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Fig. 8 有限网格敏感性报告</title>
<style>
@page {{ size:A4; margin:14mm; }}
body {{ font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif; color:#202b33; margin:0; font-size:11px; line-height:1.65; }}
h1 {{ font-size:21px; margin:0 0 4px; }} h2 {{ font-size:15px; margin:20px 0 8px; border-left:4px solid #667d7d; padding-left:9px; }}
.sub {{ color:#697884; }} .notice {{ padding:10px 13px; background:#f4f0e7; border-left:3px solid #96745c; }}
.grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin:13px 0; }}
.metric {{ padding:10px; background:#f3f1ea; }} .metric b {{ display:block; margin-top:4px; font-size:13px; }}
table {{ width:100%; border-collapse:collapse; margin-bottom:8px; }} th,td {{ padding:6px 7px; border:1px solid #dcd9cf; text-align:left; }} th {{ background:#efede5; }}
svg {{ width:100%; height:auto; border:1px solid #dedbd2; margin:6px 0 10px; }}
.footer {{ margin-top:22px; padding-top:9px; border-top:1px solid #dfe0dc; color:#75807b; font-size:9px; }}
@media print {{ .print-tip {{ display:none; }} table,svg,.notice {{ break-inside:avoid; }} }}
</style></head><body>
<h1>Fig. 8 有限频率网格敏感性报告</h1>
<div class="sub">作者固定1000点夹具 · 回顾性子网格 · 判定容差与矩阵表示尺度核查</div>
<p class="print-tip"><button onclick="window.print()">打印或另存为 PDF</button></p>
<div class="notice"><b>适用边界：</b>{escape(scope['statement'])} 本报告不评价论文连续全频定理。</div>
<div class="grid">
 <div class="metric">默认1000点重构<b>{'完全一致' if result['summary']['baseline_reconstruction_exact'] else '存在差异'}</b></div>
 <div class="metric">9点子网格<b>漏检75个完整网格未覆盖样点</b></div>
 <div class="metric">稳定工况测试设置<b>{'均未出现未覆盖点' if result['summary']['stable_case_remains_covered_in_all_tested_settings'] else '出现变化'}</b></div>
</div>
{chart}
<h2>频率采样密度</h2>
<table><thead><tr><th>点数</th><th>最大 log10 步长</th><th>检出未覆盖点</th><th>首频 / Hz</th><th>末频 / Hz</th><th>未观察到的1000点未覆盖样点</th></tr></thead><tbody>{density_rows}</tbody></table>
<p>9点子网格在0.001–10000 Hz范围内没有命中0.4985–1.6452 Hz未覆盖带；15点仅命中约0.9977 Hz的一个样点。故“所取样点均被覆盖”不能推出连续频带均被覆盖。</p>
<h2>最终判定容差</h2>
<table><thead><tr><th>增益相对容差</th><th>相位容差 / rad</th><th>相对默认分类变化</th><th>未覆盖点</th></tr></thead><tbody>{tolerance_rows}</tbody></table>
<p>在10⁻¹²至10⁻⁶的测试范围内，两个固定工况的已采样点分类均未变化。这只说明这些样点没有落入所测容差带，不能外推到其他算例。</p>
<h2>共同矩阵表示尺度</h2>
<table><thead><tr><th>共同正尺度</th><th>相对单位尺度分类变化</th><th>未覆盖点</th></tr></thead><tbody>{scale_rows}</tbody></table>
<p>在10⁻⁹至10⁹的共同正尺度范围内，逐点分类不变；该操作是整形后矩阵表示缩放，不是线路、控制器或运行点的物理扰动。</p>
<h2>可复现性与结论</h2>
<p>实验为确定性计算，无随机种子；子网格使用包含两端点的等索引取样。失败条件包括默认重构不一致、稳定工况产生未覆盖点，以及共同正尺度改变分类。当前三项失败条件均未触发，但9点频率网格构成明确的漏检反例。</p>
<div class="footer">生成接口：<code>GET /api/analysis/fig8-sensitivity</code>。本报告区分有限样点数值稳健性与连续频带定理证明。</div>
</body></html>"""


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


def render_average_dq_report(result: dict) -> str:
    """Render a self-contained report for one 16-state average-value dq run."""

    topology = result["input_topology"]
    parameters = result["input_parameters"]
    operating = result["operating_point"]
    analysis = result["result"]
    scope = result["model_scope"]
    provenance = result["provenance"]
    response = analysis["time_response"]
    nonlinear_columns = list(zip(*response["nonlinear_states"], strict=True))
    linear_columns = list(zip(*response["linear_states"], strict=True))
    equilibrium_angle = float(operating["state"][0])
    time_chart = _linear_svg_chart(
        response["time_s"],
        [
            (
                "相角偏差（非线性）",
                [(float(value) - equilibrium_angle) * 1000.0 for value in nonlinear_columns[0]],
                "#176e64",
            ),
            (
                "相角偏差（线性）",
                [(float(value) - equilibrium_angle) * 1000.0 for value in linear_columns[0]],
                "#b77824",
            ),
        ],
        "平均值模型与局部线性模型的小扰动响应",
        "时间 / s",
        "相角偏差 / mrad",
    )
    pole_rows = "".join(
        f"<tr><td>{index + 1}</td><td>{pole['real_per_s']:+.7g}</td>"
        f"<td>{pole['imag_per_s']:+.7g}</td><td>{pole['real_hz']:+.7g}</td>"
        f"<td>{pole['imag_hz']:+.7g}</td></tr>"
        for index, pole in enumerate(analysis["poles"])
    )
    parameter_rows = "".join(
        f"<tr><th>{escape(str(name))}</th><td>{escape(str(value))}</td></tr>"
        for name, value in parameters.items()
        if name not in {"schema_version", "frame_convention_id"}
    )
    state_rows = "".join(
        f"<tr><td>{escape(label)}</td><td>{_number(float(value), 8)}</td></tr>"
        for label, value in zip(
            operating["state_labels"], operating["state"], strict=True
        )
    )
    retained = "".join(
        f"<li><code>{escape(item)}</code></li>" for item in scope["retained_dynamics"]
    )
    excluded = "".join(
        f"<li><code>{escape(item)}</code></li>" for item in scope["excluded_dynamics"]
    )
    dominant = analysis["dominant_mode"]
    reduction = analysis["quasisteady_reduction_comparison"]
    frequency_error_text = (
        "不适用"
        if reduction["oscillation_frequency_relative_error"] is None
        else f"{100 * reduction['oscillation_frequency_relative_error']:.3f}%"
    )
    decay_error_text = (
        "不适用"
        if reduction["decay_rate_relative_error"] is None
        else f"{100 * reduction['decay_rate_relative_error']:.3f}%"
    )
    stability_names = {"stable": "稳定", "marginal": "临界", "unstable": "失稳"}
    converter = topology["grid_forming_converters"][0]
    line = topology["lines"][0]
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>平均值 dq 构网型变流器分析报告</title>
<style>
@page {{ size:A4; margin:14mm; }}
body {{ font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif; color:#202b33; margin:0; font-size:11px; line-height:1.6; }}
h1 {{ font-size:21px; margin:0 0 4px; }} h2 {{ font-size:15px; margin:20px 0 8px; border-left:4px solid #176e64; padding-left:9px; }}
h3 {{ font-size:12px; margin:14px 0 6px; }} .sub {{ color:#697884; }}
.notice {{ padding:10px 13px; background:#fff5df; border:1px solid #edd7a8; border-radius:7px; }}
.grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin:13px 0; }}
.metric {{ padding:9px; background:#f3f7f7; border-radius:7px; }} .metric b {{ display:block; margin-top:3px; font-size:13px; }}
table {{ width:100%; border-collapse:collapse; margin-bottom:8px; }} th,td {{ padding:5px 7px; border:1px solid #dce3e7; text-align:left; }} th {{ background:#f2f5f6; }}
svg {{ width:100%; height:auto; border:1px solid #e0e6e9; border-radius:7px; margin:5px 0 10px; }}
code {{ font-family:Consolas,monospace; font-size:10px; }} .columns {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
.footer {{ margin-top:22px; padding-top:9px; border-top:1px solid #dfe5e8; color:#75838d; font-size:9px; }}
@media print {{ .print-tip {{ display:none; }} h2 {{ break-after:avoid; }} table,svg,.notice {{ break-inside:avoid; }} }}
</style></head><body>
<h1>平均值 dq 构网型变流器分析报告</h1>
<div class="sub">16 状态正序平均模型 · {escape(result['run_id'])} · {escape(topology['name'])}</div>
<p class="print-tip"><button onclick="window.print()">打印或另存为 PDF</button></p>
<div class="notice"><b>适用边界：</b>{escape(scope['statement'])}</div>
<div class="grid">
 <div class="metric">闭环特征根分类<b>{stability_names.get(analysis['stability'], escape(analysis['stability']))}</b></div>
 <div class="metric">主导极点<b>{dominant['real_hz']:+.6f} + j{dominant['imag_hz']:+.6f} Hz</b></div>
 <div class="metric">PCC 电流<b>{operating['grid_current_magnitude_pu']:.6f} p.u.</b></div>
 <div class="metric">端口互联误差<b>{analysis['port_interconnection_max_abs_error']:.3e}</b></div>
</div>
<h2>输入模型</h2>
<p>变流器 <code>{escape(converter['id'])}</code> 位于节点 <code>{escape(converter['bus_id'])}</code>，外部线路 <code>{escape(line['id'])}</code> 的 R/X 为 {_number(line['resistance_pu'])}/{_number(line['reactance_pu'])} p.u.；坐标约定 <code>{escape(topology['frame_convention_id'])}</code>。</p>
<table><tbody>{parameter_rows}</tbody></table>
<h2>工作点与物理诊断</h2>
<div class="grid">
 <div class="metric">代数残差∞范数<b>{max(abs(value) for value in operating['algebraic_residual']):.3e}</b></div>
 <div class="metric">闭环动态残差∞范数<b>{operating['closed_rhs_residual_inf']:.3e}</b></div>
 <div class="metric">滤波器有功平衡残差<b>{operating['active_power_balance_residual_pu']:.3e} p.u.</b></div>
 <div class="metric">内部电压幅值<b>{operating['internal_voltage_magnitude_pu']:.6f} p.u.</b></div>
</div>
<table><thead><tr><th>状态</th><th>工作点值</th></tr></thead><tbody>{state_rows}</tbody></table>
<h2>模型保留项与排除项</h2><div class="columns"><div><h3>本模型保留</h3><ul>{retained}</ul></div><div><h3>本模型不包含</h3><ul>{excluded}</ul></div></div>
<h2>闭环极点</h2><table><thead><tr><th>序号</th><th>实部 / s⁻¹</th><th>虚部 / s⁻¹</th><th>实部 / Hz</th><th>虚部 / Hz</th></tr></thead><tbody>{pole_rows}</tbody></table>
<p>直接闭合矩阵与“变流器端口模型 + 外部线路方程”独立重组矩阵的最大逐元素误差为 {analysis['port_interconnection_max_abs_error']:.6e}。这项检查同时约束 PCC 方向、线路 dq 动态和电流正负号。</p>
<h2>与三状态低频近似的层级比较</h2>
<p>在同一工作点保持 Q–V 准稳态关系，数值求得同步刚度 Kδ={reduction['synchronizing_stiffness_pu_per_rad']:.7g} p.u./rad。三状态最右模态相对于16状态模型中匹配同步模态的振荡频率误差为 {frequency_error_text}，衰减率误差为 {decay_error_text}。{escape(reduction['interpretation'])}</p>
<h2>非线性—线性小扰动交叉核对</h2><p>下图比较同一工作点和初始状态下的平均值非线性 ODE 与局部线性矩阵响应。两者的一致性属于实现验证，不等同于与实物或 EMT 模型的外部确认。</p>{time_chart}
<h2>来源与结论边界</h2><table><tbody>
<tr><th>输入来源</th><td>{escape(provenance['source_kind'])}</td></tr>
<tr><th>实现</th><td><code>{escape(provenance['implementation'])}</code></td></tr>
<tr><th>模型规格</th><td><code>{escape(provenance['model_specification'])}</code></td></tr>
<tr><th>论文 Fig. 8 夹具</th><td>明确隔离；本报告不是论文算例复现</td></tr>
<tr><th>硬件参数拟合</th><td>{'否' if provenance.get('physical_hardware_fit') is False else '未声明'}</td></tr>
</tbody></table>
<div class="footer">本报告由本地分析平台从完整输入拓扑与参数即时计算。它证明当前方程和软件实现之间的内部一致性；在没有外部实物、可信 EMT 或独立实验数据前，不宣称完成工程模型确认。</div>
</body></html>"""
