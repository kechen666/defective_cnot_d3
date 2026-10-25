"""Execute the walkthrough with a fresh registered project kernel and save outputs."""
import json
import os
import sys
from pathlib import Path
import nbformat
from nbclient import NotebookClient

HERE=Path(__file__).resolve().parents[1]
expected_prefix=(HERE/'.conda'/'envs'/'defective-cnot-d3').resolve()
assert Path(sys.prefix).resolve()==expected_prefix, 'Run this script using the project Conda environment.'
assert (expected_prefix/'conda-meta'/'history').is_file()
for name,folder in {'JUPYTER_RUNTIME_DIR':'jupyter-runtime','JUPYTER_CONFIG_DIR':'jupyter-config',
                    'JUPYTER_DATA_DIR':'jupyter-data','IPYTHONDIR':'ipython'}.items():
    path=HERE/'.cache'/folder
    path.mkdir(parents=True,exist_ok=True)
    os.environ[name]=str(path)
os.environ['JUPYTER_PATH']=str(expected_prefix/'share'/'jupyter')
from jupyter_client.kernelspec import KernelSpecManager
kernel=KernelSpecManager().get_kernel_spec('defective-cnot-d3')
assert Path(kernel.argv[0]).resolve()==Path(sys.executable).resolve(), 'Notebook kernel points to a different interpreter.'
path=HERE/'defective_cnot_d3_walkthrough.ipynb'
notebook=nbformat.read(path,as_version=4)
nbformat.validate(notebook)
for cell in notebook.cells:
    if cell.cell_type=='code':
        cell.execution_count=None
        cell.outputs=[]
client=NotebookClient(notebook,timeout=300,kernel_name='defective-cnot-d3',
                      resources={'metadata':{'path':str(HERE)}},allow_errors=False)
print('Executing fresh-kernel walkthrough...',flush=True)
client.execute()
nbformat.validate(notebook)
assert all(cell.execution_count is not None for cell in notebook.cells if cell.cell_type=='code')
assert not any(o.output_type=='error' for c in notebook.cells if c.cell_type=='code' for o in c.outputs)
nbformat.write(notebook,path)
report={'nbformat_valid':True,'code_cells':sum(c.cell_type=='code' for c in notebook.cells),
        'all_executed':True,'error_outputs':0,'kernel':'defective-cnot-d3',
        'execution':'nbclient, fresh kernel, top to bottom, default 100000 shots/group'}
report.update(environment_kind='conda',environment_prefix=str(expected_prefix),python_executable=sys.executable)
(HERE/'notebook_execution_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2),flush=True)
