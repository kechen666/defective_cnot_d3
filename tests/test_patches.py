from dataclasses import replace
import json

import pytest


def test_center_data_defect_and_stage_distances():
    from patches import build_patches
    p = build_patches(True)
    assert len(p['C'].data) == 8
    assert len(p['A'].data) == len(p['T'].data) == 9
    assert (3, 11) not in p['CA'].data
    assert p['C'].distances == {'X': 2, 'Z': 2}
    assert p['CA'].distances == {'X': 6, 'Z': 2}
    assert p['AT'].distances == {'X': 3, 'Z': 7}
    for patch in p.values():
        assert patch.audit()['logical_qubits'] == 1
        assert patch.audit()['algebra_distances'] == patch.distances


def test_defect_free_baseline_distances():
    from patches import build_patches
    p = build_patches(False)
    assert len(p['C'].data) == 9
    assert p['C'].distances == {'X': 3, 'Z': 3}
    assert p['CA'].distances == {'X': 7, 'Z': 3}


def test_boundary_defect_is_not_silently_treated_as_internal():
    from patches import build_patches
    with pytest.raises(NotImplementedError):
        build_patches(True, defect=(1, 9))


@pytest.mark.parametrize('defective,case', [(False, 'healthy'), (True, 'defective')])
def test_stabilizer_objects_preserve_exported_patch_results(tmp_path, defective, case):
    from patches import HERE, Stabilizer, build_patches
    from run_experiment import export_patches

    patches = build_patches(defective)
    for patch in patches.values():
        assert all(isinstance(s, Stabilizer) for s in patch.stabilizers)
    export_patches(patches, tmp_path)
    exported = json.loads((tmp_path / 'patches.json').read_text(encoding='utf-8'))
    recorded = json.loads((HERE / 'results' / case / 'patches.json').read_text(encoding='utf-8'))
    assert exported == recorded


@pytest.mark.parametrize('defective', [False, True])
def test_stabilizers_reference_checks_with_the_correct_pauli_product(defective):
    import stim
    from patches import build_patches, pauli_on

    for patch in build_patches(defective).values():
        grouped_checks = tuple(c for s in patch.stabilizers for c in s.checks)
        assert len(grouped_checks) == len(patch.checks)
        assert all(a is b for a, b in zip(grouped_checks, patch.checks))
        qubit_map = {q: i for i, q in enumerate(patch.data)}
        for s in patch.stabilizers:
            assert len(s.checks) == (2 if any(c.gauge for c in s.checks) else 1)
            product = stim.PauliString(len(qubit_map))
            for c in s.checks:
                assert c.basis == s.basis
                product *= pauli_on(c.data, c.basis, qubit_map)
            assert product == pauli_on(s.data, s.basis, qubit_map)


@pytest.mark.parametrize('problem', ['empty', 'basis', 'support', 'copied_check'])
def test_audit_rejects_inconsistent_stabilizer_checks(problem):
    from patches import build_patches

    patch = build_patches(False)['C']
    stabilizer = patch.stabilizers[0]
    if problem == 'empty':
        invalid = replace(stabilizer, checks=())
    elif problem == 'basis':
        invalid = replace(stabilizer, basis='Z')
    elif problem == 'support':
        invalid = replace(stabilizer, data=stabilizer.data[:-1])
    else:
        invalid = replace(stabilizer, checks=(replace(stabilizer.checks[0]),))
    changed = replace(patch, stabilizers=(invalid,) + patch.stabilizers[1:])
    with pytest.raises(ValueError):
        changed.audit()
