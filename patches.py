"""Pinned SnL patch strategies and CSS algebra for the fixed internal defect."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os
import sys

import stim

HERE = Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR', str(HERE / '.cache' / 'matplotlib'))
os.environ.setdefault('TQEC_DETECTOR_DATABASE_PATH', str(HERE / '.cache' / 'detectors.pkl'))
os.environ.setdefault('WIN_PD_OVERRIDE_LOCAL_APPDATA', str(HERE / '.cache' / 'local'))
sys.path.insert(0, str(HERE / 'third_party' / 'snl'))
from defects_module import DefectiveSurfaceCode, RotatedSurfaceCode, PauliT, Pos
from defects_module.base import SuperStabilizer

DEAD = (3, 11)


def rank(rows):
    """Number of independent binary rows (integers encode bit vectors)."""
    basis = {}
    for row in rows:
        if not isinstance(row, int) or row < 0:
            raise ValueError('Binary rows must be nonnegative integers.')
        while row:
            pivot = row.bit_length() - 1
            if pivot not in basis:
                basis[pivot] = row
                break
            row ^= basis[pivot]
    return len(basis)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _coordinates(coords, label):
    _require(isinstance(coords, tuple) and bool(coords), f'{label}: expected a nonempty coordinate tuple.')
    _require(all(isinstance(q, tuple) and len(q) == 2 and
                 all(type(v) is int for v in q) for q in coords), f'{label}: invalid integer coordinates.')
    _require(len(set(coords)) == len(coords), f'{label}: duplicate coordinates.')
    return set(coords)


@dataclass(frozen=True)
class Boundary:
    """Full typed edge between corners, following ordered data-qubit centers.

    basis names the error string that can terminate here. The opposite Pauli
    along an outer edge is a dressed logical representative. These data-center
    paths are not polygon vertices. component groups edges of one contour.
    """
    name: str
    basis: str
    data: tuple[tuple[int, int], ...]
    component: str = 'outer'

    @property
    def endpoints(self):
        return self.data[0], self.data[-1]


@dataclass(frozen=True)
class Check:
    basis: str
    data: tuple[tuple[int, int], ...]
    ancilla: tuple[int, int]
    gauge: bool = False


@dataclass(frozen=True)
class Stabilizer:
    """CSS stabilizer support and the checks whose product measures it."""
    basis: str
    data: tuple[tuple[int, int], ...]
    checks: tuple[Check, ...]


@dataclass
class Patch:
    """One-logical-qubit CSS code snapshot, independent of a merge history."""
    name: str
    source: object
    data: tuple[tuple[int, int], ...]
    checks: tuple[Check, ...]
    stabilizers: tuple[Stabilizer, ...]
    logicals: dict
    distances: dict
    boundaries: tuple[Boundary, ...]

    def round_checks(self, round_index):
        """Ordinary checks every round; X/Z gauges on even/odd zero-based rounds."""
        _require(type(round_index) is int and round_index >= 0, 'Round index must be a nonnegative integer.')
        phase = 'X' if round_index % 2 == 0 else 'Z'
        return [c for c in self.checks if not c.gauge or c.basis == phase]

    def validate_data(self):
        """Category 3: coordinate, reference and ordered-boundary validity."""
        data = _coordinates(self.data, 'Patch.data')
        _require(isinstance(self.name, str) and bool(self.name), 'Patch.name must be nonempty.')
        _require(isinstance(self.checks, tuple) and bool(self.checks), 'Patch.checks must be nonempty.')
        _require(isinstance(self.stabilizers, tuple) and bool(self.stabilizers), 'Patch.stabilizers must be nonempty.')
        _require(len({id(c) for c in self.checks}) == len(self.checks), 'Patch.checks contains repeated objects.')
        for i, c in enumerate(self.checks):
            _require(isinstance(c, Check), f'Check {i}: expected Check.')
            _require(c.basis in ('X', 'Z'), f'Check {i}: unsupported basis {c.basis!r}.')
            _require(_coordinates(c.data, f'Check {i}') <= data, f'Check {i}: support outside Patch.data.')
            _coordinates((c.ancilla,), f'Check {i} ancilla')
            _require(c.ancilla not in data, f'Check {i}: ancilla is also a data qubit.')
            _require(type(c.gauge) is bool, f'Check {i}: gauge must be boolean.')
        used = set()
        for i, st in enumerate(self.stabilizers):
            _require(isinstance(st, Stabilizer), f'Stabilizer {i}: expected Stabilizer.')
            _require(st.basis in ('X', 'Z'), f'Stabilizer {i}: unsupported basis.')
            _require(_coordinates(st.data, f'Stabilizer {i}') <= data,
                     f'Stabilizer {i}: support outside Patch.data.')
            _require(isinstance(st.checks, tuple) and bool(st.checks), f'Stabilizer {i}: no measurement checks.')
            _require(len({id(c) for c in st.checks}) == len(st.checks), f'Stabilizer {i}: repeated check reference.')
            used.update(id(c) for c in st.checks)
        _require(used == {id(c) for c in self.checks}, 'Stabilizers must reference exactly the patch check objects.')
        _require(isinstance(self.logicals, dict) and set(self.logicals) == {'X', 'Z'},
                 'Exactly one X/Z logical pair is required.')
        _require(isinstance(self.distances, dict) and set(self.distances) == {'X', 'Z'},
                 'Expected X/Z distances are required.')
        for b in 'XZ':
            _require(_coordinates(self.logicals[b], f'Logical {b}') <= data, f'Logical {b}: support outside Patch.data.')
            _require(type(self.distances[b]) is int and self.distances[b] > 0, f'Distance {b} must be positive.')
        _require(isinstance(self.boundaries, tuple) and bool(self.boundaries), 'Patch.boundaries must be nonempty.')
        names, components = set(), {}
        for boundary in self.boundaries:
            _require(isinstance(boundary, Boundary), 'Expected Boundary objects.')
            _require(isinstance(boundary.name, str) and bool(boundary.name) and boundary.name not in names,
                     'Boundary names must be nonempty and unique.')
            names.add(boundary.name)
            _require(boundary.basis in ('X', 'Z'), f'Boundary {boundary.name}: unsupported terminating basis.')
            _require(isinstance(boundary.component, str) and bool(boundary.component), 'Boundary component must be nonempty.')
            _require(_coordinates(boundary.data, f'Boundary {boundary.name}') <= data,
                     f'Boundary {boundary.name}: support outside Patch.data.')
            for a, b in zip(boundary.data, boundary.data[1:]):
                step = abs(a[0] - b[0]), abs(a[1] - b[1])
                _require(max(step) == 2 and all(v in (0, 2) for v in step),
                         f'Boundary {boundary.name}: disconnected step {a} -> {b}.')
            components.setdefault(boundary.component, []).append(boundary)
        _require('outer' in components, 'An outer contour is required.')
        for component, edges in components.items():
            for a, b in zip(edges, edges[1:] + edges[:1]):
                _require(a.data[-1] == b.data[0], f'Boundary component {component}: edges do not form an ordered closed contour.')
            for i, a in enumerate(edges):
                for j, b in enumerate(edges[i + 1:], i + 1):
                    allowed = set(a.endpoints) & set(b.endpoints) if j == i + 1 or (i == 0 and j == len(edges) - 1) else set()
                    _require((set(a.data) & set(b.data)) <= allowed,
                             f'Boundary component {component}: edges overlap away from adjacent endpoints.')
        for a, first in enumerate(components.values()):
            for second in list(components.values())[a + 1:]:
                _require(not ({q for edge in first for q in edge.data} & {q for edge in second for q in edge.data}),
                         'Different boundary components share data qubits.')
        return {'data_qubits': len(data), 'checks': len(self.checks), 'stabilizers': len(self.stabilizers),
                'boundaries': len(self.boundaries), 'components': list(components),
                'boundary_coordinates': 'ordered data-qubit centers', 'boundary_basis': 'terminating error string'}

    def _masks(self):
        index = {q: i for i, q in enumerate(self.data)}
        mask = lambda qs: sum(1 << index[q] for q in qs)
        gauges = {b: [mask(c.data) for c in self.checks if c.basis == b] for b in 'XZ'}
        stabilizers = {b: [mask(st.data) for st in self.stabilizers if st.basis == b] for b in 'XZ'}
        logicals = {b: mask(self.logicals[b]) for b in 'XZ'}
        return gauges, stabilizers, logicals

    def _parameters(self):
        gauges, stabilizers, _ = self._masks()
        g = sum(rank(gauges[b]) for b in 'XZ')
        s = sum(rank(stabilizers[b]) for b in 'XZ')
        # CSS gauge commutation matrix; its rank counts anticommuting pairs.
        r = rank([sum(((x & z).bit_count() % 2) << j for j, z in enumerate(gauges['Z']))
                  for x in gauges['X']])
        return {'data_qubits': len(self.data), 'gauge_rank': g, 'stabilizer_rank': s,
                'gauge_qubits': r, 'logical_qubits': len(self.data) - s - r,
                'center_rank': g - 2 * r}

    def validate_subsystem(self):
        """Category 1: CSS gauge center, stabilizer products and bare logicals."""
        self.validate_data()
        for st in self.stabilizers:
            support = set()
            for c in st.checks:
                _require(c.basis == st.basis, f'Stabilizer {st.data}: check bases disagree.')
                support.symmetric_difference_update(c.data)
            _require(support == set(st.data), f'Check product differs from stabilizer {st.data}.')
        gauges, stabilizers, logicals = self._masks()
        for b in 'XZ':
            opposite = 'Z' if b == 'X' else 'X'
            _require(all((a & c).bit_count() % 2 == 0 for a in stabilizers[b] for c in stabilizers[opposite]),
                     f'{b} stabilizers do not commute with opposite stabilizers.')
            _require(all((a & c).bit_count() % 2 == 0 for a in stabilizers[b] for c in gauges[opposite]),
                     f'{b} stabilizer does not commute with all gauge checks.')
            _require(all((logicals[b] & c).bit_count() % 2 == 0 for c in gauges[opposite]),
                     f'Bare logical {b} does not commute with all gauge checks.')
        _require((logicals['X'] & logicals['Z']).bit_count() % 2 == 1, 'Bare logical X/Z must anticommute.')
        parameters = self._parameters()
        _require(parameters['stabilizer_rank'] == parameters['center_rank'],
                 f'Stabilizers do not generate the full gauge center: {parameters}.')
        index = {q: i for i, q in enumerate(self.data)}
        for boundary in self.boundaries:
            if boundary.component != 'outer':
                continue
            edge = sum(1 << index[q] for q in boundary.data)
            _require(all((edge & st).bit_count() % 2 == 0 for st in stabilizers[boundary.basis]) and
                     (edge & logicals[boundary.basis]).bit_count() % 2 == 1,
                     f'Boundary {boundary.name}: terminating basis disagrees with its logical edge.')
        return {'products_match': True, 'stabilizers_commute': True, 'stabilizers_central': True,
                'center_complete': True, 'bare_logical_pair_valid': True,
                'outer_boundary_logicals_valid': True, 'phase_convention': 'positive pure-X/pure-Z generators'}

    def analyze_dimensions(self):
        """Category 2: independently count gauge pairs and require one logical."""
        self.validate_subsystem()
        parameters = self._parameters()
        difference = parameters['gauge_rank'] - parameters['stabilizer_rank']
        _require(difference >= 0 and difference % 2 == 0, f'Invalid gauge/stabilizer rank difference: {parameters}.')
        _require(difference // 2 == parameters['gauge_qubits'], f'Gauge pair counts disagree: {parameters}.')
        _require(parameters['logical_qubits'] == 1, f'Expected one protected logical qubit: {parameters}.')
        return {**parameters, 'codespace_dimension': 2 ** (parameters['data_qubits'] - parameters['stabilizer_rank']),
                'protected_dimension': 2, 'gauge_dimension': 2 ** parameters['gauge_qubits']}

    def analyze_distances(self):
        """Category 2: exact dressed CSS distances and minimum-weight witnesses."""
        self.analyze_dimensions()
        _, s, l = self._masks()
        # Exact dressed CSS distance: zero opposite-stabilizer syndrome and
        # odd overlap with the opposite bare logical. Each data qubit is used
        # once in this minimum-weight dynamic program (no graph approximation).
        distances, witnesses = {}, {}
        for b in 'XZ':
            opposite = 'Z' if b == 'X' else 'X'
            constraints = s[opposite] + [l[opposite]]
            best = {0: (0, 0)}
            for j in range(len(self.data)):
                column = sum(((v >> j) & 1) << k for k, v in enumerate(constraints))
                updated = dict(best)
                for syndrome, (weight, support) in best.items():
                    target = syndrome ^ column
                    if target not in updated or updated[target][0] > weight + 1:
                        updated[target] = (weight + 1, support | (1 << j))
                best = updated
            weight, support = best[1 << len(s[opposite])]
            distances[b] = weight
            witnesses[b] = [q for j, q in enumerate(self.data) if (support >> j) & 1]
        _require(distances == self.distances, f'{self.name}: computed distances {distances} != expected {self.distances}.')
        return {'distances': distances, 'distance_witnesses': witnesses, 'method': 'exact binary dynamic programming',
                'kind': 'static dressed CSS distance', 'bound': 'exact'}

    def validate_measurements(self, rounds=6):
        """Category 4: signed flows of the actual repeated-check Builder circuit."""
        self.analyze_dimensions()
        from patch_measurements import validate_patch_measurements
        return validate_patch_measurements(self, rounds)

    def audit(self, *, compute_distances=True, check_measurements=False, detailed=False, raise_on_error=True):
        """Run four categories; retain the legacy flat result unless detailed=True.

        Invalid input raises ValueError. With raise_on_error=False, failed and
        dependency-skipped categories are returned for inspection. Skipping an
        expensive analysis never produces a computed distance or a pass result.
        """
        sections = {}
        result = {key: None for key in ('logical_qubits', 'gauge_qubits', 'stabilizer_rank', 'gauge_rank',
                                        'algebra_distances', 'distance_witnesses')}
        result['distances'] = self.distances

        def run(name, action):
            if any(item['status'] == 'failed' for item in sections.values()):
                sections[name] = {'status': 'skipped', 'reason': 'A prerequisite failed.'}
                return None
            try:
                value = action()
                sections[name] = {'status': 'passed', 'evidence': value}
                return value
            except (ValueError, AssertionError) as error:
                sections[name] = {'status': 'failed', 'error': str(error)}
                return None

        run('data', self.validate_data)
        run('subsystem', self.validate_subsystem)
        dimensions = run('dimensions', self.analyze_dimensions)
        if dimensions is not None:
            result.update({k: dimensions[k] for k in ('logical_qubits', 'gauge_qubits', 'stabilizer_rank', 'gauge_rank')})
        if compute_distances:
            distance = run('distance', self.analyze_distances)
            if distance is not None:
                result.update(algebra_distances=distance['distances'], distance_witnesses=distance['distance_witnesses'])
        else:
            sections['distance'] = {'status': 'skipped', 'reason': 'Exact distance calculation was not requested.'}
        if check_measurements:
            run('measurements', self.validate_measurements)
        else:
            sections['measurements'] = {'status': 'skipped', 'reason': 'Temporal measurement validation was not requested.'}
        failures = [f'{name}: {item["error"]}' for name, item in sections.items() if item['status'] == 'failed']
        if failures and raise_on_error:
            raise ValueError(f'{self.name}: ' + '; '.join(failures))
        if detailed or not raise_on_error:
            analysis = {'dimensions': sections['dimensions'], 'distance': sections['distance']}
            analysis['status'] = ('failed' if any(v['status'] == 'failed' for v in analysis.values()) else
                                  'skipped' if sections['dimensions']['status'] == 'skipped' else 'passed')
            result['validation'] = {'data': sections['data'], 'subsystem': sections['subsystem'],
                                    'analysis': analysis, 'measurements': sections['measurements']}
        return result


def _boundaries(obj):
    """Translate SnL edge strings; rectangular fallback for healthy patches only."""
    paths = getattr(obj, 'deformed_logicals', None)
    if paths:
        paths = {name: tuple((q.x, q.y) for q in paths[name]) for name in ('left', 'bottom', 'right', 'top')}
    else:
        _require(isinstance(obj, RotatedSurfaceCode) and not isinstance(obj, DefectiveSurfaceCode),
                 'Defective patches must supply their actual deformed boundaries.')
        xmin, xmax, ymin, ymax = obj.extent
        xs, ys = range(xmin + 1, xmax, 2), range(ymin + 1, ymax, 2)
        paths = {'left': tuple((xs[0], y) for y in reversed(ys)),
                 'bottom': tuple((x, ys[0]) for x in xs),
                 'right': tuple((xs[-1], y) for y in ys),
                 'top': tuple((x, ys[-1]) for x in reversed(xs))}
    vertical = obj.vertical_logical.name
    opposite = 'Z' if vertical == 'X' else 'X'
    return tuple(Boundary(name, opposite if name in ('left', 'right') else vertical, paths[name])
                 for name in ('left', 'bottom', 'right', 'top'))


def _convert(name, obj):
    """Adapt a pinned SnL object, keeping shared checks and typed boundaries."""
    checks = []
    stabilizers = []
    for s in sorted(obj.stabilizers, key=lambda s: (str(s.type), tuple(sorted(int(a) for a in s.ancilla)))):
        stabilizer_checks = []
        for g in (s.gauges if isinstance(s, SuperStabilizer) else [s]):
            anc = g.only_ancilla
            stabilizer_checks.append(Check(g.type.name, tuple(sorted((q.x, q.y) for q in g.data_qubits)),
                                           (anc.x, anc.y), isinstance(s, SuperStabilizer)))
        stabilizers.append(Stabilizer(s.type.name, tuple(sorted((q.x, q.y) for q in s.data_qubits)),
                                     tuple(stabilizer_checks)))
        checks.extend(stabilizer_checks)
    horizontal, vertical = getattr(obj, 'effective_distance', obj.distance)
    vertical_basis = obj.vertical_logical.name
    horizontal_basis = 'Z' if vertical_basis == 'X' else 'X'
    p = Patch(name, obj, tuple(sorted((q.x, q.y) for q in obj.data_qubits)), tuple(checks),
              tuple(stabilizers), {b: tuple((q.x, q.y) for q in obj.logicals[getattr(PauliT, b)]) for b in 'XZ'},
              {vertical_basis: int(vertical), horizontal_basis: int(horizontal)}, _boundaries(obj))
    p.audit(compute_distances=False)
    return p


@lru_cache(maxsize=4)
def build_patches(defective=True, defect=DEAD):
    """Build cached fixed C/A/T/CA/AT snapshots; only DEAD is supported."""
    if defective and defect != DEAD:
        raise NotImplementedError('Only the approved internal center data defect is supported; boundary defects require a new strategy.')
    specs = {'C': ((3, 3), (1, 9)), 'A': ((3, 3), (1, 1)), 'T': ((3, 3), (9, 1)),
             'CA': ((3, 7), (1, 1)), 'AT': ((7, 3), (1, 1))}
    result = {}
    for name, (size, offset) in specs.items():
        raw = RotatedSurfaceCode(size, sw_offset=Pos(*offset))
        if defective and name in ('C', 'CA'):
            _, candidates = DefectiveSurfaceCode.make_defective_patches(
                raw, set(), {Pos(*defect)}, set(), repurpose_ancillas=True, add_padding=False)
            raw = sorted(candidates, key=lambda p: (-min(p.effective_distance),
                                                   -sum(p.effective_distance), len(p.data_qubits)))[0]
        result[name] = _convert(name, raw)
    return result


def pauli_on(coords, basis, qubit_map, extra_qubits=0):
    """Place a uniform Pauli on coordinate support in a Stim register of IDs."""
    p = stim.PauliString(len(qubit_map) + extra_qubits)
    for q in coords:
        p[qubit_map[q]] = basis
    return p
