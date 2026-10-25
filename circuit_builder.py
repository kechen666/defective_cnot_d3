"""Local three-patch CNOT with SnL gauges and exact record/frame inference."""
from dataclasses import dataclass
from functools import lru_cache
import numpy as np
import stim

from patches import build_patches, pauli_on, DEAD
from measurement_relations import SymbolicState, bits


def audit_hardware(operations, qubit_map, defective=False):
    """Check local CX edges and moment conflicts for a physical operation log."""
    reverse = {i: q for q, i in qubit_map.items()}
    dead = 0
    local = True
    busy = set()
    for op in operations:
        name, targets = op['name'], op['targets']
        if name == 'TICK':
            busy.clear()
            continue
        if busy.intersection(targets):
            raise ValueError(f'{name} {targets}: moment conflict.')
        busy.update(targets)
        dead += sum(reverse[q] == DEAD for q in targets) if defective else 0
        if name == 'CX':
            for a, b in zip(targets[::2], targets[1::2]):
                u, v = reverse[a], reverse[b]
                local &= abs(u[0] - v[0]) == abs(u[1] - v[1]) == 1
    if dead or not local:
        raise ValueError(f'Hardware validation failed: dead-qubit operations={dead}, local CX={local}.')
    return {'dead_qubit_operations': dead, 'two_qubit_edges_local': bool(local), 'moment_conflicts': 0}


@dataclass
class Experiment:
    circuit: stim.Circuit
    patches: dict
    qubit_map: dict
    records: list
    operations: list
    stages: list
    output_records: list
    output_frames: list
    observable_selectors: list
    flow_certificate: dict
    defective: bool
    choi_harness: stim.Circuit

    def verify_native_flows(self):
        result = {}
        for name, cert in self.flow_certificate.items():
            p = stim.PauliString(cert['correlation'])
            p.sign *= (-1) ** cert['sign']
            result[name] = self.choi_harness.has_flow(stim.Flow(output=p, measurements=cert['measurements']))
        return result

    def corrected_output_bits(self, raw):
        values = []
        for selector, (frame, sign) in zip(self.output_records, self.output_frames):
            ids = list(bits(selector ^ frame))
            values.append(np.logical_xor.reduce(raw[:, ids], axis=1) ^ bool(sign))
        return np.stack(values, axis=1)

    def hardware_audit(self):
        return audit_hardware(self.operations, self.qubit_map, self.defective)


class Builder:
    def __init__(self, patches, defective):
        self.patches = patches
        data = {q for p in patches.values() for q in p.data}
        coords = data | {c.ancilla for p in patches.values() for c in p.checks}
        self.qmap = {q: i for i, q in enumerate(sorted(coords))}
        self.data_ids = {self.qmap[q] for q in data}
        self.active = set()
        self.busy = set()
        self.circuit = stim.Circuit()
        for q, i in self.qmap.items():
            self.circuit.append('QUBIT_COORDS', [i], q)
        self.full = SymbolicState(len(coords))
        self.choi = SymbolicState(len(coords) + 2)
        self.records, self.operations, self.stages = [], [], []
        self.stage = 'prepare'
        self.round = -1
        self.defective = defective

    def p(self, patch, basis, extra=0):
        return pauli_on(self.patches[patch].logicals[basis], basis, self.qmap, extra)

    def emit(self, name, targets):
        targets = list(targets)
        if name != 'TICK' and not targets:
            return
        assert len(targets) == len(set(targets)), (name, targets)
        if name == 'TICK':
            idle = sorted(self.active - self.busy)
            self.operations.append({'name': name, 'targets': [], 'idle': idle,
                                    'stage': self.stage, 'round': self.round})
            self.circuit.append('TICK')
            self.busy.clear()
            return
        if name == 'R':
            self.active.update(self.data_ids.intersection(targets))
        self.busy.update(targets)
        self.operations.append({'name': name, 'targets': targets,
                                'stage': self.stage, 'round': self.round})
        fragment = stim.Circuit()
        fragment.append(name, targets)
        start = self.circuit.num_measurements
        self.circuit += fragment
        if name == 'R':
            for q in targets:
                self.full.reset(q)
                self.choi.reset(q)
        elif name == 'M':
            for offset, q in enumerate(targets):
                m = start + offset
                self.full.measure(q, m)
                relation = self.choi.measure(q, m)
                self.records.append({'index': m, 'qubit': q, 'stage': self.stage, 'round': self.round})
                if relation is not None:
                    selector, sign = relation
                    self.circuit.append('DETECTOR',
                                        [stim.target_rec(i - self.circuit.num_measurements) for i in bits(selector)],
                                        [q, self.round, len(self.stages)])
        else:
            self.full.unitary(fragment)
            self.choi.unitary(fragment)

    def tick(self):
        self.emit('TICK', [])

    def stage_start(self, name):
        self.stage = name
        self.stages.append({'name': name, 'start_measurement': self.circuit.num_measurements,
                            'start_tick': self.circuit.num_ticks})

    def check_round(self, names, round_index):
        self.round = round_index
        checks = [c for name in names for c in self.patches[name].round_checks(round_index)]
        anc = [self.qmap[c.ancilla] for c in checks]
        xanc = [self.qmap[c.ancilla] for c in checks if c.basis == 'X']
        self.emit('R', anc)
        self.tick()
        self.emit('H', xanc)
        self.tick()
        schedules = {'X': [(1,-1), (-1,-1), (1,1), (-1,1)],
                     'Z': [(1,-1), (1,1), (-1,-1), (-1,1)]}
        for k in range(4):
            pairs = []
            for c in checks:
                dx, dy = schedules[c.basis][k]
                data = (c.ancilla[0] + dx, c.ancilla[1] + dy)
                if data in c.data:
                    a, d = self.qmap[c.ancilla], self.qmap[data]
                    pairs.extend([a,d] if c.basis == 'X' else [d,a])
            self.emit('CX', pairs)
            self.tick()
        self.emit('H', xanc)
        self.tick()
        self.emit('M', anc)
        self.tick()

    def rounds(self, names, count=6):
        for r in range(count):
            self.check_round(names, r)

    def read_data(self, coords, basis):
        ids = [self.qmap[q] for q in sorted(coords)]
        if basis == 'X':
            self.emit('H', ids)
            self.tick()
        start = self.circuit.num_measurements
        self.emit('M', ids)
        self.active.difference_update(ids)
        self.tick()
        return {q: start + i for i, q in enumerate(sorted(coords))}


