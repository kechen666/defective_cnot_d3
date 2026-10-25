"""Install with Windows extended paths, normalizing pip's relative RECORD paths.

Only the current installer process is adapted; no pip files are modified.
Windows extended paths must be absolute and cannot contain '..' components.
"""
import os
from importlib.metadata import version
from pathlib import Path
import sys


def main():
    here = Path(__file__).resolve().parents[1]
    prefix = (here / '.conda' / 'envs' / 'defective-cnot-d3').resolve()
    assert Path(sys.prefix).resolve() == prefix, 'Use the project Conda interpreter.'
    assert (prefix / 'conda-meta' / 'history').is_file()
    assert version('pip') == '26.2.1', 'This installer adapter requires the environment.yml pip pin (26.2.1).'
    from pip._internal.operations.install import wheel
    from pip._internal.cli.main import main as pip_main

    original_record_path = wheel._record_to_fs_path

    def normalized_record_path(record_path, lib_dir):
        return os.path.normpath(original_record_path(record_path, lib_dir))

    wheel._record_to_fs_path = normalized_record_path
    install_prefix = '\\\\?\\' + str(prefix) if os.name == 'nt' else str(prefix)
    try:
        return pip_main(['install', '--prefix', install_prefix, *sys.argv[1:]])
    finally:
        wheel._record_to_fs_path = original_record_path


if __name__ == '__main__':
    sys.exit(main())
