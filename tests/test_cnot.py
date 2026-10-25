import itertools
import numpy as np
import pytest


@pytest.mark.parametrize('defective', [False, True])
@pytest.mark.parametrize('basis', ['X', 'Z'])
def test_signed_cnot_truth_tables(defective, basis):
    from circuit_builder import build_cnot
    for c, t in itertools.product([0, 1], repeat=2):
        exp = build_cnot(defective, (basis, basis), basis, (c, t))
        exp.circuit.detector_error_model(allow_gauge_detectors=False)
        d, o = exp.circuit.compile_detector_sampler(seed=7).sample(128, separate_observables=True)
        assert not d.any() and not o.any()
        raw = exp.circuit.compile_sampler(seed=8).sample(128)
        corrected = exp.corrected_output_bits(raw)
        want = (c, c ^ t) if basis == 'Z' else (c ^ t, t)
        assert np.all(corrected == want)
        assert set(exp.flow_certificate) == {'XC', 'XT', 'ZC', 'ZT'}
        assert exp.hardware_audit()['dead_qubit_operations'] == 0


@pytest.mark.parametrize('defective', [False, True])
@pytest.mark.parametrize('basis', ['X', 'Z'])
def test_cnot_entangles_plus_zero(defective, basis):
    from circuit_builder import build_cnot
    exp = build_cnot(defective, ('X', 'Z'), basis)
    raw = exp.circuit.compile_sampler(seed=99).sample(128)
    corrected = exp.corrected_output_bits(raw)
    assert np.all(corrected[:, 0] == corrected[:, 1])
    _, o = exp.circuit.compile_detector_sampler(seed=9).sample(128, separate_observables=True)
    assert not o.any()


def test_gate_has_only_local_elementary_operations():
    from circuit_builder import build_cnot
    exp = build_cnot(True, ('Z', 'Z'), 'Z')
    names = {i.name for i in exp.circuit}
    assert 'MPP' not in names
    assert exp.hardware_audit()['two_qubit_edges_local']


@pytest.mark.parametrize('defective', [False, True])
def test_native_stim_verifies_all_four_signed_choi_flows(defective):
    from circuit_builder import build_cnot
    exp = build_cnot(defective)
    assert exp.verify_native_flows() == {'XC': True, 'XT': True, 'ZC': True, 'ZT': True}
