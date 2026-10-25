"""Circuit-level noise, full-DEM distance certificates, and bounded decoding."""
import math
import numpy as np
import pymatching
import stim


def add_noise(exp, probability):
    """Uniform circuit noise; retain every original measurement and annotation."""
    if not math.isfinite(probability) or not 0 <= probability < 1:
        raise ValueError('Noise probability must satisfy 0 <= p < 1.')
    noisy = stim.Circuit()
    operations = iter(exp.operations)
    for instruction in exp.circuit:
        name = instruction.name
        targets = instruction.targets_copy()
        if name in ('QUBIT_COORDS', 'DETECTOR', 'OBSERVABLE_INCLUDE'):
            noisy.append(instruction)
            continue
        metadata = next(operations)
        assert name == metadata['name']
        assert [t.value for t in targets] == metadata['targets']
        if name == 'M':
            noisy.append('M', targets, probability)
        else:
            noisy.append(instruction)
            if probability and name == 'R':
                noisy.append('X_ERROR', targets, probability)
            elif probability and name in ('H', 'X', 'Z'):
                noisy.append('DEPOLARIZE1', targets, probability)
            elif probability and name == 'CX':
                noisy.append('DEPOLARIZE2', targets, probability)
            elif probability and name == 'TICK' and metadata['idle']:
                noisy.append('DEPOLARIZE1', metadata['idle'], probability)
    assert next(operations, None) is None
    return noisy


def low_weight_distance(dem):
    """Exhaust weight 1/2 in the complete DEM, retaining hyperedge correlations.

    The returned certificate is a distance of the independent DEM mechanism
    model. A graphlike decomposition component is never counted as a fault.
    """
    signatures = {}
    for index, instruction in enumerate(dem.flattened()):
        if instruction.type != 'error' or instruction.args_copy()[0] <= 0:
            continue
        detector, observable = 0, 0
        for target in instruction.targets_copy():
            if target.is_relative_detector_id():
                detector ^= 1 << target.val
            elif target.is_logical_observable_id():
                observable ^= 1 << target.val
        witness = {'dem_instruction': index, 'error': str(instruction)}
        if detector == 0 and observable:
            return {'distance': 1, 'lower_bound': 1, 'searched_max_weight': 1,
                    'witness': [witness]}
        signatures.setdefault(detector, {}).setdefault(observable, witness)
    for outcomes in signatures.values():
        if len(outcomes) > 1:
            items = list(outcomes.values())
            return {'distance': 2, 'lower_bound': 2, 'searched_max_weight': 2,
                    'witness': items[:2]}
    return {'distance': None, 'lower_bound': 3, 'searched_max_weight': 2, 'witness': []}


def distance_audit(circuit):
    full_dem = circuit.detector_error_model(decompose_errors=False, allow_gauge_detectors=False)
    result = low_weight_distance(full_dem)
    try:
        witness = circuit.shortest_graphlike_error(ignore_ungraphlike_errors=True)
        upper = len(witness)
        result['graphlike_upper_bound'] = upper
        result['graphlike_witness'] = [str(e) for e in witness]
        if result['distance'] is None and upper == result['lower_bound']:
            result['distance'] = upper
        assert result['distance'] is None or result['distance'] <= upper
    except ValueError as error:
        result['graphlike_upper_bound'] = None
        result['graphlike_search_error'] = str(error)
    result['model'] = 'independent mechanisms of the undecomposed Stim DEM'
    return result


def wilson_interval(failures, shots):
    if shots <= 0:
        raise ValueError('shots must be positive')
    z = 1.959963984540054
    rate = failures / shots
    denominator = 1 + z*z/shots
    center = (rate + z*z/(2*shots)) / denominator
    radius = z*math.sqrt(rate*(1-rate)/shots + z*z/(4*shots*shots)) / denominator
    return [max(0., center-radius), min(1., center+radius)]


def sample_decode(circuit, shots, seed, batch_size=10000):
    if shots <= 0 or batch_size <= 0:
        raise ValueError('shots and batch_size must be positive')
    dem = circuit.detector_error_model(decompose_errors=True, allow_gauge_detectors=False,
                                       ignore_decomposition_failures=False)
    matching = pymatching.Matching.from_detector_error_model(dem)
    sampler = circuit.compile_detector_sampler(seed=seed)
    decoded_any = raw_any = 0
    per_observable = np.zeros(circuit.num_observables, dtype=np.int64)
    raw_per_observable = np.zeros(circuit.num_observables, dtype=np.int64)
    completed = 0
    while completed < shots:
        size = min(batch_size, shots-completed)
        detectors, observables = sampler.sample(size, separate_observables=True)
        predicted = matching.decode_batch(detectors)
        residual = predicted ^ observables
        decoded_any += int(np.any(residual, axis=1).sum())
        raw_any += int(np.any(observables, axis=1).sum())
        per_observable += residual.sum(axis=0).astype(np.int64)
        raw_per_observable += observables.sum(axis=0).astype(np.int64)
        completed += size
    return {'shots': shots, 'seed': seed, 'batch_size': batch_size,
            'raw_any_failures': raw_any, 'decoded_any_failures': decoded_any,
            'decoded_failures_by_observable': per_observable.tolist(),
            'raw_failures_by_observable': raw_per_observable.tolist(),
            'decoded_failure_rates_by_observable': (per_observable/shots).tolist(),
            'raw_failure_rate': raw_any/shots, 'decoded_failure_rate': decoded_any/shots,
            'decoded_wilson95': wilson_interval(decoded_any, shots),
            'raw_wilson95': wilson_interval(raw_any, shots),
            'decoded_wilson95_by_observable': [wilson_interval(int(v),shots) for v in per_observable],
            'decoder': 'PyMatching MWPM, standard decomposed DEM, uncorrelated matching'}
