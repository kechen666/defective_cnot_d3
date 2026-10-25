"""Audit the walkthrough without modifying its source or historical results.

Run with the project Conda Python. Optional full execution saves a separate
executed notebook and retains the original notebook's default parameters.
"""
import argparse
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import sys
import time

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import patches  # Configure project-local caches before other research imports.
import numpy as np
import stim
from circuit_builder import build_cnot
from measurement_relations import SymbolicState, bits
from patches import build_patches


def snapshot():
    paths = list(HERE.glob('*.py')) + list(HERE.glob('*.ipynb'))
    paths += list((HERE / 'tests').glob('*.py'))
    paths += list((HERE / 'notebook_tools').glob('*.py'))
    paths += [p for p in (HERE / 'results').rglob('*') if p.is_file()]
    return {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def exhaustive_control_distances():
    results = {}
    for defective in (False, True):
        patch = build_patches(defective)['C']
        index = {q: i for i, q in enumerate(patch.data)}
        support_mask = lambda qs: sum(1 << index[q] for q in qs)
        actual = {}
        for basis, opposite in (('X', 'Z'), ('Z', 'X')):
            constraints = [support_mask(s.data) for s in patch.stabilizers if s.basis == opposite]
            logical = support_mask(patch.logicals[opposite])
            # Enumerate all 2**n data supports, independently of Patch.audit's DP.
            candidates = [v for v in range(1 << len(patch.data))
                          if (v & logical).bit_count() % 2 == 1
                          and all((v & s).bit_count() % 2 == 0 for s in constraints)]
            actual[basis] = min(v.bit_count() for v in candidates)
        assert actual == patch.distances
        results['defective' if defective else 'healthy'] = actual
    return results


def randomized_measurement_relations():
    rng = random.Random(20261015)
    relation_count = negative_count = 0
    for trial in range(64):
        state = SymbolicState(4)
        circuit = stim.Circuit()
        relations = []
        for q in range(4):
            circuit.append('R', [q])
            state.reset(q)
        for _ in range(80):
            gate = rng.choice(('R', 'M', 'M', 'H', 'S', 'X', 'Z', 'CX'))
            q = rng.randrange(4)
            targets = [q] if gate != 'CX' else [q, rng.choice([j for j in range(4) if j != q])]
            if gate == 'M':
                relation = state.measure(q, circuit.num_measurements)
                if relation is not None:
                    relations.append(relation)
            elif gate == 'R':
                state.reset(q)
            else:
                fragment = stim.Circuit()
                fragment.append(gate, targets)
                state.unitary(fragment)
            circuit.append(gate, targets)
        raw = circuit.compile_sampler(seed=1000 + trial).sample(128)
        for selector, sign in relations:
            observed = np.logical_xor.reduce(raw[:, list(bits(selector))], axis=1)
            assert np.all(observed == sign), (trial, selector, sign)
            relation_count += 1
            negative_count += sign
    assert negative_count > 0
    return {'circuits': 64, 'random_operations_per_circuit': 80, 'shots_per_circuit': 128,
            'deterministic_relations': relation_count, 'negative_sign_relations': negative_count,
            'all_relations_match_independent_stim_samples': True}


def circuit_inventory():
    result = {}
    for defective, case in ((False, 'healthy'), (True, 'defective')):
        for basis in 'XZ':
            exp = build_cnot(defective, (basis, basis), basis)
            active, busy = set(), set()
            data = {exp.qubit_map[q] for p in exp.patches.values() for q in p.data}
            for op in exp.operations:
                name, targets = op['name'], set(op['targets'])
                if name == 'TICK':
                    assert op['idle'] == sorted(active - busy)
                    busy.clear()
                else:
                    assert not (busy & targets)
                    busy |= targets
                    if name == 'R':
                        active |= targets & data
                    if name == 'M':
                        active -= targets & data
            assert not active
            result[case + '_' + basis] = {
                'qubits': exp.circuit.num_qubits, 'ticks': exp.circuit.num_ticks,
                'measurements': exp.circuit.num_measurements,
                'detectors': exp.circuit.num_detectors,
                'observables': exp.circuit.num_observables,
                'hardware': exp.hardware_audit(), 'stages': exp.stages,
                'frame_signs': [s for _, s in exp.output_frames],
                'native_flows': exp.verify_native_flows(),
                'idle_sets_independently_recomputed': True,
            }
    return result


def execute_notebook(output):
    import nbformat
    from nbclient import NotebookClient
    prefix = HERE / '.conda' / 'envs' / 'defective-cnot-d3'
    assert Path(sys.prefix).resolve() == prefix.resolve()
    for name, folder in {'JUPYTER_RUNTIME_DIR': 'jupyter-runtime',
                         'JUPYTER_CONFIG_DIR': 'jupyter-config',
                         'JUPYTER_DATA_DIR': 'jupyter-data', 'IPYTHONDIR': 'ipython'}.items():
        path = HERE / '.cache' / folder
        path.mkdir(parents=True, exist_ok=True)
        os.environ[name] = str(path)
    os.environ['JUPYTER_PATH'] = str(prefix / 'share' / 'jupyter')
    notebook = nbformat.read(HERE / 'defective_cnot_d3_walkthrough.ipynb', as_version=4)
    nbformat.validate(notebook)
    before = set((HERE / 'notebook_runs').iterdir())
    for cell in notebook.cells:
        if cell.cell_type == 'code':
            cell.execution_count = None
            cell.outputs = []
    NotebookClient(notebook, timeout=300, kernel_name='defective-cnot-d3',
                   resources={'metadata': {'path': str(HERE)}}, allow_errors=False).execute()
    nbformat.validate(notebook)
    codes = [c for c in notebook.cells if c.cell_type == 'code']
    assert len(codes) == 22 and all(c.execution_count is not None for c in codes)
    assert not any(o.output_type == 'error' for c in codes for o in c.outputs)
    created = [p for p in (HERE / 'notebook_runs').iterdir() if p not in before
               and (p / 'notebook_completion.json').exists()]
    assert len(created) == 1, created
    run_dir = created[0]
    completion = json.loads((run_dir / 'notebook_completion.json').read_text(encoding='utf-8'))
    current = json.loads((run_dir / 'summary.json').read_text(encoding='utf-8'))
    original = json.loads((HERE / 'results' / 'summary.json').read_text(encoding='utf-8'))
    assert completion['shots'] == 1_200_000
    assert current['statistics'] == original['statistics']
    nbformat.write(notebook, output / 'executed_walkthrough.ipynb')
    return {'code_cells': 22, 'all_executed': True, 'error_outputs': 0,
            'source_cells_modified': False, 'default_shots_per_group': 100000,
            'completion': completion, 'all_12_statistics_records_equal_historical_results': True}


def check_exported_results(run_dir):
    from scipy.stats import binomtest
    from analysis import distance_audit
    summary = json.loads((run_dir / 'summary.json').read_text(encoding='utf-8'))
    with (run_dir / 'statistics.csv').open(encoding='utf-8', newline='') as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == len(summary['statistics']) == 12
    csv_index = {(r['case'], r['basis'], float(r['p'])): r for r in rows}
    assert len(csv_index) == 12
    intervals = 0
    for r in summary['statistics']:
        flat = csv_index[r['case'], r['basis'], r['p']]
        values = {k: r[k] for k in flat if k in r}
        values.update(decoded_control_failures=r['decoded_failures_by_observable'][0],
                      decoded_target_failures=r['decoded_failures_by_observable'][1],
                      decoded_control_failure_rate=r['decoded_failure_rates_by_observable'][0],
                      decoded_target_failure_rate=r['decoded_failure_rates_by_observable'][1],
                      wilson95_low=r['decoded_wilson95'][0], wilson95_high=r['decoded_wilson95'][1])
        for name, expected in values.items():
            assert (flat[name] == expected if isinstance(expected, str)
                    else math.isclose(float(flat[name]), expected, rel_tol=1e-12, abs_tol=1e-15))
        for key, failure in [('decoded_wilson95', r['decoded_any_failures']),
                             ('raw_wilson95', r['raw_any_failures'])]:
            ci = binomtest(failure, r['shots']).proportion_ci(method='wilson')
            assert np.allclose(r[key], [ci.low, ci.high], rtol=0, atol=1e-12)
            intervals += 1
        for k, failures in enumerate(r['decoded_failures_by_observable']):
            ci = binomtest(failures, r['shots']).proportion_ci(method='wilson')
            assert np.allclose(r['decoded_wilson95_by_observable'][k], [ci.low, ci.high], rtol=0, atol=1e-12)
            intervals += 1
    distances = {}
    max_dem_argument_difference = 0.
    for case in ('healthy', 'defective'):
        for basis in 'XZ':
            stem = run_dir / case / f'cnot_{basis}'
            noisy = stim.Circuit(stem.with_suffix('.noisy.stim').read_text(encoding='utf-8'))
            full = stim.DetectorErrorModel(stem.with_suffix('.full.dem').read_text(encoding='utf-8'))
            matching = stim.DetectorErrorModel(stem.with_suffix('.matching.dem').read_text(encoding='utf-8'))
            rebuilt = [noisy.detector_error_model(decompose_errors=False, allow_gauge_detectors=False),
                       noisy.detector_error_model(decompose_errors=True, allow_gauge_detectors=False,
                                                  ignore_decomposition_failures=False)]
            for stored, recomputed in zip((full, matching), rebuilt):
                a, b = list(stored.flattened()), list(recomputed.flattened())
                assert len(a) == len(b)
                for old, new in zip(a, b):
                    assert old.type == new.type and old.targets_copy() == new.targets_copy()
                    assert len(old.args_copy()) == len(new.args_copy())
                    for x, y in zip(old.args_copy(), new.args_copy()):
                        max_dem_argument_difference = max(max_dem_argument_difference, abs(x-y))
                        # Text round-trips can alter the last floating-point bit.
                        assert math.isclose(x, y, rel_tol=0, abs_tol=1e-15)
            meta = json.loads(stem.with_suffix('.metadata.json').read_text(encoding='utf-8'))
            actual = distance_audit(noisy)
            assert actual == meta['distance'] == summary['distances'][case + '_' + basis]
            distances[case + '_' + basis] = actual['distance']
    return {'run_directory': str(run_dir.resolve()), 'csv_json_records_equal': 12,
            'wilson_intervals_checked_against_scipy': intervals,
            'exported_dems_checked': 8, 'dem_target_structure_exactly_equal': True,
            'dem_argument_absolute_tolerance': 1e-15,
            'maximum_dem_argument_absolute_difference': max_dem_argument_difference,
            'distances_recomputed_from_exported_circuits': distances}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-notebook', action='store_true')
    parser.add_argument('--results', type=Path, help='Additionally recompute CSV, Wilson, DEM and distance evidence.')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    out = args.out or Path(__file__).parent / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    out.mkdir(parents=True, exist_ok=False)
    before = snapshot()
    start = time.monotonic()
    report = {'date_local': datetime.now(timezone(timedelta(hours=8))).date().isoformat(),
              'python': sys.version, 'executable': sys.executable,
              'versions': {p: importlib.metadata.version(p) for p in ('stim', 'pymatching', 'numpy', 'tqec')}}
    report['exhaustive_control_distances'] = exhaustive_control_distances()
    report['symbolic_relations'] = randomized_measurement_relations()
    report['circuits'] = circuit_inventory()
    print('Independent algebra, signed relations, and idle-set checks passed.', flush=True)
    if args.execute_notebook:
        print('Executing all original notebook cells, 100000 shots per group...', flush=True)
        report['notebook'] = execute_notebook(out)
    if args.results:
        report['exported_results'] = check_exported_results(args.results)
    assert snapshot() == before, 'An original code/notebook/result file changed.'
    report['original_code_notebook_tests_and_results_unchanged'] = True
    report['elapsed_seconds'] = round(time.monotonic() - start, 3)
    (out / 'verification.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Verified; report:', out / 'verification.json', flush=True)


if __name__ == '__main__':
    main()
