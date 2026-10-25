"""Exact stabilizer measurement relations with symbolic classical parities.

Each row is a signed Pauli whose eigenvalue is (-1)**parity(records).
Random measurements replace anticommuting rows; deterministic measurements
produce a relation and refresh their record, preventing long reference chains.
"""
import stim
import numpy as np


def mask(p):
    x, z = p.to_numpy()
    return (int.from_bytes(np.packbits(x, bitorder='little').tobytes(), 'little') |
            (int.from_bytes(np.packbits(z, bitorder='little').tobytes(), 'little') << len(p)))


def bits(value):
    while value:
        q = value & -value
        yield q.bit_length() - 1
        value ^= q


class SymbolicState:
    def __init__(self, n):
        self.n = n
        self.rows = []

    def unitary(self, circuit):
        self.rows = [(p.after(circuit), label) for p, label in self.rows]

    def _remove_components(self, predicate):
        affected = [i for i, (p, _) in enumerate(self.rows) if predicate(p)]
        if not affected:
            return
        pivot = affected[0]
        p, label = self.rows[pivot]
        for i in affected[1:]:
            q, v = self.rows[i]
            self.rows[i] = (q * p, v ^ label)
        self.rows.pop(pivot)

    def reset(self, q):
        self._remove_components(lambda p: p[q] in (1, 2))
        self._remove_components(lambda p: p[q] == 3)
        p = stim.PauliString(self.n)
        p[q] = 'Z'
        self.rows.append((p, 0))

    def forget(self, complementary_logical):
        self._remove_components(lambda p: not p.commutes(complementary_logical))

    def add_known(self, pauli, label=0):
        assert all(p.commutes(pauli) for p, _ in self.rows)
        assert self.lookup(pauli) is None
        self.rows.append((pauli, label))

    def lookup(self, target):
        basis = {}
        for i, (p, _) in enumerate(self.rows):
            v, selection = mask(p), 1 << i
            while v:
                k = v.bit_length() - 1
                if k not in basis:
                    basis[k] = (v, selection)
                    break
                a, b = basis[k]
                v ^= a
                selection ^= b
        v, selection = mask(target), 0
        while v:
            k = v.bit_length() - 1
            if k not in basis:
                return None
            a, b = basis[k]
            v ^= a
            selection ^= b
        product = stim.PauliString(self.n)
        label = 0
        for i in bits(selection):
            p, s = self.rows[i]
            product *= p
            label ^= s
        ratio = product.sign / target.sign
        assert ratio in (1, -1)
        return label, int(ratio == -1), selection

    def expectation(self, target):
        value = self.lookup(target)
        if value is None:
            raise ValueError(f'Target logical correlation is not preserved: {target}')
        return value[:2]

    def measure(self, q, measurement_index):
        p = stim.PauliString(self.n)
        p[q] = 'Z'
        value = self.lookup(p)
        if value is None:
            self._remove_components(lambda row: not row.commutes(p))
            self.rows.append((p, 1 << measurement_index))
            return None
        label, sign, selection = value
        # A new measurement is a valid generator substitution using any row
        # with nonzero coefficient in its old expression.
        pivot = next(bits(selection))
        self.rows[pivot] = (p, 1 << measurement_index)
        return label ^ (1 << measurement_index), sign