@lru_cache(maxsize=32)
def build_cnot(defective=True, input_bases=('Z','Z'), output_basis='Z', input_bits=(0,0)):
    if any(b not in 'XZ' for b in (*input_bases, output_basis)):
        raise ValueError('Only X/Z Pauli eigenstate inputs and readout are supported.')
    if any(v not in (0,1) for v in input_bits):
        raise ValueError('Input eigenvalue bits must be 0 or 1.')
    patches = build_patches(defective)
    b = Builder(patches, defective)
    b.stage_start('prepare')
    b.emit('R', [b.qmap[q] for name in ('C','A','T') for q in patches[name].data])
    b.tick()
    b.emit('H', [b.qmap[q] for name, basis in [('C',input_bases[0]),('A','X'),('T',input_bases[1])]
                 if basis == 'X' for q in patches[name].data])
    b.tick()
    for gate in 'XZ':
        b.emit(gate, [b.qmap[q] for name, basis, value in zip(('C','T'),input_bases,input_bits)
                      if value and gate != basis for q in patches[name].logicals[gate]])
    b.tick()
    # Remove the two known input eigenvalues in the detector model; purify
    # their remaining unknown logical degrees with virtual reference qubits.
    for name, basis, reference in zip(('C','T'), input_bases, (len(b.qmap),len(b.qmap)+1)):
        b.choi.forget(b.p(name, 'X' if basis == 'Z' else 'Z', 2))
        for pauli in 'XZ':
            operator = b.p(name, pauli, 2)
            operator[reference] = pauli
            b.choi.add_known(operator)
    choi_initial = [p.copy() for p, label in b.choi.rows]
    assert all(label == 0 for _, label in b.choi.rows)
    core_start = len(b.operations)
    b.rounds(('C','A','T'))
    route_ca = set(patches['CA'].data) - set(patches['C'].data) - set(patches['A'].data)
    b.stage_start('zz_merge')
    b.emit('R', [b.qmap[q] for q in sorted(route_ca)])
    b.tick()
    b.emit('H', [b.qmap[q] for q in sorted(route_ca)])
    b.tick()
    b.rounds(('CA','T'))
    b.stage_start('zz_split')
    b.read_data(route_ca, 'X')
    b.rounds(('C','A','T'))
    route_at = set(patches['AT'].data) - set(patches['A'].data) - set(patches['T'].data)
    b.stage_start('xx_merge')
    b.emit('R', [b.qmap[q] for q in sorted(route_at)])
    b.tick()
    b.rounds(('C','AT'))
    b.stage_start('xx_split')
    b.read_data(route_at, 'Z')
    b.rounds(('C','A','T'))
    b.stage_start('ancilla_readout')
    b.read_data(patches['A'].data, 'Z')
    rC, rT = len(b.qmap), len(b.qmap)+1
    desired = {'XC': b.p('C','X',2) * b.p('T','X',2), 'XT': b.p('T','X',2),
               'ZC': b.p('C','Z',2), 'ZT': b.p('C','Z',2) * b.p('T','Z',2)}
    flows = {}
    for name, p in desired.items():
        p[rC if name.endswith('C') else rT] = name[0]
        flows[name] = b.choi.expectation(p)
    # General byproduct frame, including split-induced corrections.
    xor = lambda a, c: (a[0]^c[0], a[1]^c[1])
    frames = {'X': [xor(flows['XC'], flows['XT']), flows['XT']],
              'Z': [flows['ZC'], xor(flows['ZT'], flows['ZC'])]}
    b.stage_start('output_readout')
    final = b.read_data(set(patches['C'].data) | set(patches['T'].data), output_basis)
    selectors = [sum(1 << final[q] for q in patches[name].logicals[output_basis]) for name in ('C','T')]
    corrected = [xor((s,0), f) for s,f in zip(selectors, frames[output_basis])]
    if input_bases == (output_basis,output_basis):
        obs = corrected
    elif input_bases == ('X','Z'):
        obs = [xor(*corrected)]
    else:
        raise NotImplementedError('Mixed input currently supports the approved Bell test X,Z only.')
    for i, (s, sign) in enumerate(obs):
        b.circuit.append('OBSERVABLE_INCLUDE', [stim.target_rec(j-b.circuit.num_measurements) for j in bits(s)], i)
    cert = {name: {'measurements': list(bits(label)), 'sign': sign,
                   'correlation': str(desired[name])} for name,(label,sign) in flows.items()}
    harness = stim.Circuit()
    harness.append('R', range(len(b.qmap) + 2))
    harness += stim.Tableau.from_stabilizers(choi_initial, allow_underconstrained=True).to_circuit('elimination')
    for op in b.operations[core_start:]:
        if op['stage'] == 'output_readout':
            break
        harness.append(op['name'], op['targets'])
    exp = Experiment(b.circuit, patches, b.qmap, b.records, b.operations, b.stages,
                     selectors, frames[output_basis], obs, cert, defective, harness)
    exp.hardware_audit()
    return exp
