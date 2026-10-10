"""One fixed pair of spline/SLSQP trials; sampled feasibility, not a global proof."""
from __future__ import annotations

import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import scipy
from scipy.integrate import solve_ivp
from scipy.interpolate import BSpline
from scipy.optimize import minimize

from run_power_feasibility import K, ROOT, VG, build_case

PLAN = ROOT / "results/phase-jump-power-feasibility/constrained-ocp-plan-2026-10-05.md"
OUTPUT = ROOT / "results/phase-jump-power-feasibility/constrained-ocp-2026-10-05"
T = .06
DEGREE = 5
INTERNAL = np.array([.00005, .0001, .0002, .0004, .0008, .0015,
                     .003, .006, .01, .015, .025, .04])
TOL = 1e-7


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def grid(dense=False):
    return np.unique(np.r_[np.linspace(0, .005, 2001 if dense else 101),
                           np.linspace(.005, T, 6001 if dense else 221), INTERNAL])


class SplineProblem:
    def __init__(self):
        self.case = build_case(60., "poi")
        self.knots = np.r_[np.zeros(6), INTERNAL / T, np.ones(6)]
        self.n = len(self.knots) - DEGREE - 1
        self.basis = BSpline(self.knots, np.eye(self.n), DEGREE)
        self.free = np.arange(3, self.n - 3)
        self.nvar = 2 * len(self.free)
        c = self.case
        a = -c["wb"] * c["rt"] / c["lt"] * np.eye(2) - c["wb"] * K
        di0 = a @ c["i0"] + c["wb"] / c["lt"] * (c["frozen"] - VG)
        ddi0 = a @ di0
        endpoints = np.vstack([self.basis(0), self.basis(0, nu=1),
                               self.basis(0, nu=2), self.basis(1),
                               self.basis(1, nu=1), self.basis(1, nu=2)])
        fixed_indices = np.r_[np.arange(3), np.arange(self.n - 3, self.n)]
        target = np.array([c["i0"], T * di0, T*T * ddi0, c["iss"], [0., 0.], [0., 0.]])
        self.fixed = np.zeros((self.n, 2))
        self.fixed[fixed_indices] = np.linalg.solve(endpoints[:, fixed_indices], target)
        if np.max(np.abs(endpoints[:, self.free])) > 1e-9:
            raise AssertionError("Free coefficients influence endpoint conditions")
        # Fixed before either solve: linear Greville control points, endpoint blocks eliminated.
        greville = np.array([np.mean(self.knots[j+1:j+6]) for j in range(self.n)])
        initial = (1-greville[:, None])*c["i0"] + greville[:, None]*c["iss"]
        self.x0 = initial[self.free].ravel()
        self.times = grid()
        self.train = self.matrices(self.times)
        dt = np.diff(self.times)
        self.weights = np.r_[dt[0]/2, (dt[:-1]+dt[1:])/2, dt[-1]/2]
        steady_v = VG + c["rt"] * c["iss"] + c["lt"] * K @ c["iss"]
        self.reference = steady_v + (c["frozen"]-steady_v)*np.exp(-self.times[:, None]/.02)

    def coefficients(self, x):
        coef = self.fixed.copy()
        coef[self.free] = np.asarray(x).reshape(-1, 2)
        return coef

    def matrices(self, times):
        c = self.case
        b = [self.basis(times/T, nu=j)/T**j for j in range(3)]
        offset = [bj @ self.fixed for bj in b]
        jac = [np.stack([np.kron(row[self.free], np.eye(2)) for row in bj]) for bj in b]
        vc0 = VG + c["rt"]*offset[0] + c["lt"]*(offset[0] @ K.T) + c["lt"]/c["wb"]*offset[1]
        vj = c["rt"]*jac[0] + c["lt"]*np.einsum("ab,mbn->man", K, jac[0]) + c["lt"]/c["wb"]*jac[1]
        dv0 = c["rt"]*offset[1] + c["lt"]*(offset[1] @ K.T) + c["lt"]/c["wb"]*offset[2]
        dvj = c["rt"]*jac[1] + c["lt"]*np.einsum("ab,mbn->man", K, jac[1]) + c["lt"]/c["wb"]*jac[2]
        return dict(i0=offset[0], ij=jac[0], v0=vc0, vj=vj, dv0=dv0, dvj=dvj)

    def fields(self, x, mat=None):
        m = self.train if mat is None else mat
        return tuple(m[k+"0"] + np.einsum("man,n->ma", m[k+"j"], x) for k in ["i", "v", "dv"])

    def objective(self, x):
        _, v, dv = self.fields(x)
        e = v-self.reference
        return float(np.dot(self.weights, np.sum(e*e, axis=1)+1e-4*np.sum(dv*dv, axis=1)))

    def gradient(self, x):
        _, v, dv = self.fields(x)
        return 2*np.einsum("m,ma,man->n", self.weights, v-self.reference, self.train["vj"]) + 2e-4*np.einsum("m,ma,man->n", self.weights, dv, self.train["dvj"])

    def constraints(self, x, hard_power):
        c = self.case
        i, v, _ = self.fields(x)
        parts = [1.3**2-np.sum(i*i, axis=1), np.dot(c["frozen"], c["frozen"])-np.sum(v*v, axis=1)]
        if hard_power:
            poi = c["alpha"]*v+c["beta"]*VG+c["correction"]*i
            parts.append(np.sum(poi*i, axis=1)-c["ppre"])
        return np.concatenate(parts)

    def constraint_jacobian(self, x, hard_power):
        c = self.case
        i, v, _ = self.fields(x)
        ij, vj = self.train["ij"], self.train["vj"]
        parts = [-2*np.einsum("ma,man->mn", i, ij), -2*np.einsum("ma,man->mn", v, vj)]
        if hard_power:
            poi = c["alpha"]*v+c["beta"]*VG+c["correction"]*i
            pj = c["alpha"]*vj+c["correction"]*ij
            parts.append(np.einsum("ma,man->mn", poi, ij)+np.einsum("ma,man->mn", i, pj))
        return np.vstack(parts)

    def check(self, x, times):
        i, v, dv = self.fields(x, self.matrices(times))
        c = self.case
        poi = c["alpha"]*v+c["beta"]*VG+c["correction"]*i
        current, voltage, power = np.linalg.norm(i, axis=1), np.linalg.norm(v, axis=1), np.sum(poi*i, axis=1)
        im, vm, pm = np.argmax(current), np.argmax(voltage), np.argmin(power)
        coef = self.coefficients(x)
        spline = BSpline(self.knots, coef, DEGREE)
        a = -c["wb"]*c["rt"]/c["lt"]*np.eye(2)-c["wb"]*K
        di0 = a@c["i0"]+c["wb"]/c["lt"]*(c["frozen"]-VG)
        ends = dict(start_i=float(np.linalg.norm(spline(0)-c["i0"])),
                    end_i=float(np.linalg.norm(spline(1)-c["iss"])),
                    start_di=float(np.linalg.norm(spline(0, nu=1)/T-di0)),
                    end_di=float(np.linalg.norm(spline(1, nu=1)/T)),
                    start_ddi=float(np.linalg.norm(spline(0, nu=2)/T**2-a@di0)),
                    end_ddi=float(np.linalg.norm(spline(1, nu=2)/T**2)),
                    start_v=float(np.linalg.norm(v[0]-c["frozen"])),
                    start_dv=float(np.linalg.norm(dv[0])), end_dv=float(np.linalg.norm(dv[-1])))
        return dict(grid_count=len(times), current_peak_pu=float(current[im]), current_peak_time_s=float(times[im]),
                    voltage_peak_pu=float(voltage[vm]), voltage_peak_time_s=float(times[vm]),
                    power_min_pu=float(power[pm]), power_min_time_s=float(times[pm]),
                    current_pass=bool(current[im]<=1.3+TOL),
                    voltage_pass=bool(voltage[vm]<=np.linalg.norm(c["frozen"])+TOL),
                    power_pass=bool(power[pm]>=c["ppre"]-TOL), endpoint_errors=ends,
                    endpoint_units=dict(start_i="p.u.", end_i="p.u.", start_di="p.u./s", end_di="p.u./s",
                                        start_ddi="p.u./s^2", end_ddi="p.u./s^2", start_v="p.u.",
                                        start_dv="p.u./s", end_dv="p.u./s"),
                    endpoint_pass=bool(max(ends[k] for k in ["start_i", "end_i", "start_v", "start_dv", "end_dv"])<=TOL),
                    endpoint_pass_scope="Current/voltage continuity and voltage derivative continuity; raw di/ddi residuals reported separately with units")


