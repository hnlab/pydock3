# pydock3

**pydock3** is a Python package wrapping the Fortran program *UCSF DOCK* that provides tools to help standardize and automate the computational methods employed in molecular docking. It is a natural successor to *DOCK Blaster*, originally published in 2009, and *blastermaster*, part of the DOCK 3.7 release in 2012. 

Documentation: https://wiki.docking.org/index.php/Pydock3
DOCKopt documentation: https://wiki.docking.org/index.php?title=Dockopt_(pydock3_script)

## Installation
```bash
# Through poetry
conda create -n pydock3 python=3.9
conda activate pydock3
pip install poetry
bash install.sh
```

## How to run dockopt

### 0. prepare
A job_dir_path is needed where dockopt runs.
actives.tgz and decoys.tgz are zip file of directory of db2 files.
The structure of job_dir_path and tgz files are as below:
NOTE: dockopt_config.yaml is control file of dockopt. If not given, will copy pydock3/dockopt/default_dockopt_config.yaml instead. The yaml file should have the same format as in pydock3/dockopt/dockopt_config_schema.yaml
```markdown
job_dir_path/
    - (optional) dockopt_config.yaml
    - rec.pdb
    - xtal-lig.pdb
    - actives.tgz
    - decoys.tgz

actives.tgz -> actives/
decoys.tgz -> decoys/
actives/
    - ligands/
        - 1.db2
        - 2.db2
        ...
decoys/
    - ligands/
        - a.db2
        - b.db2
        ...
```


### 1. run
through python script (Recommended)
```bash
python run_dockopt.py \
    --schedular "slurm" \
    --job_dir_path "/your/path/" \
    --tmp_dir "/tmp/your/tmp/path" \
    --config_file_path "dockopt_config.yaml" \
    --actives_tgz_file_path "actives.tgz" \
    --decoys_tgz_file_path "decoys.tgz" \
    --recpdb "rec.pdb" \
    --ligpdb "xtal-lig.pdb" \
    --extra_submission_cmd_params_str "-p honda -N 1 -n 1 -q normal" \
    --retrodock_job_timeout_minutes "12:00:00" \
    --retrodock_job_max_reattempts 0 \
    --max_task_array_size 20000 \
    --dock38bin "$DOCKBASE/docking/DOCK/bin/dock64"
```

**Or**, through command line
```bash
export SBATCH_EXEC="/usr/bin/sbatch"
export SQUEUE_EXEC="/usr/bin/squeue"
export DOCK3_EXECUTABLE_PATH="$DOCKBASE/docking/DOCK/bin/dock64"
export TMPDIR="/tmp/qcxia"

pydock3 dockopt - run slurm \
--job_dir_path="/your/path/" \
--config_file_path="dockopt_config.yaml" \
--actives_tgz_file_path="actives.tgz" \
--decoys_tgz_file_path="decoys.tgz" \
--retrodock_job_max_reattempts=0 \
--allow_failed_retrodock_jobs=False \
--retrodock_job_timeout_minutes="12:00:00" \
--max_task_array_size=None \
--extra_submission_cmd_params_str="-p honda -N 1 -n 1 -q normal" \
--sleep_seconds_after_copying_output=0 \
--export_decoys_mol2=False \
--delete_intermediate_files=False \
--force_redock=False \
--force_rewrite_results=False \
--force_rewrite_report=False
```
Multiple dockfiles will be generated locally and multiple docking campaigns will be submited remotely (through slurm as array job).
Running status can be monitored from log (for python running, an `example.log` will be recorded as screen outputs).

### 2. analysis
After running, results will be given as a directory `best_retrodock_jobs` and 2 files `report.html`, `result.csv`.
`best_retrodock_jobs` are top scored docking campaigns. dockfiles within can be used afterwards.
`result.csv` is detailed record of dockfiles and results.
`report.html` gives meaningful plot of dockopt results.


***

TIPS:
1. Dockfiles generation (blastermaster) is run on local machine (without parallel), which may be time-consuming if the combination number is huge. Should think about move this part to remote as well.
