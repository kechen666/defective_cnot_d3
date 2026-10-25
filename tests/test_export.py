def test_stim_exports_support_unicode_directories(tmp_path):
    import stim
    from circuit_builder import build_cnot
    from run_experiment import export_experiment
    folder = tmp_path / '中文实验'
    exp = build_cnot(False,('Z','Z'),'Z')
    export_experiment(exp,folder,'Z')
    with (folder/'cnot_Z.stim').open(encoding='utf-8') as f:
        restored = stim.Circuit(f.read())
    assert restored == exp.circuit