def solve_once(problem, hard_power):
    started = time.monotonic()
    accepted = problem.x0.copy()
    iterations = []

    def budget():
        if time.monotonic()-started > 30:
            raise TimeoutError("30-second fixed strategy budget")

    def objective(x):
        budget()
        return problem.objective(x)

    def gradient(x):
        budget()
        return problem.gradient(x)

    def con(x):
        budget()
        return problem.constraints(x, hard_power)

    def jac(x):
        budget()
        return problem.constraint_jacobian(x, hard_power)

    def callback(x):
        nonlocal accepted
        accepted = x.copy()
        iterations.append(dict(iteration=len(iterations)+1, elapsed_seconds=time.monotonic()-started,
                               objective=problem.objective(x), min_sampled_constraint=float(problem.constraints(x, hard_power).min())))
        budget()

    try:
        solved = minimize(objective, problem.x0.copy(), jac=gradient, method="SLSQP",
                          constraints=dict(type="ineq", fun=con, jac=jac), callback=callback,
                          options=dict(maxiter=150, ftol=1e-10, disp=False))
        x = solved.x
        state = dict(status=int(solved.status), message=str(solved.message), success=bool(solved.success),
                     iterations=int(solved.nit), function_evaluations=int(solved.nfev), termination="optimizer-returned")
    except TimeoutError as exc:
        x = accepted
        state = dict(status=None, message=str(exc), success=False, iterations=len(iterations), termination="budget-exceeded-last-accepted-iterate")
    elapsed = time.monotonic()-started
    train = problem.check(x, problem.times)
    dense = problem.check(x, grid(True))
    dense_pass = dense["current_pass"] and dense["voltage_pass"] and dense["endpoint_pass"] and (dense["power_pass"] or not hard_power)
    result = dict(strategy="with-power-floor" if hard_power else "voltage-only",
                  hard_power_constraint=hard_power, optimizer=state, optimizer_elapsed_seconds=elapsed,
                  objective=problem.objective(x), train_check=train, dense_check=dense,
                  dense_strategy_constraints_pass=dense_pass, dense_all_three_constraints_pass=dense_pass and dense["power_pass"],
                  knots_s=(problem.knots*T).tolist(), degree=DEGREE,
                  coefficients=problem.coefficients(x).tolist(), iteration_history=iterations)
    if dense_pass and dense["power_pass"]:
        result["independent_RL_integration"] = reintegrate(problem, x)
    return result


