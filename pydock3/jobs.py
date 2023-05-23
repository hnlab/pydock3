import logging
import subprocess
from typing import Tuple, List, Union
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from pydock3.files import Dir, File
from pydock3.job_schedulers import JobScheduler

from pydock3.docking import __file__ as DOCKING_INIT_FILE_PATH

DOCK3_EXECUTABLE_PATH = os.path.join(
    os.path.dirname(DOCKING_INIT_FILE_PATH), "dock3", "dock64"
)
DOCK_RUN_SCRIPT_PATH = os.path.join(
    os.path.dirname(DOCKING_INIT_FILE_PATH), "rundock.bash"
)


#
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


#
class JobSubmissionResult(Enum):
    SUCCESS = 1
    FAILED = 2
    SKIPPED_BECAUSE_ALREADY_COMPLETE = 3
    SKIPPED_BECAUSE_STILL_ON_JOB_SCHEDULER_QUEUE = 4


"""  # TODO
@dataclass
class DockingJob(ABC):
    @abstractmethod
    def submit(self):
        raise NotImplementedError
"""

@dataclass
class ArrayDockingJob(ABC):
    name: str
    job_dir: Dir
    input_molecules_tgz_file_path: str
    job_scheduler: JobScheduler
    temp_storage_path: str
    array_job_docking_configurations_file_path: str
    job_timeout_minutes: Union[None, int] = None
    extra_submission_cmd_params_str: Union[None, str] = None
    sleep_seconds_after_copying_output: int = 0
    export_mol2: bool = True
    #max_reattempts: int = 0  # TODO

    OUTDOCK_FILE_NAME = "OUTDOCK.0"

    def __post_init__(self):
        #
        with open(self.array_job_docking_configurations_file_path, 'r') as f:
            self.task_ids = [line.strip().split()[0] for line in f.readlines()]

        # create task dirs
        task_id_to_num_attempts_so_far_dict = {}
        for task_id in self.task_ids:
            task_dir = Dir(os.path.join(self.job_dir.path, task_id), create=True, reset=False)
            task_id_to_num_attempts_so_far_dict[task_id] = 0

        # create log dirs
        self.out_log_dir = Dir(os.path.join(self.job_dir.path, "out_logs"), create=True, reset=False)
        self.err_log_dir = Dir(os.path.join(self.job_dir.path, "err_logs"), create=True, reset=False)

    def submit_all_tasks(
            self,
            skip_if_complete: bool = True,
    ) -> Tuple[JobSubmissionResult, List[subprocess.CompletedProcess]]:
        """
        if job submission is skipped, returns (JobSubmissionResult, [])
        if job submission is not skipped, returns (JobSubmissionResult, List[subprocess.CompletedProcess])
        in case of failed submissions and (JobSubmissionResult, []) otherwise.
        """

        #
        if self.is_on_job_scheduler_queue:
            return JobSubmissionResult.SKIPPED_BECAUSE_STILL_ON_JOB_SCHEDULER_QUEUE, []

        #
        if skip_if_complete:
            if self.is_complete:
                return JobSubmissionResult.SKIPPED_BECAUSE_ALREADY_COMPLETE, []

        # reset task dirs
        task_ids_to_submit = []
        for task_id in self.task_ids:
            if not (self.task_is_complete(task_id) and skip_if_complete):
                task_dir = Dir(os.path.join(self.job_dir.path, task_id), create=True, reset=True)  # reset dir
                task_ids_to_submit.append(task_id)

        # set env vars dict
        env_vars_dict = {
            "EXPORT_DEST": self.job_dir.path,
            "TMPDIR": self.temp_storage_path,
            "ARRAY_JOB_DOCKING_CONFIGURATIONS": self.array_job_docking_configurations_file_path,
            "INPUT_TARBALL": self.input_molecules_tgz_file_path,
            "SLEEP_SECONDS_AFTER_COPYING_OUTPUT": str(self.sleep_seconds_after_copying_output),
        }

        #
        if self.export_mol2:
            env_vars_dict["EXPORT_MOL2"] = "true"
        else:
            env_vars_dict["EXPORT_MOL2"] = "false"

        # submit job
        procs = self.job_scheduler.submit(
            job_name=self.name,
            script_path=DOCK_RUN_SCRIPT_PATH,
            env_vars_dict=env_vars_dict,
            out_log_dir_path=self.out_log_dir.path,
            err_log_dir_path=self.err_log_dir.path,
            task_ids=task_ids_to_submit,
            job_timeout_minutes=self.job_timeout_minutes,
            extra_submission_cmd_params_str=self.extra_submission_cmd_params_str,
        )

        failed_procs = [proc for proc in procs if proc.stderr]
        if failed_procs:
            return JobSubmissionResult.FAILED, failed_procs
        else:
            return JobSubmissionResult.SUCCESS, []

    def submit_task(
            self,
            task_id: Union[str, int],
            skip_if_complete: bool = True,
    ) -> Tuple[JobSubmissionResult, List[subprocess.CompletedProcess]]:
        """
        if job submission is skipped, returns (JobSubmissionResult, [])
        if job submission is not skipped, returns (JobSubmissionResult, List[subprocess.CompletedProcess])
        in case of failed submissions and (JobSubmissionResult, []) otherwise.
        """

        #
        if skip_if_complete:
            if self.task_is_complete(task_id):
                return JobSubmissionResult.SKIPPED_BECAUSE_ALREADY_COMPLETE, []

        # reset task dir
        task_ids_to_submit = []
        if not (self.task_is_complete(task_id) and skip_if_complete):
            task_dir = Dir(os.path.join(self.job_dir.path, task_id), create=True, reset=True)  # reset dir
            task_ids_to_submit.append(task_id)

        # set env vars dict
        env_vars_dict = {
            "EXPORT_DEST": self.job_dir.path,
            "TMPDIR": self.temp_storage_path,
            "ARRAY_JOB_DOCKING_CONFIGURATIONS": self.array_job_docking_configurations_file_path,
            "INPUT_TARBALL": self.input_molecules_tgz_file_path,
            "SLEEP_SECONDS_AFTER_COPYING_OUTPUT": str(self.sleep_seconds_after_copying_output),
        }

        #
        if self.export_mol2:
            env_vars_dict["EXPORT_MOL2"] = "true"
        else:
            env_vars_dict["EXPORT_MOL2"] = "false"

        # submit job
        procs = self.job_scheduler.submit(
            job_name=self.name,
            script_path=DOCK_RUN_SCRIPT_PATH,
            env_vars_dict=env_vars_dict,
            out_log_dir_path=self.out_log_dir.path,
            err_log_dir_path=self.err_log_dir.path,
            task_ids=task_ids_to_submit,
            job_timeout_minutes=self.job_timeout_minutes,
            extra_submission_cmd_params_str=self.extra_submission_cmd_params_str,
        )

        failed_procs = [proc for proc in procs if proc.stderr]
        if failed_procs:
            return JobSubmissionResult.FAILED, failed_procs
        else:
            return JobSubmissionResult.SUCCESS, []

    @property
    def is_on_job_scheduler_queue(self):
        return self.job_scheduler.job_is_on_queue(self.name)

    @property
    def is_complete(self):
        return all(
            [
                self.task_is_complete(task_id)
                for task_id in self.task_ids
            ]
        )

    def task_is_complete(self, task_id: Union[str, int]):
        return File.file_exists(os.path.join(self.job_dir.path, task_id, self.OUTDOCK_FILE_NAME))
