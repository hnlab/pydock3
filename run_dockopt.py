import os
import shutil
import argparse
import logging

parser = argparse.ArgumentParser("DOCKopt")
parser.add_argument("--schedular",type=str,choices=["sge","slurm"],default="slurm")
parser.add_argument("--job_dir_path",type=str,help="rootpath of dockopt job",required=True)
parser.add_argument("--tmp_dir",type=str,help="temp dir",required=True)
parser.add_argument("--config_file_path",type=str,help="absolute path of config file",required=True)
parser.add_argument("--actives_tgz_file_path",type=str,help="absolute path of actives tgz file",required=True)
parser.add_argument("--decoys_tgz_file_path",type=str,help="absolute path of decoys tgz file",required=True)
parser.add_argument("--recpdb",type=str,help="absolute path of rec.pdb",required=True)
parser.add_argument("--ligpdb",type=str,help="absolute path of lig.pdb",required=True)
parser.add_argument("--extra_submission_cmd_params_str",type=str,help="job array submit optional arguments",default="-p honda -N 1 -n 1 -q normal")
parser.add_argument("--retrodock_job_timeout_minutes",type=str,help="",default="12:00:00")
parser.add_argument("--retrodock_job_max_reattempts",type=int,help="",default=0)
parser.add_argument("--max_task_array_size",type=int,help="max array size based on slurm configuration",default=20000)
parser.add_argument("--allow_failed_retrodock_jobs",type=str,help="",default=None)
parser.add_argument("--sleep_seconds_after_copying_output",type=float,help="sleep seconds after copying output",default=1)
parser.add_argument("--export_decoys_mol2",action="store_true",help="",default=False)
parser.add_argument("--delete_intermediate_files",action="store_true",help="",default=False)
parser.add_argument("--force_redock",action="store_true",help="",default=False)
parser.add_argument("--force_rewrite_results",action="store_true",help="",default=False)
parser.add_argument("--force_rewrite_report",action="store_true",help="",default=False)
parser.add_argument("--dock38bin",type=str,help="DOCK bin dock64",default="/home/qcxia/opt/DOCK_Release_Apr_21_2023/dock3/dock64")
parser.add_argument("--verbose",action="store_true",help="verbose log output",default=False)
args = parser.parse_args()

# should modify #
os.environ["SBATCH_EXEC"] = "/usr/bin/sbatch" # must determine resource
os.environ["SQUEUE_EXEC"] = "/usr/bin/squeue"
os.environ["DOCK3_EXECUTABLE_PATH"] = args.dock38bin
os.environ["TMPDIR"] = args.tmp_dir

scheduler = args.schedular
job_dir_path = args.job_dir_path
config_file_path = args.config_file_path
actives_tgz_file_path = args.actives_tgz_file_path
decoys_tgz_file_path = args.decoys_tgz_file_path
extra_submission_cmd_params_str = args.extra_submission_cmd_params_str,
retrodock_job_timeout_minutes = args.retrodock_job_timeout_minutes, # 12 hours for normal
retrodock_job_max_reattempts = args.retrodock_job_max_reattempts,
max_task_array_size = args.max_task_array_size,
allow_failed_retrodock_jobs = args.allow_failed_retrodock_jobs,
sleep_seconds_after_copying_output = args.sleep_seconds_after_copying_output,
export_decoys_mol2 = args.export_decoys_mol2,
delete_intermediate_files = args.delete_intermediate_files,
force_redock = args.force_redock,
force_rewrite_results = args.force_rewrite_results,
force_rewrite_report = args.force_rewrite_report,

if not os.path.exists(job_dir_path): os.makedirs(job_dir_path)
#################
if args.verbose: level = logging.DEBUG
else: level = logging.INFO
logging.basicConfig(
    level=level,
    format="%(asctime)s : %(levelname)s : %(message)s",
    handlers=[
        # logging.FileHandler(f"{job_dir_path}/example.log","w"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("dockopt")

# make sure rec.pdb and xtal-lig.pdb located in job_dir_path
shutil.copy(args.recpdb, f"{job_dir_path}/rec.pdb")
shutil.copy(args.ligpdb, f"{job_dir_path}/xtal-lig.pdb")

from pydock3.dockopt import Dockopt
if __name__ == "__main__":
    job_dockopt = Dockopt()
    job_dockopt.new(job_dir_path=job_dir_path)
    # can modify #
    job_dockopt.run(
        scheduler = "slurm",
        job_dir_path = job_dir_path,
        retrodock_job_timeout_minutes = "12:00:00", # 12 hours for normal
        config_file_path = args.config_file_path, # dockopt_config.yaml
        actives_tgz_file_path = args.actives_tgz_file_path, # actives.tgz
        decoys_tgz_file_path = args.decoys_tgz_file_path, # decoys.tgz
        retrodock_job_max_reattempts = args.retrodock_job_max_reattempts,
        allow_failed_retrodock_jobs = args.allow_failed_retrodock_jobs,
        max_task_array_size = args.max_task_array_size,
        extra_submission_cmd_params_str = args.extra_submission_cmd_params_str,
        sleep_seconds_after_copying_output = args.sleep_seconds_after_copying_output,
        export_decoys_mol2 = args.export_decoys_mol2,
        delete_intermediate_files = args.delete_intermediate_files,
        force_redock = args.force_redock,
        force_rewrite_results = args.force_rewrite_results,
        force_rewrite_report = args.force_rewrite_report,
    )
    ##############

