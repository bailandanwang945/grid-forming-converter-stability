"""Bounded sampled-command pilot; no digital PI, PWM, or hardware claim.

Run from the repository root: python experiments/average-dq/run_sampled_modulation_pilot.py
Only this script and results/average-dq-sampled-modulation-pilot are owned here.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import scipy
from scipy.integrate import solve_ivp
from scipy.linalg import eig, expm
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.core.average_dq_model import build_average_dq_model, _closed_rhs, _references
from backend.core.average_dq_presets import build_average_dq_ablation_anchor_case

FACTORS = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0]
PERIODS = [1e-4, 5e-4, 1e-3, 2e-3]
SMALL_PERIODS = [1e-7, 2e-7, 5e-7]
TOL = dict(block_relative=2e-7, command_relative=2e-7,
           equilibrium_absolute=1e-8, eigen_residual=1e-9,
           classification_per_s=1e-5, propagation_relative=2e-7,
           small_period_relative=0.003)
START = time.perf_counter()


def deadline():
    if time.perf_counter() - START > 115:
        raise TimeoutError("Pilot reached its 115-second internal deadline")


def relative_error(actual, expected):
    return float(np.linalg.norm(actual - expected) / max(1.0, np.linalg.norm(expected)))


def command(x, p, converter):
    """Independent transcription of the continuous inner-loop command equations.

    x contains only the first 14 continuous states; no internal-voltage input.
    This avoids deriving the command from Tmod times the core RHS.
    """
    j = np.array([[0.0, -1.0], [1.0, 0.0]])
    omega = 1.0 + x[1]
    ic, vc, ig = x[4:6], x[6:8], x[8:10]
    vref = np.array([converter.voltage_setpoint_pu +
        p.reactive_power_voltage_droop_pu *
        (converter.reactive_power_setpoint_pu - x[3]), 0.0])
    vref -= p.virtual_resistance_pu * ig
    vref -= p.virtual_reactance_pu * omega * j @ ig
    iref = (ig + p.filter_capacitor_susceptance_pu * omega * j @ vc
            + p.voltage_proportional_gain_pu * (vref - vc) + x[10:12])
    return (vc + p.converter_side_resistance_pu * ic
            + p.converter_side_reactance_pu * omega * j @ ic
            + p.current_proportional_gain_pu * (iref - ic) + x[12:14])


def command_jacobian(x, p, converter):
    f = np.empty((2, 14))
    for k in range(14):
        h = 1e-6 * max(1.0, abs(x[k]))
        plus, minus = x.copy(), x.copy()
        plus[k] += h
        minus[k] -= h
        f[:, k] = (command(plus, p, converter) - command(minus, p, converter)) / (2*h)
    return f


def split(model):
    a = model.linearization.closed_state_matrix
    tau = model.parameters.modulation_time_constant_s
    return a[:14, :14], a[:14, 14:], tau * a[14:, :14]


def sampled_matrix(a0, b, f, period):
    aug = np.zeros((16, 16))
    aug[:14, :14], aug[:14, 14:] = a0, b
    transition = expm(aug * period)
    return transition[:14, :14] + transition[:14, 14:] @ f


def lag_matrix(a0, b, f, tau):
    return np.block([[a0, b], [f/tau, -np.eye(2)/tau]])


def spectrum(a, period=None):
    values, vectors = eig(a)
    denominator = max(1.0, np.linalg.norm(a, 2))
    residuals = [float(np.linalg.norm(a @ vectors[:, k] - values[k] * vectors[:, k]) /
                       (denominator * np.linalg.norm(vectors[:, k]))) for k in range(len(values))]
    metric = float(np.max(values.real)) if period is None else float(np.log(np.max(abs(values))) / period)
    pending = max(residuals) > TOL['eigen_residual'] or abs(metric) <= TOL['classification_per_s']
    status = 'numerical-pending' if pending else ('stable' if metric < 0 else 'unstable')
    order = np.lexsort((values.imag, values.real))
    return dict(spectrum=[[float(values[k].real), float(values[k].imag)] for k in order],
                metric_per_s=metric, metric_name='alpha' if period is None else 'log_rho_over_Ts',
                spectral_radius=None if period is None else float(np.max(abs(values))),
                maximum_eigenpair_relative_residual=max(residuals), classification=status)


def propagation_test(a0, b, f, period):
    phi = sampled_matrix(a0, b, f, period)
    # Both physical command axes, plus two state directions; equal initial norm.
    initial = [np.linalg.pinv(f) @ v for v in np.eye(2)]
    initial += [np.eye(14)[4], np.eye(14)[7]]
    errors = []
    command_vectors = []
    for x in initial:
        x = x / np.linalg.norm(x)
        actual, expected = x.copy(), x.copy()
        command_vectors.append((f @ x).tolist())
        for _ in range(3):
            deadline()
            held = f @ actual
            sol = solve_ivp(lambda _t, state: a0 @ state + b @ held,
                            (0, period), actual, method='DOP853',
                            rtol=1e-10, atol=1e-12, max_step=period/8)
            if not sol.success:
                raise RuntimeError(sol.message)
            actual = sol.y[:, -1]
            expected = phi @ expected
            errors.append(relative_error(actual, expected))
    return dict(method='DOP853', rtol=1e-10, atol=1e-12, max_step_s=period/8,
                cycles_per_direction=3, directions=4, initial_command_vectors=command_vectors,
                command_direction_rank=int(np.linalg.matrix_rank(np.array(command_vectors)[:2])),
                maximum_relative_error=max(errors), passed=max(errors) <= TOL['propagation_relative'])


def nonlinear_map_test(model, a0, b, f, period=5e-4):
    """Local-dq envelope hold: phase synthesis remains continuous.

    Integrate the original nonlinear top-14 RHS with fixed bottom-2 inputs.
    Centered differences on delta and frequency test the nonlinear map,
    not just agreement of two linear matrix propagation implementations.
    """
    xstar = model.operating_point.state
    ustar = xstar[14:]
    amplitudes = [1e-5, 5e-6, 2.5e-6]
    phi = sampled_matrix(a0,b,f,period)
    rows = []
    for column in [0,1]:
        expected = phi[:,column]
        for amplitude in amplitudes:
            endpoints = []
            for sign in [-1,1]:
                deadline()
                initial = xstar.copy()
                initial[column] += sign*amplitude
                rhs0 = _closed_rhs(initial,model.operating_point.grid_voltage_global,
                    _references(model.converter),model.topology,model.parameters,model.converter,model.line)
                # g(x)=u+Tmod*rhs_u. This includes the affine ustar term.
                held = initial[14:] + model.parameters.modulation_time_constant_s * rhs0[14:]
                def nonlinear_rhs(_t, state):
                    return _closed_rhs(np.concatenate([state,held]),
                        model.operating_point.grid_voltage_global,_references(model.converter),
                        model.topology,model.parameters,model.converter,model.line)[:14]
                sol = solve_ivp(nonlinear_rhs,(0,period),initial[:14],method='DOP853',
                    rtol=1e-11,atol=1e-13,max_step=period/12)
                if not sol.success:
                    raise RuntimeError(sol.message)
                endpoints.append(sol.y[:,-1])
            observed = (endpoints[1]-endpoints[0])/(2*amplitude)
            rows.append(dict(state_column=column,amplitude=amplitude,
                relative_map_derivative_error=relative_error(observed,expected)))
    return dict(period_s=period,current_pi_factor=0.5,method='DOP853',rtol=1e-11,atol=1e-13,
        max_step_s=period/12,amplitudes=amplitudes,tested_columns=['delta','frequency_deviation'],
        rows=rows,passed=max(row['relative_map_derivative_error'] for row in rows)<2e-5,
        note='Centered finite differences may reach an integration-roundoff floor; all amplitude errors retained.')


def main():
    output = ROOT / 'results/average-dq-sampled-modulation-pilot'
    result = dict(schema='sampled-modulation-pilot/1.0', date='2026-10-02',
        hypothesis='First-order modulation lag may change a sampled-command stability classification.',
        unique_change='Synchronous ZOH of local control-dq modulation envelope; all other control continuous; no one-sample computational delay.',
        parameters=dict(current_pi_factors=FACTORS, periods_s=PERIODS, small_periods_s=SMALL_PERIODS),
        tolerances=TOL, equations=dict(phi='exp(A0*Ts)+Gamma*F',
            gamma='integral_0^Ts exp(A0*t)*B dt, evaluated by block exponential',
            ideal='A0+B*F', phase_matched_lag='tau=Ts/2'),
        provenance=dict(python=sys.version, scipy=scipy.__version__, numpy=np.__version__,
                        platform=platform.platform(),
                        commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                        command='python experiments/average-dq/run_sampled_modulation_pilot.py'),
        points=[], propagation=[], checks=[], limitations=[
            'Synthetic average-value single-converter model; no EMT, switching waveform, or hardware validation.',
            'Only the modulation command is sampled. PI integrators, outer loops and measurement filters remain continuous.',
            'Held values are local control-dq envelopes with continuously evolving phase synthesis, not physical alpha-beta/abc voltage holds.',
            'No discrete coordinate-update timing is included; this is not a physical digital-controller reference.',
            'No computational delay, PWM carrier dynamics, quantization, saturation or multirate control.',
            'Six prescribed current-PI factors and four periods do not establish a continuous parameter region.',
            'Small-period convergence is numerical evidence, not a theorem or physical confirmation.',
            'No novelty established: ZOH, matrix exponential and sampled feedback are existing methods.',
            'The tau=Ts/2 lag is a low-frequency phase-matched comparator, not an identical actuator.'])
    hashes = {}
    for path in ['backend/core/average_dq_model.py', 'backend/core/average_dq_presets.py', __file__]:
        file = Path(path) if Path(path).is_absolute() else ROOT/path
        hashes[str(file.relative_to(ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()
    result['provenance']['source_sha256_provenance_only'] = hashes
    all_passed = True
    try:
        for factor in FACTORS:
            deadline()
            topology, p = build_average_dq_ablation_anchor_case()
            p = p.model_copy(update=dict(current_proportional_gain_pu=p.current_proportional_gain_pu*factor,
                                        current_integral_gain_per_s=p.current_integral_gain_per_s*factor))
            model = build_average_dq_model(topology, p)
            a = model.linearization.closed_state_matrix
            a0, b, f = split(model)
            direct_f = command_jacobian(model.operating_point.state[:14], p, model.converter)
            checks = dict(current_pi_factor=factor,
                a22_relative_error=relative_error(a[14:,14:], -np.eye(2)/p.modulation_time_constant_s),
                independent_command_F_relative_error=relative_error(f, direct_f),
                command_equilibrium_absolute_error=float(np.max(abs(command(model.operating_point.state[:14],p,model.converter)
                                                               -model.operating_point.state[14:]))),
                command_has_no_internal_voltage_argument=True,
                finite_difference_relative_step=1e-6)
            alternative = build_average_dq_model(topology, p.model_copy(update=dict(
                modulation_time_constant_s=p.modulation_time_constant_s*2)))
            a02, b2, f2 = split(alternative)
            checks['Tmod_double_a0_relative_error'] = relative_error(a02,a0)
            checks['Tmod_double_b_relative_error'] = relative_error(b2,b)
            checks['Tmod_double_F_relative_error'] = relative_error(f2,f)
            checks['Tmod_double_equilibrium_absolute_error'] = float(np.max(abs(
                alternative.operating_point.state-model.operating_point.state)))
            checks['passed'] = (max(checks[k] for k in ['a22_relative_error','Tmod_double_a0_relative_error',
                'Tmod_double_b_relative_error','Tmod_double_F_relative_error']) <= TOL['block_relative'] and
                checks['independent_command_F_relative_error'] <= TOL['command_relative'] and
                max(checks[k] for k in ['command_equilibrium_absolute_error','Tmod_double_equilibrium_absolute_error'])
                <= TOL['equilibrium_absolute'])
            model_half_step = build_average_dq_model(topology,p,relative_step=5e-6)
            a0h,bh,fh=split(model_half_step)
            ah=model_half_step.linearization.closed_state_matrix
            checks['linearization_relative_steps']=[1e-5,5e-6]
            checks['linearization_matrix_step_relative_difference']=relative_error(ah,a)
            ideal_matrix = a0+b@f
            ideal = spectrum(ideal_matrix)
            baseline = spectrum(a)
            ideal_roots = np.linalg.eigvals(ideal_matrix)
            convergence = []
            for small in SMALL_PERIODS:
                sm = sampled_matrix(a0,b,f,small)
                inferred = np.log(np.linalg.eigvals(sm).astype(complex))/small
                costs = abs(inferred[:,None]-ideal_roots[None,:])
                ri, ci = linear_sum_assignment(costs)
                convergence.append(dict(period_s=small,
                    maximum_matched_root_absolute_error_per_s=float(np.max(costs[ri,ci])),
                    alpha_error_per_s=float(abs(np.log(max(abs(np.linalg.eigvals(sm))))/small-ideal['metric_per_s']))))
            errors = [row['maximum_matched_root_absolute_error_per_s'] for row in convergence]
            checks['small_period_root_errors_per_s'] = convergence
            checks['small_period_errors_increase_with_Ts'] = all(errors[k] <= errors[k+1]*1.02+1e-6 for k in range(2))
            checks['smallest_period_relative_root_error'] = errors[0]/max(1.0,float(max(abs(ideal_roots))))
            checks['small_period_regression_passed'] = (checks['small_period_errors_increase_with_Ts'] and
                checks['smallest_period_relative_root_error'] <= TOL['small_period_relative'])
            checks['passed'] = checks['passed'] and checks['small_period_regression_passed']
            result['checks'].append(checks)
            all_passed &= checks['passed']
            for period in PERIODS:
                deadline()
                sampled = spectrum(sampled_matrix(a0,b,f,period),period)
                lag = spectrum(lag_matrix(a0,b,f,period/2))
                negative = spectrum(expm(a*period),period)
                # Compare adjacent finite-difference steps before allowing labels.
                comparisons = [(baseline,spectrum(ah)),
                    (ideal,spectrum(a0h+bh@fh)),
                    (sampled,spectrum(sampled_matrix(a0h,bh,fh,period),period)),
                    (lag,spectrum(lag_matrix(a0h,bh,fh,period/2))),
                    (negative,spectrum(expm(ah*period),period))]
                for item, alternate_item in comparisons:
                    diff=abs(item['metric_per_s']-alternate_item['metric_per_s'])
                    item['linearization_step_metric_difference_per_s']=diff
                    item['classification_uncertainty_per_s']=max(TOL['classification_per_s'],10*diff)
                    if abs(item['metric_per_s']) <= item['classification_uncertainty_per_s']:
                        item['classification']='numerical-pending'
                negative_pass = negative['classification'] == baseline['classification']
                all_passed &= negative_pass
                result['points'].append(dict(current_pi_factor=factor,period_s=period,
                    baseline_original_tau_s=p.modulation_time_constant_s,
                    baseline=baseline,ideal_instantaneous=ideal,sampled_command=sampled,
                    phase_matched_lag=lag,full_closed_loop_exponential_negative_control=negative,
                    negative_control_label_preserved=negative_pass,
                    sampled_vs_phase_matched_lag_disagreement=(sampled['classification'] != lag['classification']
                        and 'numerical-pending' not in [sampled['classification'],lag['classification']])))
            if factor in [0.5,2.0]:
                check = propagation_test(a0,b,f,1e-3)
                check['current_pi_factor'] = factor
                result['propagation'].append(check)
                all_passed &= check['passed'] and check['command_direction_rank']==2
            if factor == 0.5:
                result['nonlinear_one_cycle_map_check']=nonlinear_map_test(model,a0,b,f)
                all_passed &= result['nonlinear_one_cycle_map_check']['passed']
            print(f'factor={factor:g}: block={checks["passed"]}; 4 periods recorded',flush=True)
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
        all_passed = False
    result['runtime_s'] = time.perf_counter()-START
    result['point_count'] = len(result['points'])
    result['disagreement_count'] = sum(p['sampled_vs_phase_matched_lag_disagreement'] for p in result['points'])
    result['status'] = 'verified-bounded-pilot' if all_passed and len(result['points'])==24 else 'incomplete-or-check-failed'
    output.mkdir(parents=True,exist_ok=True)
    (output/'pilot.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    lines = ['# 同步采样调制指令有界预实验','',
        f'- 状态：{result["status"]}；实际记录 {len(result["points"])} / 24 点。',
        f'- 采样保持与 τ=Ts/2 一阶滞后标签分歧：{result["disagreement_count"]} 点。',
        '- 同一 D=60、X=0.1 模型；只同步采样并保持局部控制dq调制包络，PI与外环仍连续；无一拍计算延迟。',
        '- 局部dq包络保持包含连续相位合成，不等同物理αβ/abc保持；未建离散坐标更新时间。',
        '- 属于模型比较，不是实机安全周期；原创性尚未建立。','',
        '|电流PI倍率|Ts(s)|原模型alpha|即时alpha|采样logρ/Ts|相位匹配滞后alpha|采样/滞后标签|',
        '|---:|---:|---:|---:|---:|---:|---|']
    for row in result['points']:
        lines.append(f'|{row["current_pi_factor"]:g}|{row["period_s"]:g}|'
            f'{row["baseline"]["metric_per_s"]:.8g}|{row["ideal_instantaneous"]["metric_per_s"]:.8g}|'
            f'{row["sampled_command"]["metric_per_s"]:.8g}|{row["phase_matched_lag"]["metric_per_s"]:.8g}|'
            f'{row["sampled_command"]["classification"]}/{row["phase_matched_lag"]["classification"]}|')
    lines += ['', '## 核验','', '- 全部谱及特征对残差在 pilot.json，含全部24点的4种对照与原模型。',
        '- F由独立控制方程有限差分核对；A22、双Tmod分块和工作点一致性均记录实际误差。',
        '- 小Ts三点报告匹配根误差与回归趋势；整机指数仅作为稳定标签不变阴性对照。',
        '- 两个倍率、两种命令轴及两种状态方向：逐周期固定输入DOP853独立核传播；3周期/方向。',
        '- 原非线性RHS的delta/frequency一周期映射作三幅值中心差分；仅局部dq保持假设。',
        '- 相邻线性化步长1e-5、5e-6核分类指标；落在10倍指标差异或1e-5/s内单列待定。',
        '- 每个状态/谱接近边界或残差超过冻结门槛时为 numerical-pending，不强制标签。', '',
        '## 复现及限制','', '```powershell','python experiments/average-dq/run_sampled_modulation_pilot.py','```','']
    lines += [f'- {item}' for item in result['limitations']]
    if 'error' in result:
        lines += ['',f'未完成原因：{result["error"]}']
    (output/'pilot.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=result['status'],points=result['point_count'],
        disagreements=result['disagreement_count'],runtime_s=result['runtime_s'],
        output=str(output)),ensure_ascii=False),flush=True)
    return 0 if result['status']=='verified-bounded-pilot' else 1


if __name__ == '__main__':
    raise SystemExit(main())
