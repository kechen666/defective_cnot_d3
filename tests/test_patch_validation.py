"""Regressions for boundary semantics, gauge-center validity and real schedules."""
from dataclasses import replace

import pytest

from patches import DEAD, Patch, Stabilizer, build_patches


def replace_check(patch, old, new):
    return replace(patch, checks=tuple(new if c is old else c for c in patch.checks),
                   stabilizers=tuple(replace(s, checks=tuple(new if c is old else c for c in s.checks))
                                     for s in patch.stabilizers))


@pytest.mark.parametrize('defective', [False, True])
def test_all_snapshots_pass_the_four_categories(defective):
    for patch in build_patches(defective).values():
        report = patch.audit(detailed=True, check_measurements=True)
        assert set(report['validation']) == {'data', 'subsystem', 'analysis', 'measurements'}
        assert all(section['status'] == 'passed' for section in report['validation'].values())
        temporal = report['validation']['measurements']['evidence']
        assert temporal['check_measurement_flows'] == sum(len(patch.round_checks(r)) for r in range(6))
        assert temporal['repeat_parity_flows'] >= len(patch.stabilizers)
        assert temporal['logical_memory_flows'] == 2
        dimensions = report['validation']['analysis']['dimensions']['evidence']
        assert dimensions['logical_qubits'] == 1
        assert dimensions['codespace_dimension'] == dimensions['protected_dimension'] * dimensions['gauge_dimension']


@pytest.mark.parametrize('defective', [False, True])
def test_boundary_convention_and_upstream_paths(defective):
    for patch in build_patches(defective).values():
        assert [(b.name, b.basis) for b in patch.boundaries] == [
            ('left', 'Z'), ('bottom', 'X'), ('right', 'Z'), ('top', 'X')]
        for a, b in zip(patch.boundaries, patch.boundaries[1:] + patch.boundaries[:1]):
            assert a.endpoints[1] == b.endpoints[0]
        upstream = getattr(patch.source, 'deformed_logicals', None)
        if upstream:
            assert all(b.data == tuple((q.x, q.y) for q in upstream[b.name]) for b in patch.boundaries)
    assert DEAD not in {q for b in build_patches(True)['C'].boundaries for q in b.data}


@pytest.mark.parametrize('problem', ['duplicate_data', 'outside_support', 'basis', 'repeated_boundary', 'disconnected_boundary'])
def test_bad_input_reports_failure_and_skips_dependent_work(problem):
    patch = build_patches(False)['C']
    if problem == 'duplicate_data':
        invalid = replace(patch, data=patch.data + (patch.data[0],))
    elif problem == 'outside_support':
        old = patch.checks[0]
        invalid = replace_check(patch, old, replace(old, data=old.data + ((101, 101),)))
    elif problem == 'basis':
        old = patch.checks[0]
        invalid = replace_check(patch, old, replace(old, basis='Y'))
    elif problem == 'repeated_boundary':
        invalid = replace(patch, boundaries=patch.boundaries + (patch.boundaries[0],))
    else:
        boundary = patch.boundaries[0]
        invalid = replace(patch, boundaries=(replace(boundary, data=(boundary.data[0], boundary.data[-1])),) + patch.boundaries[1:])
    report = invalid.audit(raise_on_error=False, check_measurements=True)['validation']
    assert report['data']['status'] == 'failed'
    assert report['subsystem']['status'] == report['analysis']['status'] == report['measurements']['status'] == 'skipped'
    with pytest.raises(ValueError):
        invalid.audit()


def test_wrong_boundary_type_is_rejected_by_the_code_algebra():
    patch = build_patches(False)['C']
    invalid = replace(patch, boundaries=(replace(patch.boundaries[0], basis='X'),) + patch.boundaries[1:])
    invalid.validate_data()
    with pytest.raises(ValueError, match='terminating basis'):
        invalid.validate_subsystem()


def test_upstream_vertical_pauli_orientation_is_respected():
    from patches import PauliT, RotatedSurfaceCode, _convert
    patch = _convert('swapped_orientation', RotatedSurfaceCode((3, 5), vertical_logical=PauliT.Z))
    assert patch.audit()['algebra_distances'] == {'X': 3, 'Z': 5}
    assert [b.basis for b in patch.boundaries] == ['X', 'Z', 'X', 'Z']


