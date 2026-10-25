"""Signed measurement-flow validation for one patch's actual Builder schedule."""
import stim


def validate_patch_measurements(patch, rounds=6):
    """Verify memory checks on unknown input data, without merge/split operations.

    At least two full X/Z gauge cycles are needed to test repeated parity.
    Stim 1.16 signed flow checks have a false-positive bound of 2**-256.
    """
    from circuit_builder import Builder, audit_hardware
    from patches import _require, pauli_on

    _require(type(rounds) is int and rounds >= 4, 'Temporal validation requires at least four rounds.')
    for c in patch.checks:
        _require(all(abs(q[0] - c.ancilla[0]) == abs(q[1] - c.ancilla[1]) == 1 for q in c.data),
                 f'Check {c.ancilla}: support is not completely covered by the four-neighbor Builder.')
    builder = Builder({patch.name: patch}, defective=False)
    counts = {id(c): 0 for c in patch.checks}
    previous, observations, relations, round_counts = {}, {}, [], []
    check_flows = 0
    for r in range(rounds):
        selected = patch.round_checks(r)
        _require(len({id(c) for c in selected}) == len(selected), f'Round {r}: repeated check.')
        _require(len({c.ancilla for c in selected}) == len(selected), f'Round {r}: shared ancilla conflict.')
        for i, a in enumerate(selected):
            for b in selected[i + 1:]:
                _require(a.basis == b.basis or len(set(a.data) & set(b.data)) % 2 == 0,
                         f'Round {r}: simultaneous anticommuting checks {a.ancilla}, {b.ancilla}.')
        instruction_start = len(builder.circuit)
        record_start = len(builder.records)
        measurement_start = builder.circuit.num_measurements
        builder.check_round((patch.name,), r)
        records = builder.records[record_start:]
        _require(len(records) == len(selected), f'Round {r}: check/record count mismatch.')
        body = stim.Circuit()
        for instruction in builder.circuit[instruction_start:]:
            if instruction.name != 'DETECTOR':
                body.append(instruction)
        selected_ids = {id(c) for c in selected}
        measured = {}
        for c, record in zip(selected, records):
            _require(record['qubit'] == builder.qmap[c.ancilla], f'Round {r}: wrong ancilla record.')
            flow = stim.Flow(input=pauli_on(c.data, c.basis, builder.qmap),
                             measurements=[record['index'] - measurement_start])
            _require(body.has_flow(flow), f'Round {r}: circuit does not measure check {c.ancilla} as declared.')
            measured[id(c)] = record['index']
            counts[id(c)] += 1
            check_flows += 1
        for i, s in enumerate(patch.stabilizers):
            if not all(id(c) in selected_ids for c in s.checks):
                continue
            parity = [measured[id(c)] for c in s.checks]
            operator = pauli_on(s.data, s.basis, builder.qmap)
            _require(builder.circuit.has_flow(stim.Flow(input=operator, measurements=parity)),
                     f'Round {r}: gauge parity does not measure stabilizer {i}.')
            if i in previous:
                ids = sorted(set(previous[i]) ^ set(parity))
                _require(builder.circuit.has_flow(stim.Flow(measurements=ids)),
                         f'Round {r}: stabilizer {i} parity is not preserved across rounds.')
                relations.append({'stabilizer': i, 'round': r, 'measurements': ids, 'sign': 0})
            previous[i] = parity
            observations[i] = observations.get(i, 0) + 1
        round_counts.append(len(selected))
    _require(all(n >= 2 for n in counts.values()), 'Some checks were not measured in two complete cycles.')
    _require(all(observations.get(i, 0) >= 2 for i in range(len(patch.stabilizers))),
             'Some stabilizers lack repeated complete gauge measurements.')
    for basis in 'XZ':
        logical = pauli_on(patch.logicals[basis], basis, builder.qmap)
        _require(builder.circuit.has_flow(stim.Flow(input=logical, output=logical)),
                 f'Memory schedule changes bare logical {basis}.')
    hardware = audit_hardware(builder.operations, builder.qmap)
    builder.circuit.detector_error_model(allow_gauge_detectors=False)
    return {'rounds': rounds, 'round_check_counts': round_counts, 'check_measurement_flows': check_flows,
            'stabilizer_measurement_flows': sum(observations.values()), 'repeat_parity_flows': len(relations),
            'logical_memory_flows': 2, 'detectors': builder.circuit.num_detectors,
            'hardware': hardware, 'relations': relations,
            'method': 'signed Stim flows on the actual Builder circuit',
            'input': 'unknown data; no assumed logical eigenvalue',
            'signed_flow_false_positive_bound': '2^-256 per checked flow'}
