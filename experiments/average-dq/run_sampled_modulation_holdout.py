"""Frozen hold-coordinate/delay model audit; not a digital hardware model.

python experiments/average-dq/run_sampled_modulation_holdout.py
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
from scipy.linalg import expm
from scipy.optimize import linear_sum_assignment

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.core.average_dq_model import build_average_dq_model, _closed_rhs, _references, _rotation, J
from backend.core.average_dq_presets import build_average_dq_ablation_anchor_case
from run_sampled_modulation_pilot import split, spectrum, lag_matrix, command, command_jacobian, relative_error

CONFIG=dict(X_pu=[0.2,0.4],D_pu=60,current_pi_factors=[0.5,1,1.5,2,3,4],
    periods_s=[1e-4,5e-4,1e-3,2e-3],holds=['local-control-dq','global-synchronous-dq'],
    delay_steps=[0,1],small_periods_s=[1e-7,2e-7,5e-7],
    map_check_factor=1.5,map_check_period_s=5e-4,map_amplitudes=[1e-5,5e-6,2.5e-6])
TOL=dict(block_relative=2e-7,F_relative=2e-7,equilibrium_absolute=1e-8,
    ideal_invariance_relative=2e-12,eigen_residual=1e-9,label_per_s=1e-5,
    step_uncertainty_multiplier=10,propagation_relative=2e-7,nonlinear_map_relative=2e-5,
    small_period_relative=0.005)
START=None


def deadline():
    if time.perf_counter()-START > 115:
        raise TimeoutError('115-second holdout deadline')


def transition(a,b,f,period,delay):
    block=np.zeros((16,16)); block[:14,:14]=a; block[:14,14:]=b
    full=expm(block*period)
    e,g=full[:14,:14],full[:14,14:]
    phi=e+g@f if delay==0 else np.block([[e,g],[f,np.zeros((2,2))]])
    return phi,e,g


def coordinates(model):
    a,b,f=split(model)
    c=np.zeros((2,14)); c[:,0]=J@model.operating_point.state[14:]
    return {'local-control-dq':(a,b,f),'global-synchronous-dq':(a-b@c,b,f+c)},c


def label_with_step(primary,secondary):
    diff=abs(primary['metric_per_s']-secondary['metric_per_s'])
    uncertainty=max(TOL['label_per_s'],TOL['step_uncertainty_multiplier']*diff)
    primary['step_metric_difference_per_s']=diff
    primary['label_uncertainty_per_s']=uncertainty
    if (abs(primary['metric_per_s'])<=uncertainty or
        primary['maximum_eigenpair_relative_residual']>TOL['eigen_residual'] or
        secondary['maximum_eigenpair_relative_residual']>TOL['eigen_residual']):
        primary['classification']='numerical-pending'
    return primary


def small_period_test(a,b,f,ideal_roots,delay):
    rows=[]
    for period in CONFIG['small_periods_s']:
        phi,_,_=transition(a,b,f,period,delay)
        values=np.linalg.eigvals(phi).astype(complex)
        inferred=np.log(values)/period
        costs=abs(ideal_roots[:,None]-inferred[None,:])
        ri,ci=linear_sum_assignment(costs)
        fast=[k for k in range(len(values)) if k not in ci]
        rows.append(dict(period_s=period,matched_slow_mode_count=len(ci),
            maximum_slow_root_absolute_error_per_s=float(max(costs[ri,ci])),
            full_log_rho_over_Ts_per_s=float(np.log(max(abs(values)))/period),
            unmatched_fast_discrete_roots=[[float(values[k].real),float(values[k].imag)] for k in fast],
            unmatched_fast_growth_rates_per_s=[float(np.log(abs(values[k]))/period) for k in fast]))
    errors=[r['maximum_slow_root_absolute_error_per_s'] for r in rows]
    relative=errors[0]/max(1,float(max(abs(ideal_roots))))
    trend=all(errors[k]<=errors[k+1]*1.02+1e-6 for k in range(2))
    fast_ok=all(all(rate<0 for rate in r['unmatched_fast_growth_rates_per_s']) for r in rows)
    return dict(rows=rows,smallest_period_relative_error=relative,
        monotone_with_period=trend,extra_fast_modes_stable=fast_ok,
        passed=relative<=TOL['small_period_relative'] and trend and fast_ok)


def linear_propagation(a,b,f,period,delay):
    phi,_,_=transition(a,b,f,period,delay)
    directions=[]
    if delay:
        directions=[np.eye(16)[0],np.eye(16)[1],np.eye(16)[14],np.eye(16)[15]]
    else:
        directions=[np.linalg.pinv(f)@axis for axis in np.eye(2)]
        directions += [np.eye(14)[0],np.eye(14)[1]]
    errors=[]
    for initial in directions:
        state=initial/np.linalg.norm(initial); exact=state.copy()
        for _ in range(3):
            deadline()
            x=state[:14]
            held=f@x if delay==0 else state[14:]
            next_held=f@x
            sol=solve_ivp(lambda _t,y:a@y+b@held,(0,period),x,
                method='DOP853',rtol=1e-10,atol=1e-12,max_step=period/8)
            if not sol.success: raise RuntimeError(sol.message)
            state=sol.y[:,-1] if delay==0 else np.concatenate([sol.y[:,-1],next_held])
            exact=phi@exact
            errors.append(relative_error(state,exact))
    return dict(cycles=3,directions=4,rtol=1e-10,atol=1e-12,max_step_s=period/8,
        maximum_relative_error=max(errors),passed=max(errors)<=TOL['propagation_relative'])


def nonlinear_map(model,initial,held_perturbation,hold,delay,period):
    eq=model.operating_point.state; delta_star=eq[0]; ustar=eq[14:]
    g=command(initial,model.parameters,model.converter)
    new_canonical=g-ustar if hold=='local-control-dq' else _rotation(-delta_star)@_rotation(initial[0])@g-ustar
    canonical=(new_canonical if delay==0 else held_perturbation)+ustar
    held_global=_rotation(delta_star)@canonical
    def rhs(_t,x):
        local=canonical if hold=='local-control-dq' else _rotation(-x[0])@held_global
        return _closed_rhs(np.concatenate([x,local]),model.operating_point.grid_voltage_global,
            _references(model.converter),model.topology,model.parameters,model.converter,model.line)[:14]
    sol=solve_ivp(rhs,(0,period),initial,method='DOP853',rtol=1e-11,atol=1e-13,max_step=period/12)
    if not sol.success: raise RuntimeError(sol.message)
    return sol.y[:,-1] if delay==0 else np.concatenate([sol.y[:,-1],new_canonical])


def nonlinear_check(model,hold,delay):
    a,b,f=coordinates(model)[0][hold]
    period=CONFIG['map_check_period_s']; phi,_,_=transition(a,b,f,period,delay)
    columns=[0,1] if delay==0 else [0,1,14,15]
    amplitudes=CONFIG['map_amplitudes'] if delay==0 else CONFIG['map_amplitudes'][:2]
    rows=[]
    for column in columns:
        for amp in amplitudes:
            endings=[]
            for sign in [-1,1]:
                deadline()
                initial=model.operating_point.state[:14].copy(); old=np.zeros(2)
                if column<14: initial[column]+=sign*amp
                else: old[column-14]+=sign*amp
                endings.append(nonlinear_map(model,initial,old,hold,delay,period))
            measured=(endings[1]-endings[0])/(2*amp)
            rows.append(dict(column=column,amplitude=amp,relative_error=relative_error(measured,phi[:,column])))
    return dict(hold=hold,delay_steps=delay,period_s=period,columns=columns,amplitudes=amplitudes,
        rtol=1e-11,atol=1e-13,max_step_s=period/12,rows=rows,
        maximum_relative_error=max(r['relative_error'] for r in rows),
        passed=max(r['relative_error'] for r in rows)<=TOL['nonlinear_map_relative'],
        note='All amplitude errors retained; numerical noise floors need not decrease monotonically.')


def main():
    global START
    START=time.perf_counter()
    output=ROOT/'results/average-dq-sampled-modulation-holdout'
    result=dict(schema='sampled-modulation-holdout/1.0',date='2026-10-02',config=CONFIG,tolerances=TOL,
        hypothesis='First-order phase-matched lag may give a different stability label from a declared sampled-command model.',
        equations=dict(rotation='R(delta)=[[cos,-sin],[sin,cos]], local=R(delta)^T global',
            global_canonical_input='h=R(delta*)^T global_held_voltage perturbation',
            C='(J*u*)*e_delta^T',global_A0='A0-B*C',global_F='F+C',
            no_delay='Phi=E+Gamma*F',one_step_delay='Phi=[[E,Gamma],[F,0]]',
            delayed_state='[x_perturbation, previous held canonical voltage perturbation]',
            comparator='same holding coordinates, first-order lag tau=(delay_steps+0.5)*Ts'),
        provenance=dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            python=sys.version,scipy=scipy.__version__,numpy=np.__version__,platform=platform.platform(),
            command='python experiments/average-dq/run_sampled_modulation_holdout.py'),
        checks=[],records=[],small_period_checks=[],linear_propagation=[],nonlinear_maps=[],
        limitations=[
            'Frozen holdout X values differ from the pilot, but both belong to one team-built single-converter model.',
            'All PI, outer-loop, measurement and phase states remain continuous; only a command envelope is held.',
            'Global-synchronous dq is not fixed physical alpha-beta/abc/PWM voltage; carrier/reference-frame implementation is not modeled.',
            'One-step delay means old held command is applied this cycle and present command is queued for the next; no other computational pipeline.',
            'Phase-matched lag is not an equivalent actuator; two coordinate choices and delays define different modeling assumptions.',
            '192 records and disagreement counts are paired deterministic model comparisons, not independent trials or probabilities.',
            'No EMT/hardware/external physical confirmation, no safe sampling-period prescription, no continuous parameter-domain theorem.',
            'Novelty not established; existing ZOH, sampled feedback and matrix-exponential methods are reused.'])
    hashes={}
    for name in [__file__,'experiments/average-dq/run_sampled_modulation_pilot.py',
                 'backend/core/average_dq_model.py','backend/core/average_dq_presets.py']:
        path=Path(name) if Path(name).is_absolute() else ROOT/name
        hashes[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    result['provenance']['source_sha256_provenance_only']=hashes
    passed=True
    try:
        for x_value in CONFIG['X_pu']:
            for factor in CONFIG['current_pi_factors']:
                deadline()
                topology,p=build_average_dq_ablation_anchor_case()
                next(line for line in topology.lines if line.id=='line-grid').reactance_pu=x_value
                p=p.model_copy(update=dict(current_proportional_gain_pu=p.current_proportional_gain_pu*factor,
                    current_integral_gain_per_s=p.current_integral_gain_per_s*factor))
                model=build_average_dq_model(topology,p,relative_step=1e-5)
                half=build_average_dq_model(topology,p,relative_step=5e-6)
                cases,c=coordinates(model); halves,_=coordinates(half)
                a,b,f=cases['local-control-dq']; ag,bg,fg=cases['global-synchronous-dq']
                eq=model.operating_point.state
                # Rotation sign and global command Jacobian independently differenced.
                h=1e-6
                derivative_rotation=(_rotation(h)-_rotation(-h))/(2*h)
                global_fd=np.empty((2,14))
                for col in range(14):
                    step=h*max(1,abs(eq[col])); plus=eq[:14].copy(); minus=plus.copy()
                    plus[col]+=step; minus[col]-=step
                    gp=_rotation(-eq[0])@_rotation(plus[0])@command(plus,p,model.converter)
                    gm=_rotation(-eq[0])@_rotation(minus[0])@command(minus,p,model.converter)
                    global_fd[:,col]=(gp-gm)/(2*step)
                check=dict(X_pu=x_value,current_pi_factor=factor,
                    original_line_R_pu=model.line.resistance_pu,
                    rotation_sign_relative_error=relative_error(derivative_rotation,J),
                    local_F_relative_error=relative_error(f,command_jacobian(eq[:14],p,model.converter)),
                    global_F_relative_error=relative_error(fg,global_fd),
                    global_command_angle_column_relative_error=relative_error(fg[:,0],global_fd[:,0]),
                    A22_relative_error=relative_error(model.linearization.closed_state_matrix[14:,14:],-np.eye(2)/p.modulation_time_constant_s),
                    command_equilibrium_error=float(max(abs(command(eq[:14],p,model.converter)-eq[14:]))),
                    ideal_coordinate_invariance_error=relative_error(ag+bg@fg,a+b@f),
                    relative_steps=[1e-5,5e-6],parameters=p.model_dump(mode='json'))
                zero_c=np.zeros_like(c)
                check['C_zero_degeneracy_negative_control']=[dict(delay_steps=d,
                    relative_transition_difference=relative_error(
                        transition(a-b@zero_c,b,f+zero_c,5e-4,d)[0],transition(a,b,f,5e-4,d)[0]))
                    for d in [0,1]]
                check['C_zero_is_algebraic_only_not_physical_freezing']=True
                check['passed']=(max(check[k] for k in ['rotation_sign_relative_error','local_F_relative_error',
                    'global_F_relative_error','A22_relative_error'])<=TOL['F_relative'] and
                    check['command_equilibrium_error']<=TOL['equilibrium_absolute'] and
                    check['ideal_coordinate_invariance_error']<=TOL['ideal_invariance_relative'])
                check['passed'] &= all(v['relative_transition_difference']<=TOL['ideal_invariance_relative']
                    for v in check['C_zero_degeneracy_negative_control'])
                result['checks'].append(check); passed &= check['passed']
                ideal_roots=np.linalg.eigvals(a+b@f)
                for hold in CONFIG['holds']:
                    a0,b0,f0=cases[hold]; a1,b1,f1=halves[hold]
                    ideal=label_with_step(spectrum(a0+b0@f0),spectrum(a1+b1@f1))
                    for delay in CONFIG['delay_steps']:
                        small=small_period_test(a0,b0,f0,ideal_roots,delay)
                        small.update(X_pu=x_value,current_pi_factor=factor,hold=hold,delay_steps=delay)
                        result['small_period_checks'].append(small); passed &= small['passed']
                        for period in CONFIG['periods_s']:
                            deadline()
                            phi,_,_=transition(a0,b0,f0,period,delay)
                            phi1,_,_=transition(a1,b1,f1,period,delay)
                            sampled=label_with_step(spectrum(phi,period),spectrum(phi1,period))
                            tau=(delay+0.5)*period
                            lag=label_with_step(spectrum(lag_matrix(a0,b0,f0,tau)),spectrum(lag_matrix(a1,b1,f1,tau)))
                            disagree=(sampled['classification']!=lag['classification'] and
                                'numerical-pending' not in [sampled['classification'],lag['classification']])
                            result['records'].append(dict(X_pu=x_value,D_pu=60,R_pu=model.line.resistance_pu,
                                current_pi_factor=factor,period_s=period,hold=hold,delay_steps=delay,
                                phase_matched_tau_s=tau,sampled=sampled,lag=lag,ideal=ideal,
                                label_disagreement=disagree,coordinate_input_basis='equilibrium local axes for both holdings'))
                            passed &= max(sampled['maximum_eigenpair_relative_residual'],lag['maximum_eigenpair_relative_residual'])<=TOL['eigen_residual']
                        if x_value==0.2 and factor==1:
                            prop=linear_propagation(a0,b0,f0,5e-4,delay)
                            prop.update(X_pu=x_value,current_pi_factor=factor,hold=hold,delay_steps=delay,period_s=5e-4)
                            result['linear_propagation'].append(prop); passed &= prop['passed']
                if factor==CONFIG['map_check_factor']:
                    for delay in [0,1]:
                        nl=nonlinear_check(model,'global-synchronous-dq',delay)
                        nl.update(X_pu=x_value,current_pi_factor=factor)
                        result['nonlinear_maps'].append(nl); passed &= nl['passed']
                print(f'X={x_value:g}, PI={factor:g}: 16 records, checks={check["passed"]}',flush=True)
    except Exception as error:
        result['error']=f'{type(error).__name__}: {error}'; passed=False
    result['record_count']=len(result['records'])
    result['lag_disagreement_count']=sum(r['label_disagreement'] for r in result['records'])
    result['pending_record_count']=sum('numerical-pending' in [r['sampled']['classification'],r['lag']['classification']] for r in result['records'])
    result['summary_by_hold_delay']=[dict(hold=hold,delay_steps=delay,
        paired_comparisons=sum(r['hold']==hold and r['delay_steps']==delay for r in result['records']),
        disagreement_count=sum(r['label_disagreement'] and r['hold']==hold and r['delay_steps']==delay for r in result['records']))
        for hold in CONFIG['holds'] for delay in CONFIG['delay_steps']]
    coordinate_pairs=delay_pairs=0; coordinate_diff=delay_diff=0
    index={(r['X_pu'],r['current_pi_factor'],r['period_s'],r['hold'],r['delay_steps']):r for r in result['records']}
    for x in CONFIG['X_pu']:
        for factor in CONFIG['current_pi_factors']:
            for period in CONFIG['periods_s']:
                for delay in [0,1]:
                    left=index.get((x,factor,period,CONFIG['holds'][0],delay)); right=index.get((x,factor,period,CONFIG['holds'][1],delay))
                    if left and right:
                        coordinate_pairs+=1; coordinate_diff+=left['sampled']['classification']!=right['sampled']['classification']
                for hold in CONFIG['holds']:
                    left=index.get((x,factor,period,hold,0)); right=index.get((x,factor,period,hold,1))
                    if left and right:
                        delay_pairs+=1; delay_diff+=left['sampled']['classification']!=right['sampled']['classification']
    result['coordinate_label_comparison']=dict(pairs=coordinate_pairs,label_differences=coordinate_diff)
    result['delay_label_comparison']=dict(pairs=delay_pairs,label_differences=delay_diff)
    result['runtime_s']=time.perf_counter()-START
    result['status']='verified-bounded-holdout' if passed and len(result['records'])==192 else 'incomplete-or-check-failed'
    output.mkdir(parents=True,exist_ok=True)
    (output/'holdout.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    lines=['# 保持坐标与一拍命令延迟：冻结参数留出预实验','',
        f'- 状态：{result["status"]}；{result["record_count"]}/192 条成对模型比较，{result["pending_record_count"]} 条待定。',
        f'- 与相同坐标的相位匹配一阶滞后标签分歧：{result["lag_disagreement_count"]} 条。',
        f'- 坐标比较 {coordinate_diff}/{coordinate_pairs} 对标签不同；延迟比较 {delay_diff}/{delay_pairs} 对不同。',
        '- 计数不是概率，各条件是同一组模型场景的重复比较。全谱及额外延迟快模态均保存在 holdout.json。',
        '- 只保持局部或全局同步dq调制包络；PI/外环连续。不是全数字、abc/PWM或实机安全周期。','',
        '|保持坐标|命令延迟拍数|成对比较|与一阶近似标签分歧|','|---|---:|---:|---:|']
    for s in result['summary_by_hold_delay']:
        lines.append(f'|{s["hold"]}|{s["delay_steps"]}|{s["paired_comparisons"]}|{s["disagreement_count"]}|')
    lines+=['','## 全部192条比较','',
        '|X|PI倍率|Ts(s)|保持|延迟拍数|采样logρ/Ts|近似alpha|采样/近似标签|','|---:|---:|---:|---|---:|---:|---:|---|']
    for r in result['records']:
        lines.append(f'|{r["X_pu"]:g}|{r["current_pi_factor"]:g}|{r["period_s"]:g}|{r["hold"]}|{r["delay_steps"]}|'
            f'{r["sampled"]["metric_per_s"]:.9g}|{r["lag"]["metric_per_s"]:.9g}|'
            f'{r["sampled"]["classification"]}/{r["lag"]["classification"]}|')
    lines+=['','## 核验和边界','',
        '- 先核原旋转R的导数符号与独立global命令Jacobian，再核理想反馈坐标不变。',
        '- 每基础点使用两种线性化步长；冻结残差门和指标差异不确定带，不强行给近界标签。',
        '- 延迟模型是16状态增广矩阵；小Ts匹配14个慢模态，同时单列2个快模态及其增率，完整稳定分类不删快根。',
        '- 4种坐标/延迟条件均有DOP853逐周期独立传播；两个不同X点有global无延迟及一拍非线性周期map差分。',
        '- 相位匹配滞后tau=(拍数+0.5)Ts仍非等价执行器；不存在物理实现优劣或安全周期结论。','',
        '```powershell','python experiments/average-dq/run_sampled_modulation_holdout.py','```','']
    lines += [f'- {v}' for v in result['limitations']]
    if 'error' in result: lines+=['',f'未完成原因：{result["error"]}']
    (output/'holdout.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=result['status'],records=result['record_count'],
        disagreements=result['lag_disagreement_count'],runtime_s=result['runtime_s']),ensure_ascii=False),flush=True)
    return 0 if result['status']=='verified-bounded-holdout' else 1


if __name__=='__main__':
    raise SystemExit(main())
