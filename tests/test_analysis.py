import stim
import pytest


def test_hypergraph_low_weight_search_uses_full_faults():
    from analysis import low_weight_distance
    dem = stim.DetectorErrorModel('error(0.1) D0 D1 D2\nerror(0.1) D0 D1 D2 L0')
    result = low_weight_distance(dem)
    assert result['distance'] == 2
    assert len(result['witness']) == 2
    assert low_weight_distance(stim.DetectorErrorModel('error(0.1) L0'))['distance'] == 1


@pytest.mark.parametrize('defective', [False, True])
@pytest.mark.parametrize('basis', ['X', 'Z'])
def test_noise_and_decoder_use_consistent_records(defective, basis):
    from circuit_builder import build_cnot
    from analysis import add_noise, sample_decode
    exp = build_cnot(defective, (basis,basis), basis)
    noisy = add_noise(exp, 1e-3)
    assert noisy.num_measurements == exp.circuit.num_measurements
    noisy.detector_error_model(decompose_errors=True, ignore_decomposition_failures=False)
    data = sample_decode(noisy, 2048, 44)
    assert 0 <= data['decoded_any_failures'] <= 2048
    assert data['shots'] == 2048
    dead = exp.qubit_map.get((3,11))
    if defective and dead is not None:
        assert all(dead not in [t.value for t in op.targets_copy() if t.is_qubit_target] for op in noisy)


def test_noise_rejects_invalid_probability():
    from circuit_builder import build_cnot
    from analysis import add_noise
    with pytest.raises(ValueError):
        add_noise(build_cnot(), -1)


def test_zero_noise_reports_per_output_rates_and_nonzero_uncertainty():
    from circuit_builder import build_cnot
    from analysis import sample_decode
    stats=sample_decode(build_cnot().circuit,256,99)
    assert stats['decoded_failure_rates_by_observable'] == [0.,0.]
    assert stats['decoded_wilson95'][0] == 0.
    assert 0 < stats['decoded_wilson95'][1] < 0.02


@pytest.mark.parametrize('defective,expected', [(False,3), (True,2)])
@pytest.mark.parametrize('basis', ['X','Z'])
def test_full_cnot_distance_certificates(defective, expected, basis):
    from circuit_builder import build_cnot
    from analysis import add_noise, distance_audit
    result = distance_audit(add_noise(build_cnot(defective,(basis,basis),basis),1e-3))
    assert result['distance'] == expected
    assert result['graphlike_upper_bound'] == expected
    assert result['lower_bound'] == expected
