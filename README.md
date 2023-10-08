# pydock3

**pydock3** is a Python package wrapping the Fortran program *UCSF DOCK* that provides tools to help standardize and automate the computational methods employed in molecular docking. It is a natural successor to *DOCK Blaster*, originally published in 2009, and *blastermaster*, part of the DOCK 3.7 release in 2012. 

Documentation: https://wiki.docking.org/index.php/Pydock3

## Installation
```bash
# Through poetry
pip install poetry
bash install.sh
```

## How to run dockopt

### 0. prepare
A job_dir_path is needed where dockopt runs.
positives.tgz and negatives.tgz are zip file of directory of db2 files.
The structure of job_dir_path and tgz files are as below:
NOTE: dockopt_config.yaml is control file of dockopt. If not given, will copy pydock3/dockopt/default_dockopt_config.yaml instead.
```markdown
job_dir_path/
    - (optional) dockopt_config.yaml
    - rec.pdb
    - xtal-lig.pdb
    - positives.tgz
    - negatives.tgz

positives.tgz -> positives/
negatives.tgz -> negatives/
positives/
    - ligands/
        - 1.db2
        - 2.db2
        ...
negatives/
    - ligands/
        - a.db2
        - b.db2
        ...
```


### 1. run
through python script
```bash
python run_dockopt.py # many parameters should/can be modifed within the script.
```
**Or**, through command line
```bash
export SBATCH_EXEC="/usr/bin/sbatch -p helium -N 1 -n 1"
export SQUEUE_EXEC="/usr/bin/squeue"
export DOCK3_EXECUTABLE_PATH="/pubhome/qcxia02/soft/DOCK_Release_Apr_21_2023/dock3/dock64"
export TMPDIR="/tmp/qcxia"

pydock3 dockopt - run slurm \
--job_dir_path="/pubhome/qcxia02/git-repo/pydock3/example" \
--config_file_path=None \
--positives_tgz_file_path=None \
--negatives_tgz_file_path=None \
--retrodock_job_max_reattempts=0 \
--allow_failed_retrodock_jobs=False \
--retrodock_job_timeout_minutes=None \
--max_task_array_size=None \
--extra_submission_cmd_params_str=None \
--sleep_seconds_after_copying_output=0 \
--export_negatives_mol2=False \
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
