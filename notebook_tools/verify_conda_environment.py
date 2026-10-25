"""Verify the project Conda interpreter, every package pin, and Notebook kernel."""
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import ssl
import sys

HERE = Path(__file__).resolve().parents[1]
EXPECTED_PREFIX = (HERE / '.conda' / 'envs' / 'defective-cnot-d3').resolve()


def read_pins(path):
    pins = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('-r '):
            pins.update(read_pins(path.parent / line[3:]))
        else:
            name, version = line.split('==')
            pins[name] = version
    return pins


def main():
    assert Path(sys.prefix).resolve() == EXPECTED_PREFIX, 'Use the project Conda environment.'
    assert (EXPECTED_PREFIX / 'conda-meta' / 'history').is_file()
    assert sys.version_info[:2] == (3, 12)
    pins = read_pins(HERE / 'requirements-notebook-lock.txt')
    actual = {}
    for name, wanted in pins.items():
        dist = metadata.distribution(name)
        assert dist.version == wanted, f'{name}: expected {wanted}, found {dist.version}'
        assert Path(dist.locate_file('')).resolve().is_relative_to(EXPECTED_PREFIX), name
        actual[name] = dist.version
    assert Path(metadata.distribution('tqec').locate_file('')).resolve().is_relative_to(EXPECTED_PREFIX)
    actual['tqec'] = metadata.version('tqec')
    os.environ['JUPYTER_PATH'] = str(EXPECTED_PREFIX / 'share' / 'jupyter')
    from jupyter_client.kernelspec import KernelSpecManager
    kernel = KernelSpecManager().get_kernel_spec('defective-cnot-d3')
    assert Path(kernel.argv[0]).resolve() == Path(sys.executable).resolve()
    report = {
        'environment_kind': 'conda', 'environment_name': 'defective-cnot-d3',
        'environment_prefix': str(EXPECTED_PREFIX), 'python_executable': sys.executable,
        'python_version': sys.version, 'openssl': ssl.OPENSSL_VERSION,
        'pip_version': metadata.version('pip'),
        'locked_package_count': len(pins), 'all_pins_match': True,
        'all_packages_in_project_environment': True, 'versions': actual,
        'kernel': kernel.to_dict(), 'kernel_resource_dir': kernel.resource_dir,
    }
    (HERE / 'conda_environment_validation.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Conda environment verified: {len(pins)} package pins and the project kernel.')


if __name__ == '__main__':
    main()
