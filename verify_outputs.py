"""Read delivered artifacts independently and check circuits, records and counts."""
import argparse
import hashlib
import json
from pathlib import Path
import stim
from patches import HERE, DEAD
from run_experiment import write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,default=HERE/'results')
    args=parser.parse_args()
    summary=json.loads((args.results/'summary.json').read_text(encoding='utf-8'))
    rows=summary['statistics']
    assert len(rows)==12
    assert len({(r['case'],r['basis'],r['p']) for r in rows})==12
    for r in rows:
        assert r['shots']==summary['config']['shots_per_group']
        assert r['decoded_any_failures']/r['shots']==r['decoded_failure_rate']
        assert r['decoded_wilson95'][0]<=r['decoded_failure_rate']<=r['decoded_wilson95'][1]
        assert r['decoded_any_failures']>=max(r['decoded_failures_by_observable'])
        assert r['decoded_any_failures']<=sum(r['decoded_failures_by_observable'])
    report={'total_shots':sum(r['shots'] for r in rows),'circuits':{},'tqec':{}}
    for case in ('healthy','defective'):
        for basis in 'XZ':
            folder=args.results/case
            clean=stim.Circuit((folder/f'cnot_{basis}.stim').read_text(encoding='utf-8'))
            noisy=stim.Circuit((folder/f'cnot_{basis}.noisy.stim').read_text(encoding='utf-8'))
            meta=json.loads((folder/f'cnot_{basis}.metadata.json').read_text(encoding='utf-8'))
            assert hashlib.sha256(str(clean).encode()).hexdigest()==meta['sha256']
            assert clean.num_measurements==noisy.num_measurements==meta['measurements']
            assert clean.num_detectors==noisy.num_detectors==meta['detectors']
            coords={v['id']:v['coordinate'] for v in meta['qubit_map']}
            if case=='defective':
                assert list(DEAD) not in coords.values()
            busy=set()
            for instruction in noisy:
                name=instruction.name
                ids=[t.value for t in instruction.targets_copy() if t.is_qubit_target]
                assert all(i in coords for i in ids)
                if name=='CX':
                    for a,b in zip(ids[::2],ids[1::2]):
                        u,v=coords[a],coords[b]
                        assert abs(u[0]-v[0])==abs(u[1]-v[1])==1
                if name=='TICK':
                    busy.clear()
                elif name in ('R','M','H','X','Z','CX'):
                    assert not busy.intersection(ids)
                    busy.update(ids)
            clean.detector_error_model(allow_gauge_detectors=False)
            noisy.detector_error_model(decompose_errors=True,ignore_decomposition_failures=False)
            det,obs=clean.compile_detector_sampler(seed=123).sample(1024,separate_observables=True)
            assert not det.any() and not obs.any()
            harness=stim.Circuit((folder/f'ideal_choi_verification_only_{basis}.stim').read_text(encoding='utf-8'))
            for cert in meta['signed_choi_flow_certificate'].values():
                p=stim.PauliString(cert['correlation'])
                p.sign*=(-1)**cert['sign']
                assert harness.has_flow(stim.Flow(output=p,measurements=cert['measurements']))
            report['circuits'][f'{case}_{basis}']={'noiseless_shots':1024,'detector_events':0,
                'observable_flips':0,'native_flows':True,'local_edges':True,'moment_conflicts':0,
                'measurements':clean.num_measurements,'ticks':clean.num_ticks,'distance':meta['distance']['distance']}
    tqec=args.results/'tqec_reference'
    validation=json.loads((tqec/'validation.json').read_text(encoding='utf-8'))
    for basis in 'XZ':
        circuit=stim.Circuit((tqec/f'cnot_{basis}.stim').read_text(encoding='utf-8'))
        det,obs=circuit.compile_detector_sampler(seed=321).sample(1024,separate_observables=True)
        assert not det.any() and not obs.any()
        report['tqec'][basis]=validation[basis]
    write_json(args.results/'delivery_validation.json',report)
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