def reintegrate(problem, x):
    c = problem.case
    spline = BSpline(problem.knots, problem.coefficients(x), DEGREE)

    def voltage(t):
        i, di = spline(t/T), spline(t/T, nu=1)/T
        return VG+c["rt"]*i+c["lt"]*K@i+c["lt"]/c["wb"]*di

    def rhs(t, i):
        return c["wb"]/c["lt"]*(voltage(t)-VG-c["rt"]*i)-c["wb"]*K@i

    times = grid(True)
    target = spline(times/T)
    solved = solve_ivp(rhs, (0, T), c["i0"], method="DOP853", rtol=1e-11, atol=1e-13,
                       max_step=.000025, t_eval=times)
    error = float(np.max(np.abs(solved.y.T-target))) if solved.success and len(solved.t)==len(times) else None
    return dict(method="DOP853", success=bool(solved.success), message=str(solved.message),
                max_absolute_state_error_pu=error, state_error_pass=error is not None and error<=TOL)


def main():
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    sources = [Path(__file__), PLAN, ROOT/"experiments/phase-jump/run_power_feasibility.py",
               ROOT/"references/papers/Awal-et-al-2026-phase-jump-overload-arxiv-2607.07904v1.pdf"]
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in sources}
    expected_pdf = "a3639891dce05a209ec98d39c34c77875abab552de32e66cd39e7f638da3a69f"
    if hashes[str(sources[-1].relative_to(ROOT))] != expected_pdf:
        raise AssertionError("Original PDF differs from registered v1 hash")
    p = SplineProblem()
    OUTPUT.mkdir()
    started = time.monotonic()
    result = dict(status="running", source_hashes=hashes, environment=dict(python=platform.python_version(),
                  numpy=np.__version__, scipy=scipy.__version__),
                  configuration=dict(T_s=T, degree=DEGREE, knot_vector_normalized=p.knots.tolist(),
                  internal_knots_s=INTERNAL.tolist(), variable_count=p.nvar, tau_s=.02, wT=10., wr=1e-4,
                  terminal_penalty_zero_by_hard_endpoint=True, maxiter=150, seconds_per_strategy=30,
                  ftol=1e-10, check_tolerance=TOL, train_times_s=p.times.tolist(), dense_times_s=grid(True).tolist(),
                  initial_choice="linear-current Greville control points with first/last three fixed by endpoints"),
                  case={k:v.tolist() if isinstance(v, np.ndarray) else v for k,v in p.case.items()},
                  initial_coefficients=p.coefficients(p.x0).tolist(), initial_check=p.check(p.x0, p.times), strategies=[],
                  caveats=["Finite sampled constraints, not continuous-time proof", "Hard power floor is nonconvex; SLSQP has no global optimality guarantee",
                           "Narrower spline and hard endpoint family, not complete author OCP reproduction", "No inverter-side or DC/modulation hardware ratings confirmed"])

    def save():
        target = OUTPUT/"result.json"
        target.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        if json.loads(target.read_text(encoding="utf-8"))["source_hashes"] != hashes:
            raise AssertionError("Result readback failed")

    save()
    try:
        for hard in [False, True]:
            row = solve_once(p, hard)
            result["strategies"].append(row)
            save()
            print(json.dumps({"strategy":row["strategy"], "optimizer":row["optimizer"], "dense":row["dense_check"]}), flush=True)
        if hashes != {str(s.relative_to(ROOT)):sha(s) for s in sources}:
            raise AssertionError("Sources changed during computation")
        result["status"] = "complete" if all(r["optimizer"]["termination"]=="optimizer-returned" for r in result["strategies"]) else "incomplete-budget"
        baseline, modified = result["strategies"]
        result["paired_evidence_observed"] = bool(baseline["dense_strategy_constraints_pass"] and not baseline["dense_check"]["power_pass"] and modified["dense_all_three_constraints_pass"])
    except Exception as exc:
        result["status"] = "execution-failed"
        result["failure"] = repr(exc)
        raise
    finally:
        result["elapsed_seconds"] = time.monotonic()-started
        save()
    print(json.dumps({"status":result["status"], "paired_evidence_observed":result["paired_evidence_observed"], "elapsed_seconds":result["elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
