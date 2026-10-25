"""Compile the pinned TQEC gallery CNOT at k=1 (d=3), as a separate reference."""
import argparse
from pathlib import Path
import patches  # Configure all caches inside the workspace before importing TQEC.
from tqec import Basis, NoiseModel, compile_block_graph
from tqec.gallery import cnot
from run_experiment import write_json, write_stim


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=patches.HERE/'results'/'tqec_reference')
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    report={}
    for basis in 'XZ':
        print(f'Compiling TQEC {basis}, k=1...',flush=True)
        graph=cnot(getattr(Basis,basis))
        compiled=compile_block_graph(graph)
        clean=compiled.generate_stim_circuit(k=1,database_path=patches.HERE/'.cache'/'detectors.pkl')
        noisy=NoiseModel.uniform_depolarizing(0.001).noisy_circuit(clean)
        write_stim(args.out/f'cnot_{basis}.stim',clean)
        write_stim(args.out/f'cnot_{basis}.noisy.stim',noisy)
        write_stim(args.out/f'cnot_{basis}.dem',noisy.detector_error_model(decompose_errors=True,ignore_decomposition_failures=False))
        clean.detector_error_model(allow_gauge_detectors=False)
        det,obs=clean.compile_detector_sampler(seed=793).sample(1024,separate_observables=True)
        assert not det.any() and not obs.any()
        distance=len(noisy.shortest_graphlike_error())
        assert distance == 3
        report[basis]={'k':1,'nominal_distance':3,'graphlike_upper_bound':distance,
                       'qubits':clean.num_qubits,'ticks':clean.num_ticks,'observables':clean.num_observables,
                       'shots':1024,'detector_events':int(det.sum()),'observable_flips':int(obs.sum()),
                       'role':'separate ideal-chip structural reference, different schedule and noise; not paired LER control'}
    write_json(args.out/'validation.json',report)
    print(report,flush=True)


if __name__ == '__main__':
    main()
