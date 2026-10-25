"""Export physical circuits and run the predeclared complete-CNOT experiment."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

import numpy as np
from circuit_builder import build_cnot
from analysis import add_noise, distance_audit, sample_decode
from measurement_relations import bits
from patches import HERE, DEAD, PauliT


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def write_stim(path, value):
    # Stim's native fopen path overload does not support Unicode Windows paths.
    # Python's Unicode-aware I/O works for both circuits and DEMs.
    path.write_text(str(value)+'\n',encoding='utf-8')


def validate_noiseless(exp, shots=1024, seed=7013):
    exp.circuit.detector_error_model(allow_gauge_detectors=False)
    detectors, observables = exp.circuit.compile_detector_sampler(seed=seed).sample(
        shots, separate_observables=True)
    assert not detectors.any() and not observables.any()
    flows = exp.verify_native_flows()
    assert all(flows.values())
    return {'shots': shots, 'seed': seed, 'detector_events': int(detectors.sum()),
            'observable_flips': int(observables.sum()), 'native_signed_choi_flows': flows,
            'hardware': exp.hardware_audit()}


def export_experiment(exp, folder, basis):
    folder.mkdir(parents=True, exist_ok=True)
    stem = folder / f'cnot_{basis}'
    write_stim(Path(str(stem)+'.stim'),exp.circuit)
    noisy = add_noise(exp, 1e-3)
    write_stim(Path(str(stem)+'.noisy.stim'),noisy)
    write_stim(Path(str(stem)+'.full.dem'),noisy.detector_error_model(decompose_errors=False))
    write_stim(Path(str(stem)+'.matching.dem'),noisy.detector_error_model(decompose_errors=True, ignore_decomposition_failures=False))
    write_stim(folder / f'ideal_choi_verification_only_{basis}.stim',exp.choi_harness)
    write_json(folder / f'cnot_{basis}.metadata.json', {
        'nominal_distance': 3, 'defective': exp.defective, 'input_bases': [basis,basis],
        'output_basis': basis, 'qubits': exp.circuit.num_qubits, 'ticks': exp.circuit.num_ticks,
        'measurements': exp.circuit.num_measurements, 'detectors': exp.circuit.num_detectors,
        'observables': exp.circuit.num_observables,
        'qubit_map': [{'coordinate': q, 'id': i} for q,i in exp.qubit_map.items()],
        'stages': exp.stages, 'operations': exp.operations, 'measurements_index': exp.records,
        'final_logical_selectors': [list(bits(v)) for v in exp.output_records],
        'output_frames': [{'measurements': list(bits(v)), 'sign': s} for v,s in exp.output_frames],
        'observable_selectors': [{'measurements': list(bits(v)), 'sign': s} for v,s in exp.observable_selectors],
        'signed_choi_flow_certificate': exp.flow_certificate,
        'noiseless_validation': validate_noiseless(exp),
        'distance': distance_audit(noisy),
        'sha256': hashlib.sha256(str(exp.circuit).encode()).hexdigest(),
    })
    return distance_audit(noisy)


def export_patches(patches, folder):
    from defects_module.utils import memory_program, standard_noise
    write_json(folder/'patches.json', {name: {
        'data': p.data, 'checks': [vars(c) for c in p.checks],
        'stabilizers': [(s.basis, s.data) for s in p.stabilizers],
        'bare_logicals': p.logicals, 'audit': p.audit()} for name,p in patches.items()})
    audits = {}
    for basis in 'XZ':
        original = memory_program(patches['C'].source, standard_noise(0), getattr(PauliT,basis), rounds=6)
        circuit = original.stim_circuit
        write_stim(folder/f'snl_memory_{basis}.stim',circuit)
        circuit.detector_error_model(allow_gauge_detectors=False)
        detectors, obs = circuit.compile_detector_sampler(seed=713).sample(1024,separate_observables=True)
        assert not detectors.any() and not obs.any()
        audits[basis] = {'shots':1024, 'detector_events':int(detectors.sum()), 'observable_flips':int(obs.sum())}
    write_json(folder/'snl_memory_validation.json',audits)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shots', type=int, default=100000)
    parser.add_argument('--seed', type=int, default=20261013)
    parser.add_argument('--out', type=Path, default=HERE/'results')
    parser.add_argument('--overwrite', action='store_true', help='Explicitly replace an existing result set.')
    args = parser.parse_args()
    if args.shots <= 0:
        parser.error('--shots must be positive')
    if (args.out/'summary.json').exists() and not args.overwrite:
        parser.error('Result set exists; choose another --out directory or explicitly use --overwrite.')
    config = {'nominal_distance':3, 'defect':{'patch':'C','global':DEAD,'local':(3,3),'kind':'permanent data qubit'},
              'stage_rounds':6, 'probabilities':[1e-4,1e-3,3e-3], 'shots_per_group':args.shots,
              'noise':{'R':'X_ERROR(p) after R', 'M':'M(p)', 'H,X,Z':'DEPOLARIZE1(p)',
                       'CX':'DEPOLARIZE2(p)', 'idle':'DEPOLARIZE1(p) on active healthy data at each idle TICK'},
              'seed_base':args.seed, 'seed_formula':'seed_base + 100*case_index + 10*basis_index + p_index',
              'python':platform.python_version(), 'versions':{p:importlib.metadata.version(p) for p in
                       ('numpy','stim','pymatching','tqec','tqecd','matplotlib','pytest')},
              'sources':json.loads((HERE/'sources.json').read_text(encoding='utf-8'))}
    write_json(args.out/'config.json',config)
    rows, distances = [], {}
    for ci, defective in enumerate((False,True)):
        case = 'defective' if defective else 'healthy'
        folder = args.out/case
        for bi, basis in enumerate('XZ'):
            exp = build_cnot(defective,(basis,basis),basis)
            distance = export_experiment(exp,folder,basis)
            distances[f'{case}_{basis}'] = distance
            if bi == 0:
                export_patches(exp.patches,folder)
            for pi, p in enumerate(config['probabilities']):
                seed = args.seed + 100*ci + 10*bi + pi
                stats = sample_decode(add_noise(exp,p),args.shots,seed)
                row = {'case':case, 'basis':basis, 'p':p, 'ticks':exp.circuit.num_ticks, **stats}
                rows.append(row)
                print(f'{case} {basis} p={p:g}: {stats["decoded_any_failures"]}/{args.shots} decoded failures',flush=True)
        for basis in 'XZ':
            bell = build_cnot(defective,('X','Z'),basis)
            validation = validate_noiseless(bell)
            raw = bell.circuit.compile_sampler(seed=881).sample(1024)
            corrected = bell.corrected_output_bits(raw)
            assert np.all(corrected[:,0] == corrected[:,1])
            validation['corrected_bell_parity_failures'] = int(np.logical_xor(*corrected.T).sum())
            write_stim(folder/f'bell_{basis}.stim',bell.circuit)
            write_json(folder/f'bell_{basis}.validation.json',validation)
    write_json(args.out/'summary.json',{'config':config, 'distances':distances,'statistics':rows})
    fields = ['case','basis','p','shots','seed','ticks','raw_any_failures','decoded_any_failures',
              'raw_failure_rate','decoded_failure_rate','decoded_control_failures','decoded_target_failures',
              'decoded_control_failure_rate','decoded_target_failure_rate',
              'wilson95_low','wilson95_high']
    with (args.out/'statistics.csv').open('w',newline='',encoding='utf-8') as f:
        writer = csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        for row in rows:
            flat = {k:row[k] for k in fields if k in row}
            flat.update(decoded_control_failures=row['decoded_failures_by_observable'][0],
                        decoded_target_failures=row['decoded_failures_by_observable'][1],
                        decoded_control_failure_rate=row['decoded_failure_rates_by_observable'][0],
                        decoded_target_failure_rate=row['decoded_failure_rates_by_observable'][1],
                        wilson95_low=row['decoded_wilson95'][0],wilson95_high=row['decoded_wilson95'][1])
            writer.writerow(flat)
    print(f'Complete: {len(rows)*args.shots} shots; results at {args.out}',flush=True)


if __name__ == '__main__':
    main()