def test_pairwise_commuting_stabilizers_must_also_commute_with_gauges():
    patch = build_patches(True)['C']
    i = next(i for i, s in enumerate(patch.stabilizers) if s.basis == 'X' and len(s.checks) == 2)
    split = tuple(Stabilizer(c.basis, c.data, (c,)) for c in patch.stabilizers[i].checks)
    invalid = replace(patch, stabilizers=patch.stabilizers[:i] + split + patch.stabilizers[i + 1:])
    invalid.validate_data()
    with pytest.raises(ValueError, match='all gauge checks'):
        invalid.validate_subsystem()


def test_incomplete_center_is_rejected_even_when_all_checks_are_referenced():
    patch = build_patches(False)['C']
    a, b = patch.stabilizers[:2]
    product = Stabilizer('X', tuple(sorted(set(a.data) ^ set(b.data))), a.checks + b.checks)
    invalid = replace(patch, stabilizers=(product, replace(product)) + patch.stabilizers[2:])
    invalid.validate_data()
    with pytest.raises(ValueError, match='full gauge center'):
        invalid.validate_subsystem()


def test_unconstrained_extra_data_changes_the_protected_dimension():
    patch = build_patches(True)['C']
    invalid = replace(patch, data=tuple(sorted(patch.data + (DEAD,))))
    invalid.validate_subsystem()
    with pytest.raises(ValueError, match='one protected logical'):
        invalid.analyze_dimensions()


def test_distance_is_optional_and_a_mismatch_is_reported(monkeypatch):
    patch = build_patches(False)['C']
    fast = patch.audit(compute_distances=False, detailed=True)
    assert fast['algebra_distances'] is fast['distance_witnesses'] is None
    assert fast['validation']['analysis']['distance']['status'] == 'skipped'
    assert fast['validation']['measurements']['status'] == 'skipped'
    invalid = replace(patch, distances={'X': 2, 'Z': 3})
    report = invalid.audit(raise_on_error=False)['validation']['analysis']
    assert report['status'] == report['distance']['status'] == 'failed'
    assert report['dimensions']['status'] == 'passed'
    def forbidden(self):
        raise RuntimeError('Exact distance must not execute in fast mode.')
    monkeypatch.setattr(Patch, 'analyze_distances', forbidden)
    patch.audit(compute_distances=False)


def test_nonrectangular_paths_are_statically_representable():
    patch = build_patches(False)['C']
    move = lambda q: (q[0] + (2 if q[1] == 11 else 0), q[1])
    support = lambda qs: tuple(move(q) for q in qs)
    checks = {id(c): replace(c, data=support(c.data)) for c in patch.checks}
    bent = replace(patch, data=tuple(sorted(support(patch.data))),
                   checks=tuple(checks[id(c)] for c in patch.checks),
                   stabilizers=tuple(replace(s, data=support(s.data), checks=tuple(checks[id(c)] for c in s.checks))
                                     for s in patch.stabilizers),
                   logicals={b: support(qs) for b, qs in patch.logicals.items()},
                   boundaries=tuple(replace(b, data=support(b.data)) for b in patch.boundaries))
    assert bent.analyze_dimensions()['logical_qubits'] == 1
    with pytest.raises(ValueError, match='four-neighbor'):
        bent.validate_measurements()


def test_timing_rejects_a_broken_physical_measurement(monkeypatch):
    from circuit_builder import Builder
    original = Builder.emit
    def missing_cx(self, name, targets):
        return original(self, name, list(targets)[2:] if name == 'CX' else targets)
    monkeypatch.setattr(Builder, 'emit', missing_cx)
    with pytest.raises(ValueError, match='does not measure check'):
        build_patches(False)['C'].validate_measurements()


def test_timing_rejects_incomplete_gauge_coverage(monkeypatch):
    original = Patch.round_checks
    patch = build_patches(True)['C']
    omitted = next(c for c in patch.checks if c.gauge)
    monkeypatch.setattr(Patch, 'round_checks', lambda self, r: [c for c in original(self, r) if c is not omitted])
    with pytest.raises(ValueError, match='not measured|lack repeated'):
        patch.validate_measurements()
