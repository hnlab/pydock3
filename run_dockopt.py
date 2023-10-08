import os
# should modify #
os.environ["SBATCH_EXEC"] = "/usr/bin/sbatch -p helium -N 1 -n 1" # must determine resource
os.environ["SQUEUE_EXEC"] = "/usr/bin/squeue"
os.environ["DOCK3_EXECUTABLE_PATH"] = "/pubhome/qcxia02/soft/DOCK_Release_Apr_21_2023/dock3/dock64"
os.environ["TMPDIR"] = "/tmp/qcxia"
job_dir_path = "/pubhome/qcxia02/git-repo/pydock3/example"
#################
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s : %(levelname)s : %(message)s",
    handlers=[
        logging.FileHandler(f"{job_dir_path}/example.log"),
        logging.StreamHandler(),
    ],
)
from pydock3.dockopt import Dockopt

if __name__ == "__main__":
    job_dockopt = Dockopt()
    job_dockopt.new(job_dir_path=job_dir_path)
    # can modify #
    job_dockopt.run(
        scheduler = "slurm",
        job_dir_path = job_dir_path,
        config_file_path = None, # dockopt_config.yaml
        positives_tgz_file_path = None, # positives.tgz
        negatives_tgz_file_path = None, # negatives.tgz
        retrodock_job_max_reattempts = 0,
        allow_failed_retrodock_jobs = False,
        retrodock_job_timeout_minutes = None,
        max_task_array_size = None,
        extra_submission_cmd_params_str = None,
        sleep_seconds_after_copying_output = 0,
        export_negatives_mol2 = False,
        delete_intermediate_files = False,
        force_redock = False,
        force_rewrite_results = False,
        force_rewrite_report = False,
    )
    ##############

