def test_symbolic_relations_keep_random_gauges_and_latest_records():
    from measurement_relations import SymbolicState
    import stim
    state = SymbolicState(2)
    state.reset(0)
    state.reset(1)
    state.unitary(stim.Circuit('H 0\nCX 0 1'))
    assert state.measure(0, 0) is None
    relation = state.measure(1, 1)
    assert relation == (3, 0)  # Bell pair: raw m0 XOR m1 = 0.
    assert state.measure(1, 2) == (6, 0)  # Use latest m1, not m0.
