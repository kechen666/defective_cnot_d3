"""Verify or fetch pinned source archives. Does not edit an existing source tree."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

HERE=Path(__file__).resolve().parent


def tree_hash(root, paths):
    digest=hashlib.sha256()
    for name in sorted(paths):
        digest.update(name.encode('utf-8')+b'\0')
        digest.update((root/name).read_bytes())
        digest.update(b'\0')
    return digest.hexdigest()


def fetch(url, path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with urllib.request.urlopen(url,timeout=90) as response:
        path.write_bytes(response.read())


def extract(archive, destination):
    destination=destination.resolve()
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            relative=Path(*Path(info.filename).parts[1:])
            if not relative.parts or info.is_dir():
                continue
            target=(destination/relative).resolve()
            if not target.is_relative_to(destination):
                raise ValueError('Archive path escapes destination')
            # Extended paths avoid Windows' legacy 260-character limit.
            native=Path('\\\\?\\'+str(target)) if __import__('os').name=='nt' else target
            native.parent.mkdir(parents=True,exist_ok=True)
            native.write_bytes(z.read(info))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tqec-source',type=Path,required=True)
    args=parser.parse_args()
    source=json.loads((HERE/'sources.json').read_text(encoding='utf-8'))
    archive=HERE/'third_party'/'snl.zip'
    if not archive.exists():
        fetch('https://codeload.github.com/amazon-science/snakes_and_ladders_adapting_the_surface_code_to_defects/zip/'+source['snl_commit'],archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=source['snl_archive_sha256']:
        raise ValueError('SnL archive checksum mismatch')
    snl=HERE/'third_party'/'snl'
    if not (snl/'defects_module').exists():
        extract(archive,snl)
    if tree_hash(snl,source['snl_files'])!=source['snl_tree_sha256']:
        raise ValueError('SnL source differs from the pinned source')
    if not args.tqec_source.exists():
        archive=HERE/'third_party'/'tqec.zip'
        if not archive.exists():
            fetch('https://codeload.github.com/tqec/tqec/zip/'+source['tqec_commit'],archive)
        extract(archive,args.tqec_source)
    if tree_hash(args.tqec_source,source['tqec_files'])!=source['tqec_tree_sha256']:
        raise ValueError('TQEC source differs from the pinned source')
    print('Pinned source fingerprints verified.')


if __name__=='__main__':
    main()
