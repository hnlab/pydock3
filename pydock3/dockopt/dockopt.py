from typing import Union, Iterable, List
import itertools
from operator import getitem
import os
import shutil
import sys
from functools import wraps
from dataclasses import dataclass, fields, asdict
from copy import copy, deepcopy
import logging
import collections
import time
import random
from datetime import datetime
import hashlib

import networkx as nx
import numpy as np
import pandas as pd
from dirhash import dirhash
import matplotlib.pyplot as plt

import seaborn as sns
from joypy import joyplot


from pydock3.util import (
    Script,
    CleanExit,
    get_dataclass_as_dict,
    validate_variable_type,
)
from pydock3.config import (
    Parameter,
    flatten_and_parameter_cast_param_dict,
    get_univalued_flat_parameter_cast_param_dicts_from_multivalued_param_dict,
)
from pydock3.blastermaster.blastermaster import BlasterFiles, get_blaster_steps
from pydock3.dockopt.config import DockoptParametersConfiguration
from pydock3.files import (
    Dir,
    File,
    IndockFile,
    OutdockFile,
    INDOCK_FILE_NAME,
)
from pydock3.blastermaster.util import (
    WorkingDir,
    BlasterFile,
    DockFiles,
    BlasterFileNames,
)
from pydock3.dockopt.roc import ROC
from pydock3.jobs import RetrodockJob, DOCK3_EXECUTABLE_PATH
from pydock3.job_schedulers import SlurmJobScheduler, SGEJobScheduler
from pydock3.dockopt import __file__ as DOCKOPT_INIT_FILE_PATH
from pydock3.blastermaster.programs.thinspheres.sph_lib import read_sph, write_sph
from pydock3.retrodock.retrodock import log_job_submission_result, get_results_dataframe_from_actives_job_and_decoys_job_outdock_files, str_to_float
from pydock3.blastermaster.util import DEFAULT_FILES_DIR_PATH
from pydock3.dockopt.results_manager import RESULTS_CSV_FILE_NAME, ResultsManager, DockoptResultsManager
from pydock3.dockopt.reporter import Reporter, PDFReporter, RETRODOCK_JOB_DIR_PATH_COLUMN_NAME
from pydock3.dockopt.criterion import EnrichmentScore, Criterion
from pydock3.dockopt.pipeline import PipelineComponent, PipelineComponentSequence, Pipeline
from pydock3.retrodock.retrodock import ROC_PLOT_FILE_NAME, ENERGY_PLOT_FILE_NAME, CHARGE_PLOT_FILE_NAME

#
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


#
SCHEDULER_NAME_TO_CLASS_DICT = {
    "sge": SGEJobScheduler,
    "slurm": SlurmJobScheduler,
}

#
CRITERION_CLASS_DICT = {"enrichment_score": EnrichmentScore}


def get_persistent_hash_of_tuple(t: tuple) -> str:
    m = hashlib.md5()
    for s in t:
        m.update(str(s).encode())
    return m.hexdigest()


@dataclass
class RetrodockArgsSet:
    scheduler: str
    job_dir_path: str = "."
    dock_files_dir_path: Union[None, str] = None
    indock_file_path: Union[None, str] = None
    dock_executable_path: Union[None, str] = None
    actives_tgz_file_path: Union[None, str] = None
    decoys_tgz_file_path: Union[None, str] = None
    temp_storage_path: Union[None, str] = None
    retrodock_job_max_reattempts: int = 0
    retrodock_job_timeout_minutes: Union[None, int] = None
    max_scheduler_jobs_running_at_a_time: Union[None, int] = None
    export_decoy_poses: bool = False


class Dockopt(Script):
    JOB_DIR_NAME = "dockopt_job"
    CONFIG_FILE_NAME = "dockopt_config.yaml"
    ACTIVES_TGZ_FILE_NAME = "actives.tgz"
    DECOYS_TGZ_FILE_NAME = "decoys.tgz"
    DEFAULT_CONFIG_FILE_PATH = os.path.join(
        os.path.dirname(DOCKOPT_INIT_FILE_PATH), "default_dockopt_config.yaml"
    )

    def __init__(self):
        super().__init__()

        self.job_dir = None  # assigned in .init()

    @staticmethod
    def handle_run_func(run_func):
        @wraps(run_func)
        def wrapper(self, *args, **kwargs):
            with CleanExit():
                logger.info(f"Running {self.__class__.__name__}")
                run_func(self, *args, **kwargs)

        return wrapper

    def init(
        self,
        job_dir_path: str = JOB_DIR_NAME,
        overwrite: bool = False
    ) -> None:
        # create job dir
        self.job_dir = Dir(path=job_dir_path, create=True, reset=False)

        # create working dir & copy in blaster files
        blaster_file_names = list(get_dataclass_as_dict(BlasterFileNames()).values())
        user_provided_blaster_file_paths = [
            os.path.abspath(f) for f in blaster_file_names if os.path.isfile(f)
        ]
        files_to_copy_str = "\n\t".join(user_provided_blaster_file_paths)
        if user_provided_blaster_file_paths:
            logger.info(
                f"Copying the following files from current directory into job working directory:\n\t{files_to_copy_str}"
            )
            for blaster_file_path in user_provided_blaster_file_paths:
                self.job_dir.copy_in_file(blaster_file_path)
        else:
            logger.info(
                f"No blaster files detected in current working directory. Be sure to add them manually before running the job."
            )

        # copy in actives and decoys TGZ files
        tgz_files = [self.ACTIVES_TGZ_FILE_NAME, self.DECOYS_TGZ_FILE_NAME]
        tgz_file_names_in_cwd = [f for f in tgz_files if os.path.isfile(f)]
        tgz_file_names_not_in_cwd = [f for f in tgz_files if not os.path.isfile(f)]
        if tgz_file_names_in_cwd:
            files_to_copy_str = "\n\t".join(tgz_file_names_in_cwd)
            logger.info(
                f"Copying the following files from current directory into job directory:\n\t{files_to_copy_str}"
            )
            for tgz_file_name in tgz_file_names_in_cwd:
                self.job_dir.copy_in_file(tgz_file_name)
        if tgz_file_names_not_in_cwd:
            files_missing_str = "\n\t".join(tgz_file_names_not_in_cwd)
            logger.info(
                f"The following required files were not found in current working directory. Be sure to add them manually to the job directory before running the job.\n\t{files_missing_str}"
            )

        # write fresh config file from default file
        save_path = os.path.join(self.job_dir.path, self.CONFIG_FILE_NAME)
        DockoptParametersConfiguration.write_config_file(
            save_path, self.DEFAULT_CONFIG_FILE_PATH, overwrite=overwrite
        )

    @handle_run_func.__get__(0)
    def run(
        self,
        scheduler: str,
        job_dir_path: str = ".",
        config_file_path: str = None,
        actives_tgz_file_path: str = None,
        decoys_tgz_file_path: str = None,
        retrodock_job_max_reattempts: int = 0,
        retrodock_job_timeout_minutes: str = None,
        max_scheduler_jobs_running_at_a_time: str = None,  # TODO
        export_decoy_poses: bool = False,  # TODO
    ) -> None:
        # validate args
        if config_file_path is None:
            config_file_path = os.path.join(job_dir_path, self.CONFIG_FILE_NAME)
        if actives_tgz_file_path is None:
            actives_tgz_file_path = os.path.join(job_dir_path, self.ACTIVES_TGZ_FILE_NAME)
        if decoys_tgz_file_path is None:
            decoys_tgz_file_path = os.path.join(job_dir_path, self.DECOYS_TGZ_FILE_NAME)
        try:
            File.validate_file_exists(config_file_path)
        except FileNotFoundError:
            logger.error("Config file not found. Are you in the job directory?")
            return
        try:
            File.validate_file_exists(actives_tgz_file_path)
            File.validate_file_exists(decoys_tgz_file_path)
        except FileNotFoundError:
            logger.error(
                "Actives TGZ file and/or decoys TGZ file not found. Did you put them in the job directory?\nNote: if you do not have actives and decoys, please use blastermaster instead of dockopt."
            )
            return
        if scheduler not in SCHEDULER_NAME_TO_CLASS_DICT:
            logger.error(
                f"scheduler flag must be one of: {list(SCHEDULER_NAME_TO_CLASS_DICT.keys())}"
            )
            return

        #
        try:
            scheduler = SCHEDULER_NAME_TO_CLASS_DICT[scheduler]()
        except KeyError:
            logger.error(
                f"The following environmental variables are required to use the {scheduler} job scheduler: {SCHEDULER_NAME_TO_CLASS_DICT[scheduler].REQUIRED_ENV_VAR_NAMES}"
            )
            return

        #
        try:
            temp_storage_path = os.environ["TMPDIR"]
        except KeyError:
            logger.error(
                "The following environmental variables are required to submit retrodock jobs: TMPDIR"
            )
            return

        #
        retrodock_args_set = RetrodockArgsSet(
            scheduler=scheduler,
            actives_tgz_file_path=actives_tgz_file_path,
            decoys_tgz_file_path=decoys_tgz_file_path,
            temp_storage_path=temp_storage_path,
            retrodock_job_max_reattempts=retrodock_job_max_reattempts,
            retrodock_job_timeout_minutes=retrodock_job_timeout_minutes,
            max_scheduler_jobs_running_at_a_time=max_scheduler_jobs_running_at_a_time,
            export_decoy_poses=export_decoy_poses,
        )

        #
        logger.info("Loading config file...")
        config = DockoptParametersConfiguration(config_file_path)
        logger.info("done.")

        #
        config_params_str = "\n".join(
            [
                f"{param_name}: {param.value}"
                for param_name, param in flatten_and_parameter_cast_param_dict(
                    config.param_dict
                ).items()
            ]
        )
        logger.debug(f"Parameters:\n{config_params_str}")

        #
        blaster_file_names = list(get_dataclass_as_dict(BlasterFileNames()).values())
        blaster_files_to_copy_in = [
            os.path.abspath(f) for f in blaster_file_names if os.path.isfile(f)
        ]

        #
        pipeline = DockoptPipeline(
            **config.param_dict["pipeline"],
            dir_path=job_dir_path,
            results_manager=DockoptResultsManager("results.csv"),
            blaster_files_to_copy_in=blaster_files_to_copy_in,
        )
        pipeline.run(retrodock_args_set=retrodock_args_set)


class Step(PipelineComponent):
    WORKING_DIR_NAME = "working"
    RETRODOCK_JOBS_DIR_NAME = "retrodock_jobs"
    BEST_RETRODOCK_JOBS_DIR_NAME = "best_retrodock_jobs"

    def __init__(
        self,
            component_id: str,
            dir_path: str,
            criterion: str,
            top_n: int,
            results_manager: ResultsManager,
            parameters: Iterable[dict],
            blaster_files_to_copy_in: Iterable[BlasterFile],
            dock_files_to_copy_from_previous_step: Iterable[str],
    ):
        super().__init__(
            component_id=component_id,
            dir_path=dir_path,
            criterion=criterion,
            top_n=top_n,
            results_manager=results_manager,
        )

        #
        self.parameters = parameters

        #
        blaster_file_names = list(get_dataclass_as_dict(BlasterFileNames()).values())
        backup_blaster_file_paths = [
            os.path.join(DEFAULT_FILES_DIR_PATH, blaster_file_name)
            for blaster_file_name in blaster_file_names
        ]
        new_file_names = [
            f"{File.get_file_name_of_file(file_path)}_1"  # TODO
            for file_path in blaster_files_to_copy_in
        ]  # all nodes in graph will be numerically indexed, including input files
        new_backup_file_names = [
            f"{File.get_file_name_of_file(file_path)}_1"  # TODO
            for file_path in backup_blaster_file_paths
        ]  # ^
        self.working_dir = WorkingDir(
            path=os.path.join(self.dir.path, self.WORKING_DIR_NAME),
            create=True,
            reset=False,
            files_to_copy_in=blaster_files_to_copy_in,
            new_file_names=new_file_names,
            backup_files_to_copy_in=backup_blaster_file_paths,
            new_backup_file_names=new_backup_file_names,
        )
        self.retrodock_jobs_dir = Dir(
            path=os.path.join(self.dir.path, self.RETRODOCK_JOBS_DIR_NAME),
            create=True,
            reset=False,
        )
        self.best_retrodock_jobs_dir = Dir(
            path=os.path.join(self.dir.path, self.BEST_RETRODOCK_JOBS_DIR_NAME),
            create=True,
            reset=True,
        )

        # copy in dock files passed from previous component
        dock_file_identifier_to_dock_file_name_dict = BlasterFileNames().dock_file_identifier_to_dock_file_name_dict
        dock_file_name_to_num_witnessed_so_far_dict = {dock_file_name: 0 for dock_file_name in dock_file_identifier_to_dock_file_name_dict.values()}
        for dock_file in dock_files_to_copy_from_previous_step:
            for dock_file_identifier, dock_file_name in dock_file_identifier_to_dock_file_name_dict.items():
                if dock_file.startswith(dock_file_name):
                    new_dock_file_name = f"{dock_file_name}_{dock_file_name_to_num_witnessed_so_far_dict[dock_file_name]+1}"  # index starting at 1
                    self.working_dir.copy_in_file(dock_file, dst_file_name=dock_file_name)
                    dock_file_name_to_num_witnessed_so_far_dict[dock_file_name] += 1  # increment index for dock file name
                    break
            raise Exception(f"Witnessed 'dock_file'. Expected dock file name to start with one of: {dock_file_identifier_to_dock_file_name_dict.values()}")

        #
        self.actives_tgz_file = None  # set at beginning of .run()
        self.decoys_tgz_file = None  # set at beginning of .run()

        #
        self.blaster_files = BlasterFiles(working_dir=self.working_dir)

        #
        dock_files_generation_flat_param_dicts = (
            get_univalued_flat_parameter_cast_param_dicts_from_multivalued_param_dict(
                self.parameters["dock_files_generation"]
            )
        )
        param_dict_hashes = []
        for p_dict in dock_files_generation_flat_param_dicts:
            p_dict_items_interleaved_sorted_by_key_tuple = tuple(
                itertools.chain.from_iterable(
                    sorted(list(zip(*list(zip(*p_dict.items())))), key=lambda x: x[0])
                )
            )
            param_dict_hashes.append(
                get_persistent_hash_of_tuple(
                    p_dict_items_interleaved_sorted_by_key_tuple
                )
            )
        self.dock_files_generation_flat_param_dicts = [
            x
            for x, y in sorted(
                zip(dock_files_generation_flat_param_dicts, param_dict_hashes),
                key=lambda pair: pair[1],
            )
        ]

        # get directed acyclical graph defining how to get all combinations of dock files we need from the provided input files and parameters
        graph = nx.DiGraph()
        dock_file_nodes_combinations = []
        for (
            dock_files_generation_flat_param_dict
        ) in self.dock_files_generation_flat_param_dicts:
            # get config for get_blaster_steps
            # each value in dict must be an instance of Parameter
            steps = get_blaster_steps(
                blaster_files=self.blaster_files,
                flat_param_dict=dock_files_generation_flat_param_dict,
                working_dir=self.working_dir,
            )

            # form subgraph for this dock_files_generation_param_dict from the blaster steps it defines
            subgraph = nx.DiGraph()
            blaster_file_name_to_hash_dict = {}
            for step in steps:
                infiles_dict_items_list = sorted(step.infiles._asdict().items())
                outfiles_dict_items_list = sorted(step.outfiles._asdict().items())
                parameters_dict_items_list = sorted(step.parameters._asdict().items())

                # get infiles hashes
                infile_hash_tuples = []
                for infile_step_var_name, infile in infiles_dict_items_list:
                    if (
                        infile.original_file_in_working_dir.name
                        not in blaster_file_name_to_hash_dict
                    ):
                        blaster_file_name_to_hash_dict[
                            infile.original_file_in_working_dir.name
                        ] = get_persistent_hash_of_tuple(
                            (infile.original_file_in_working_dir.name,)
                        )
                    infile_hash_tuples.append(
                        (
                            infile_step_var_name,
                            blaster_file_name_to_hash_dict[
                                infile.original_file_in_working_dir.name
                            ],
                        )
                    )

                # get step hash from infile hashes, step dir, parameters, and outfiles
                step_hash = get_persistent_hash_of_tuple(
                    tuple(
                        infile_hash_tuples
                        + [step.__class__.__name__, step.step_dir.name]
                        + [
                            (parameter_step_var_name, parameter.__hash__())
                            for parameter_step_var_name, parameter in parameters_dict_items_list
                        ]
                        + [
                            (
                                outfile_step_var_name,
                                outfile.original_file_in_working_dir.name,
                            )
                            for outfile_step_var_name, outfile in outfiles_dict_items_list
                        ]
                    )
                )

                # get outfile hashes from step_hash
                for outfile_step_var_name, outfile in outfiles_dict_items_list:
                    blaster_file_name_to_hash_dict[
                        outfile.original_file_in_working_dir.name
                    ] = get_persistent_hash_of_tuple(
                        (step_hash, outfile.original_file_in_working_dir.name)
                    )

                # add infile nodes
                for infile in step.infiles:
                    if (
                        self._get_blaster_file_node_with_same_file_name(
                            infile.original_file_in_working_dir.name, subgraph
                        )
                        is not None
                    ):
                        continue
                    subgraph.add_node(
                        blaster_file_name_to_hash_dict[
                            infile.original_file_in_working_dir.name
                        ],
                        blaster_file=deepcopy(infile.original_file_in_working_dir),
                        original_blaster_file_name=infile.original_file_in_working_dir.name,
                    )

                # add outfile nodes
                for outfile in step.outfiles:
                    if self._get_blaster_file_node_with_same_file_name(
                        outfile.original_file_in_working_dir.name, subgraph
                    ):
                        raise Exception(
                            f"Attempting to add outfile to subgraph that already has said outfile as node: {outfile.original_file_in_working_dir.name}"
                        )
                    subgraph.add_node(
                        blaster_file_name_to_hash_dict[
                            outfile.original_file_in_working_dir.name
                        ],
                        blaster_file=deepcopy(outfile.original_file_in_working_dir),
                        original_blaster_file_name=outfile.original_file_in_working_dir.name,
                    )

                # add parameter nodes
                for parameter in step.parameters:
                    subgraph.add_node(
                        parameter.__hash__(), parameter=deepcopy(parameter)
                    )

                # connect each infile node to every outfile node
                for (infile_step_var_name, infile), (
                    outfile_step_var_name,
                    outfile,
                ) in itertools.product(
                    infiles_dict_items_list, outfiles_dict_items_list
                ):
                    subgraph.add_edge(
                        blaster_file_name_to_hash_dict[
                            infile.original_file_in_working_dir.name
                        ],
                        blaster_file_name_to_hash_dict[
                            outfile.original_file_in_working_dir.name
                        ],
                        step_class=step.__class__,
                        original_step_dir_name=step.step_dir.name,
                        step_instance=deepcopy(step),
                        step_hash=step_hash,
                        parent_node_step_var_name=infile_step_var_name,
                        child_node_step_var_name=outfile_step_var_name,
                    )

                # connect each parameter node to every outfile nodes
                for (parameter_step_var_name, parameter), (
                    outfile_step_var_name,
                    outfile,
                ) in itertools.product(
                    parameters_dict_items_list, outfiles_dict_items_list
                ):
                    subgraph.add_edge(
                        parameter.__hash__(),
                        blaster_file_name_to_hash_dict[
                            outfile.original_file_in_working_dir.name
                        ],
                        step_class=step.__class__,
                        original_step_dir_name=step.step_dir.name,
                        step_instance=deepcopy(
                            step
                        ),  # this will be replaced with step instance with unique dir path
                        step_hash=step_hash,
                        parent_node_step_var_name=parameter_step_var_name,
                        child_node_step_var_name=outfile_step_var_name,
                    )

            # record the combination of dock files for this subgraph
            dock_file_nodes_combinations.append(self._get_dock_file_nodes(subgraph))

            # merge subgraph into full graph
            graph = nx.compose(graph, subgraph)

        #
        self.dock_file_nodes_combinations = dock_file_nodes_combinations

        # update self.graph blaster_files' file paths
        blaster_file_nodes = [
            node_name
            for node_name, node_data in graph.nodes.items()
            if graph.nodes[node_name].get("blaster_file")
        ]
        blaster_file_nodes_sorted = sorted(blaster_file_nodes)

        #
        original_blaster_file_name_to_num_unique_instances_witnessed_so_far_counter = (
            collections.defaultdict(int)
        )
        for blaster_file_node in blaster_file_nodes_sorted:
            blaster_file = graph.nodes[blaster_file_node]["blaster_file"]
            original_blaster_file_name = graph.nodes[blaster_file_node][
                "original_blaster_file_name"
            ]
            original_blaster_file_name_to_num_unique_instances_witnessed_so_far_counter[
                original_blaster_file_name
            ] += 1
            blaster_file.path = f"{blaster_file.path}_{original_blaster_file_name_to_num_unique_instances_witnessed_so_far_counter[original_blaster_file_name]}"
            graph.nodes[blaster_file_node]["blaster_file"] = blaster_file

        #
        step_hash_to_edges_dict = collections.defaultdict(list)
        step_hash_to_step_class_instance_dict = {}
        for u, v, data in graph.edges(data=True):
            step_hash_to_edges_dict[data["step_hash"]].append((u, v))
            step_hash_to_step_class_instance_dict[data["step_hash"]] = data[
                "step_instance"
            ]
        step_hash_to_edges_dict_sorted = {
            key: value
            for key, value in sorted(
                step_hash_to_edges_dict.items(), key=lambda x: x[0]
            )
        }

        #
        original_step_dir_name_to_num_unique_instances_witnessed_so_far_counter = (
            collections.defaultdict(int)
        )
        step_hash_to_step_dir_path_dict = {}
        for step_hash, edges in step_hash_to_edges_dict_sorted.items():
            original_step_dir_name = graph.get_edge_data(*edges[0])[
                "original_step_dir_name"
            ]  # just get the first edge since they all have the same original_step_dir_name
            original_step_dir_name_to_num_unique_instances_witnessed_so_far_counter[
                original_step_dir_name
            ] += 1
            step_dir_path = graph.get_edge_data(*edges[0])[
                "step_instance"
            ].step_dir.path
            if step_hash not in step_hash_to_step_dir_path_dict:
                step_hash_to_step_dir_path_dict[
                    step_hash
                ] = f"{step_dir_path}_{original_step_dir_name_to_num_unique_instances_witnessed_so_far_counter[original_step_dir_name]}"

        #
        for step_hash, edges in step_hash_to_edges_dict_sorted.items():
            #
            step_dir = Dir(path=step_hash_to_step_dir_path_dict[step_hash])

            #
            kwargs = {"step_dir": step_dir}
            for (parent_node, child_node) in edges:
                edge_data_dict = graph.get_edge_data(parent_node, child_node)
                parent_node_data_dict = graph.nodes[parent_node]
                child_node_data_dict = graph.nodes[child_node]
                parent_node_step_var_name = edge_data_dict["parent_node_step_var_name"]
                child_node_step_var_name = edge_data_dict["child_node_step_var_name"]
                if "blaster_file" in parent_node_data_dict:
                    kwargs[parent_node_step_var_name] = parent_node_data_dict[
                        "blaster_file"
                    ]
                if "parameter" in parent_node_data_dict:
                    kwargs[parent_node_step_var_name] = parent_node_data_dict[
                        "parameter"
                    ]
                if "blaster_file" in child_node_data_dict:
                    kwargs[child_node_step_var_name] = child_node_data_dict[
                        "blaster_file"
                    ]
                if "parameter" in child_node_data_dict:
                    kwargs[child_node_step_var_name] = child_node_data_dict["parameter"]

            #
            step_class = graph.get_edge_data(*edges[0])["step_class"]
            step_hash_to_step_class_instance_dict[step_hash] = step_class(**kwargs)

            #
            for (parent_node, child_node) in edges:
                graph.get_edge_data(parent_node, child_node)[
                    "step_instance"
                ] = step_hash_to_step_class_instance_dict[step_hash]

        # validate that there are no cycles (i.e. that it is a DAG)
        if not nx.is_directed_acyclic_graph(graph):
            raise Exception("Cycle found in blaster targets DAG!")

        #
        self.graph = graph
        logger.debug(
            f"Graph initialized with:\n\tNodes: {self.graph.nodes}\n\tEdges: {self.graph.edges}"
        )

        dock_file_node_to_dock_files_arg_dict = {}
        for dock_file_nodes_combination in self.dock_file_nodes_combinations:
            for node in dock_file_nodes_combination:
                original_blaster_file_name = self.graph.nodes[node][
                    "original_blaster_file_name"
                ]
                dock_file_node_to_dock_files_arg_dict[
                    node
                ] = self.blaster_files.get_attribute_name_of_blaster_file_with_file_name(
                    original_blaster_file_name
                )
        self.dock_file_node_to_dock_files_arg_dict = (
            dock_file_node_to_dock_files_arg_dict
        )

    def run(self, retrodock_args_set: RetrodockArgsSet) -> pd.core.frame.DataFrame:
        if retrodock_args_set.actives_tgz_file_path is not None:
            self.actives_tgz_file = File(path=retrodock_args_set.actives_tgz_file_path)
        else:
            self.actives_tgz_file = None
        if retrodock_args_set.decoys_tgz_file_path is not None:
            self.decoys_tgz_file = File(path=retrodock_args_set.decoys_tgz_file_path)
        else:
            self.decoys_tgz_file = None

        # run necessary steps to get all dock files
        logger.info("Generating dock files for all docking configurations")
        for dock_file_nodes_combination in self.dock_file_nodes_combinations:
            for dock_file_node in dock_file_nodes_combination:
                self._run_unrun_steps_needed_to_create_this_blaster_file_node(
                    dock_file_node, self.graph
                )

        #
        logger.info("Getting dock files combinations...")
        dock_files_combinations = []
        for dock_file_nodes_combination in self.dock_file_nodes_combinations:
            kwargs = {}
            for node in dock_file_nodes_combination:
                kwargs[
                    self.dock_file_node_to_dock_files_arg_dict[node]
                ] = self.graph.nodes[node]["blaster_file"]
            dock_files_combinations.append(DockFiles(**kwargs))

        #
        dock_files_modification_flat_param_dicts = (
            get_univalued_flat_parameter_cast_param_dicts_from_multivalued_param_dict(
                self.parameters["dock_files_modification"]
            )
        )
        logger.info("done.")

        #
        if (
            len(
                list(
                    set(
                        [
                            flat_param_dict["matching_spheres_perturbation.use"].value
                            for flat_param_dict in dock_files_modification_flat_param_dicts
                        ]
                    )
                )
            )
            != 1
        ):
            raise Exception(
                "matching_spheres_perturbation.use cannot be both True and False."
            )

        # matching spheres perturbation
        if dock_files_modification_flat_param_dicts[0][
            "matching_spheres_perturbation.use"
        ].value:
            logger.info("Running matching spheres perturbation...")
            dock_files_combinations_after_modifications = []
            dock_files_generation_flat_param_dicts_after_modifications = []
            dock_files_modification_flat_param_dicts_after_modifications = []
            for (
                dock_files_modification_flat_param_dict
            ) in dock_files_modification_flat_param_dicts:
                #
                unperturbed_file_name_to_perturbed_file_names_dict = (
                    collections.defaultdict(list)
                )
                for node_name, node_data in self.graph.nodes(data=True):
                    if node_data.get("blaster_file") is None:
                        continue
                    if (
                        node_data["original_blaster_file_name"]
                        == self.blaster_files.matching_spheres_file.name
                    ):
                        file_name = node_data["blaster_file"].name
                        spheres = read_sph(
                            os.path.join(self.working_dir.path, file_name),
                            chosen_cluster="A",
                            color="A",
                        )

                        #
                        for i in range(
                            int(
                                dock_files_modification_flat_param_dict[
                                    "matching_spheres_perturbation.num_samples_per_matching_spheres_file"
                                ].value
                            )
                        ):
                            #
                            perturbed_file_name = f"{file_name}_{i + 1}"
                            perturbed_file_path = os.path.join(
                                self.working_dir.path, perturbed_file_name
                            )
                            unperturbed_file_name_to_perturbed_file_names_dict[
                                file_name
                            ].append(perturbed_file_name)

                            # skip perturbation if perturbed file already exists
                            if File.file_exists(perturbed_file_path):
                                continue

                            # perturb all spheres in file
                            new_spheres = []
                            for sphere in spheres:
                                new_sphere = copy(sphere)
                                max_deviation = float(
                                    dock_files_modification_flat_param_dict[
                                        "matching_spheres_perturbation.max_deviation_angstroms"
                                    ].value
                                )
                                perturbation_xyz = tuple(
                                    [
                                        random.uniform(
                                            -max_deviation,
                                            max_deviation,
                                        )
                                        for _ in range(3)
                                    ]
                                )
                                new_sphere.X += perturbation_xyz[0]
                                new_sphere.Y += perturbation_xyz[1]
                                new_sphere.Z += perturbation_xyz[2]
                                new_spheres.append(new_sphere)

                            # write perturbed spheres to new matching spheres file
                            write_sph(perturbed_file_path, new_spheres)

                #
                for i, (
                    dock_files_combination,
                    dock_files_generation_flat_param_dict,
                ) in enumerate(
                    zip(
                        dock_files_combinations,
                        self.dock_files_generation_flat_param_dicts,
                    )
                ):
                    for (
                        perturbed_file_name
                    ) in unperturbed_file_name_to_perturbed_file_names_dict[
                        dock_files_combination.matching_spheres_file.name
                    ]:
                        new_dock_files_combination = copy(dock_files_combination)
                        new_dock_files_combination.matching_spheres_file = BlasterFile(
                            os.path.join(self.working_dir.path, perturbed_file_name)
                        )
                        dock_files_combinations_after_modifications.append(
                            new_dock_files_combination
                        )
                        dock_files_generation_flat_param_dicts_after_modifications.append(
                            dock_files_generation_flat_param_dict
                        )
                        dock_files_modification_flat_param_dicts_after_modifications.append(
                            dock_files_modification_flat_param_dict
                        )
            logger.info("done")
        else:
            dock_files_combinations_after_modifications = dock_files_combinations
            dock_files_generation_flat_param_dicts_after_modifications = (
                self.dock_files_generation_flat_param_dicts
            )
            dock_files_modification_flat_param_dicts_after_modifications = (
                dock_files_modification_flat_param_dicts
            )

        #
        indock_flat_param_dicts = (
            get_univalued_flat_parameter_cast_param_dicts_from_multivalued_param_dict(
                self.parameters["indock"]
            )
        )

        #
        if isinstance(self.parameters["custom_dock_executable"], list):
            dock_executable_paths = []
            for dock_executable_path in self.parameters["custom_dock_executable"].value:
                if dock_executable_path is None:
                    dock_executable_paths.append(DOCK3_EXECUTABLE_PATH)
                else:
                    dock_executable_paths.append(dock_executable_path)
        else:
            if self.parameters["custom_dock_executable"] is None:
                dock_executable_paths = [DOCK3_EXECUTABLE_PATH]
            else:
                dock_executable_paths = [self.parameters["custom_dock_executable"]]

        #
        docking_configuration_info_combinations = list(
            itertools.product(
                dock_executable_paths,
                zip(
                    dock_files_combinations_after_modifications,
                    dock_files_generation_flat_param_dicts_after_modifications,
                    dock_files_modification_flat_param_dicts_after_modifications,
                ),
                indock_flat_param_dicts,
            )
        )

        # make indock file for each combination of (1) set of dock files and (2) indock_flat_param_dict
        logger.info("Making INDOCK files...")
        flat_param_dicts = []
        docking_configurations = []
        for i, (
            dock_executable_path,
            (
                dock_files,
                dock_files_generation_flat_param_dict,
                dock_files_modification_flat_param_dict,
            ),
            indock_flat_param_dict,
        ) in enumerate(docking_configuration_info_combinations):
            # get full flat parameter dict
            flat_param_dict = {}
            flat_param_dict["dock_executable_path"] = dock_executable_path
            flat_param_dict.update(
                {
                    f"dock_files_generation.{key}": value
                    for key, value in dock_files_generation_flat_param_dict.items()
                }
            )
            flat_param_dict.update(
                {
                    f"dock_files_modification.{key}": value
                    for key, value in dock_files_modification_flat_param_dict.items()
                }
            )
            flat_param_dict.update(
                {
                    f"indock.{key}": value
                    for key, value in indock_flat_param_dict.items()
                }
            )

            # make indock file for each combination of dock files
            indock_file_name = f"{INDOCK_FILE_NAME}_{i + 1}"
            indock_file = IndockFile(
                path=os.path.join(self.working_dir.path, indock_file_name)
            )
            indock_file.write(dock_files, flat_param_dict)

            #
            flat_param_dicts.append(flat_param_dict)
            docking_configurations.append(
                (dock_executable_path, dock_files, indock_file)
            )

        # TODO: improve this
        all_docking_configuration_file_names = []
        for node_name, node_data in self.graph.nodes.items():
            original_blaster_file_name = node_data.get("original_blaster_file_name")
            if original_blaster_file_name is not None:
                all_docking_configuration_file_names.append(
                    node_data["blaster_file"].path
                )
        unique_dock_file_nodes = list(
            set(
                [
                    node
                    for dock_file_nodes_combination in self.dock_file_nodes_combinations
                    for node in dock_file_nodes_combination
                ]
            )
        )
        for node in unique_dock_file_nodes:
            all_docking_configuration_file_names.append(
                self.graph.nodes[node]["blaster_file"].name
            )

        #
        job_hash = dirhash(
            self.working_dir.path,
            "md5",
            match=all_docking_configuration_file_names,
        )
        with open(os.path.join(self.dir.path, "job_hash.md5"), "w") as f:
            f.write(f"{job_hash}\n")

        # write actives tgz and decoys tgz file paths to actives_and_decoys.sdi
        logger.info("Writing actives_and_decoys.sdi file...")
        retrodock_input_sdi_file = File(
            path=os.path.join(self.dir.path, "actives_and_decoys.sdi")
        )
        with open(retrodock_input_sdi_file.path, "w") as f:
            f.write(f"{self.actives_tgz_file.path}\n")
            f.write(f"{self.decoys_tgz_file.path}\n")
        logger.info("done")

        #
        retrodock_jobs = []
        retrodock_job_dir_path_to_docking_configuration_file_names_dict = {}
        for i, (dock_executable_path, dock_files, indock_file) in enumerate(
            docking_configurations
        ):
            #
            retro_dock_job_dir_path = os.path.join(
                self.retrodock_jobs_dir.path, str(i + 1)
            )
            docking_configuration_file_names = [
                getattr(dock_files, dock_file_field.name).name
                for dock_file_field in fields(dock_files)
            ] + [indock_file.name]
            retrodock_job_dir_path_to_docking_configuration_file_names_dict[
                retro_dock_job_dir_path
            ] = docking_configuration_file_names

            #
            retrodock_job_dir = Dir(
                path=retro_dock_job_dir_path,
                create=True,
            )

            #
            retrodock_job = RetrodockJob(
                name=f"dockopt_job_{job_hash}_{retrodock_job_dir.name}",
                job_dir=retrodock_job_dir,
                input_sdi_file=retrodock_input_sdi_file,
                dock_files=dock_files,
                indock_file=indock_file,
                job_scheduler=retrodock_args_set.scheduler,
                dock_executable_path=dock_executable_path,
                temp_storage_path=retrodock_args_set.temp_storage_path,
                max_reattempts=retrodock_args_set.retrodock_job_max_reattempts,
            )
            retrodock_jobs.append(retrodock_job)
        logger.debug("done")

        # submit docking jobs
        for retrodock_job in retrodock_jobs:
            sub_result, proc = retrodock_job.submit(
                job_timeout_minutes=retrodock_args_set.retrodock_job_timeout_minutes,
                skip_if_complete=True,
            )
            log_job_submission_result(retrodock_job, sub_result, proc)

        # make a queue of tuples containing job-relevant data for processing
        RetrodockJobInfoTuple = collections.namedtuple(
            "RetrodockJobInfoTuple", "job flat_param_dict"
        )
        retrodock_jobs_processing_queue = [
            RetrodockJobInfoTuple(
                retrodock_jobs[i], flat_param_dicts[i]
            )
            for i in range(len(retrodock_jobs))
        ]

        # process results of docking jobs
        logger.info(
            f"Awaiting / processing retrodock job results ({len(retrodock_jobs)} jobs in total)"
        )
        data_dicts = []
        while len(retrodock_jobs_processing_queue) > 0:
            #
            retrodock_job_info_tuple = retrodock_jobs_processing_queue.pop(0)
            retrodock_job, flat_param_dict = retrodock_job_info_tuple

            #
            if retrodock_job.is_running:
                retrodock_jobs_processing_queue.append(
                    retrodock_job_info_tuple
                )  # move job to back of queue
                time.sleep(
                    1
                )  # sleep a bit while waiting for outdock file in order to avoid wasteful queue-cycling
                continue  # move on to next job in queue while job continues to run
            else:
                if (
                    not retrodock_job.is_complete
                ):  # not all expected OUTDOCK files exist yet
                    time.sleep(
                        1
                    )  # sleep for a bit and check again in case job just finished
                    if not retrodock_job.is_complete:
                        # job must have timed out / failed
                        logger.warning(
                            f"Job failure / time out witnessed for job: {retrodock_job.name}"
                        )
                        if retrodock_job.num_attempts > retrodock_job_max_reattempts:
                            logger.warning(
                                f"Max job reattempts exhausted for job: {retrodock_job.name}"
                            )
                            continue  # move on to next job in queue without re-attempting failed job

                        retrodock_job.submit(
                            job_timeout_minutes=retrodock_job_timeout_minutes,
                            skip_if_complete=False,
                        )  # re-attempt job
                        retrodock_jobs_processing_queue.append(
                            retrodock_job_info_tuple
                        )  # move job to back of queue
                        continue  # move on to next job in queue while docking job runs

            # load outdock file and get dataframe
            try:
                # get dataframe of actives job results and decoys job results combined
                df = (
                    get_results_dataframe_from_actives_job_and_decoys_job_outdock_files(
                        retrodock_job.actives_outdock_file.path, retrodock_job.decoys_outdock_file.path
                    )
                )
            except Exception as e:  # if outdock file failed to be parsed then re-attempt job
                logger.warning(f"Failed to parse outdock file(s) due to error: {e}")
                if retrodock_job.num_attempts > retrodock_job_max_reattempts:
                    logger.warning(
                        f"Max job reattempts exhausted for job: {retrodock_job.name}"
                    )
                    continue  # move on to next job in queue without re-attempting failed job

                retrodock_job.submit(
                    job_timeout_minutes=retrodock_job_timeout_minutes,
                    skip_if_complete=False,
                )  # re-attempt job
                retrodock_jobs_processing_queue.append(
                    retrodock_job_info_tuple
                )  # move job to back of queue
                continue  # move on to next job in queue while docking job runs

            #
            logger.info(
                f"Docking job '{retrodock_job.name}' completed. Successfully loaded OUTDOCK file(s)."
            )

            # sort dataframe by total energy score
            df["total_energy"] = df["total_energy"].astype(float)
            df = df.sort_values(
                by=["total_energy", "is_active"], na_position="last", ignore_index=True
            )  # sorting secondarily by 'is_active' (0 or 1) ensures that decoys are ranked before actives in case they have the same exact score (pessimistic approach)
            df = df.drop_duplicates(
                subset=["db2_file_path"], keep="first", ignore_index=True
            )

            # make data dict for this job (will be used to make dataframe for results of all jobs)
            data_dict = copy(flat_param_dict)
            data_dict[RETRODOCK_JOB_DIR_PATH_COLUMN_NAME] = retrodock_job.job_dir.path

            # get ROC and calculate enrichment score of this job's docking set-up
            if isinstance(self.criterion, EnrichmentScore):
                logger.debug("Calculating ROC and enrichment score...")
                booleans = df["is_active"]
                data_dict[self.criterion.name] = self.criterion.calculate(
                    booleans,
                    image_save_path=os.path.join(
                        retrodock_job.job_dir.path, ROC_PLOT_FILE_NAME
                    ),
                )
                logger.debug("done.")

            # save data_dict for this job
            data_dicts.append(data_dict)

        # write jobs completion status
        num_jobs_completed = len(
            [1 for retrodock_job in retrodock_jobs if retrodock_job.is_complete]
        )
        logger.info(
            f"Finished {num_jobs_completed} out of {len(retrodock_jobs)} retrodock jobs."
        )
        if num_jobs_completed == 0:
            logger.error(
                "All retrodock jobs failed. Something is wrong. Please check logs."
            )
            return

        # make dataframe of optimization job results
        df = pd.DataFrame(data=data_dicts)

        return df


        df = df.sort_values(by=self.criterion.name, ascending=False, ignore_index=True)  # TODO: get rid of this if opt results saving is moved to decorator

        # save optimization job results dataframe to csv
        optimization_results_csv_file_path = os.path.join(  # TODO: move this to a decorator, perhaps
            self.dir.path, RESULTS_CSV_FILE_NAME
        )
        logger.debug(
            f"Saving optimization job results to {optimization_results_csv_file_path}"
        )
        df.to_csv(optimization_results_csv_file_path)

        # copy best job to output dir
        logger.debug(
            f"Copying top {self.top_n} retrodock jobs to {self.best_retrodock_jobs_dir.path}"
        )
        if os.path.isdir(self.best_retrodock_jobs_dir.path):
            shutil.rmtree(self.best_retrodock_jobs_dir.path, ignore_errors=True)
        for i, best_retrodock_job_dir_path in enumerate(
            df.head(self.top_n)[RETRODOCK_JOB_DIR_PATH_COLUMN_NAME]
        ):
            dst_best_job_dir_path = os.path.join(
                self.best_retrodock_jobs_dir.path, str(i + 1)
            )
            shutil.copytree(
                best_retrodock_job_dir_path,
                dst_best_job_dir_path,
            )

            # copy docking configuration files to best jobs dir
            best_job_dockfiles_dir = Dir(
                os.path.join(dst_best_job_dir_path, "dockfiles"), create=True
            )
            for (
                file_name
            ) in retrodock_job_dir_path_to_docking_configuration_file_names_dict[
                best_retrodock_job_dir_path
            ]:
                best_job_dockfiles_dir.copy_in_file(
                    os.path.join(self.working_dir.path, file_name)
                )

            #
            df_best_job = (
                get_results_dataframe_from_actives_job_and_decoys_job_outdock_files(
                    actives_outdock_file_path=os.path.join(
                        best_retrodock_job_dir_path,
                        "output",
                        "1",
                        "OUTDOCK.0",
                    ),
                    decoys_outdock_file_path=os.path.join(
                        best_retrodock_job_dir_path,
                        "output",
                        "2",
                        "OUTDOCK.0",
                    ),
                )
            )

            # sort dataframe by total energy score
            df_best_job = df_best_job.sort_values(
                by=["total_energy", "is_active"], na_position="last", ignore_index=True
            )  # sorting secondarily by 'is_active' (0 or 1) ensures that decoys are ranked before actives in case they have the same exact score (pessimistic approach)
            df_best_job = df_best_job.drop_duplicates(
                subset=["db2_file_path"], keep="first", ignore_index=True
            )  # keep only the best score per molecule

            # get ROC and calculate enrichment score of this job's docking set-up
            # TODO: get this from Retrodock instead
            booleans = df_best_job["is_active"].astype(bool)
            roc = ROC(booleans)

            # write ROC plot image
            roc_plot_image_path = os.path.join(dst_best_job_dir_path, ROC_PLOT_FILE_NAME)
            roc.plot(save_path=roc_plot_image_path)

            # ridge plot for energy terms
            # TODO: get this from Retrodock instead
            pivot_rows = []
            for i, row in df_best_job.iterrows():
                for col in [
                    "total_energy",
                    "electrostatic_energy",
                    "vdw_energy",
                    "polar_desolvation_energy",
                    "apolar_desolvation_energy",
                ]:
                    pivot_row = {"energy_term": col}
                    if row["is_active"] == 1:
                        pivot_row["active"] = str_to_float(row[col])
                        pivot_row["decoy"] = np.nan
                    else:
                        pivot_row["active"] = np.nan
                        pivot_row["decoy"] = str_to_float(row[col])
                    pivot_rows.append(pivot_row)
            df_best_job_pivot = pd.DataFrame(pivot_rows)
            fig, ax = joyplot(
                data=df_best_job_pivot,
                by="energy_term",
                column=["active", "decoy"],
                color=["#686de0", "#eb4d4b"],
                legend=True,
                alpha=0.85,
                figsize=(12, 8),
                ylim="own",
            )
            plt.title("ridgeline plot: energy terms (actives vs. decoys)")
            plt.tight_layout()
            plt.savefig(os.path.join(dst_best_job_dir_path, ENERGY_PLOT_FILE_NAME))
            plt.close(fig)

            # split violin plot of charges
            # TODO: get this from Retrodock instead
            fig = plt.figure()
            sns.violinplot(
                data=df_best_job,
                x="charge",
                y="total_energy",
                split=True,
                hue="activity_class",
            )
            plt.title("split violin plot: charge (actives vs. decoys)")
            plt.tight_layout()
            plt.savefig(os.path.join(dst_best_job_dir_path, CHARGE_PLOT_FILE_NAME))
            plt.close(fig)

        return df

    @staticmethod
    def _get_blaster_file_node_with_same_file_name(
        name: str,
        g: nx.classes.digraph.DiGraph,
    ) -> BlasterFile:
        blaster_file_node_names = [
            node_name
            for node_name, node_data in g.nodes.items()
            if g.nodes[node_name].get("blaster_file")
        ]
        if len(blaster_file_node_names) == 0:
            return None
        blaster_file_nodes_with_same_file_name = [
            blaster_file_node_name
            for blaster_file_node_name in blaster_file_node_names
            if name == g.nodes[blaster_file_node_name]["blaster_file"].name
        ]
        if len(blaster_file_nodes_with_same_file_name) == 0:
            return None
        (
            blaster_file_node_with_same_file_name,
        ) = blaster_file_nodes_with_same_file_name

        return blaster_file_node_with_same_file_name

    @staticmethod
    def _get_start_nodes(g: nx.classes.digraph.DiGraph) -> List[BlasterFile]:
        start_nodes = []
        for node_name, node_data in g.nodes.items():
            if g.in_degree(node_name) == 0:
                start_nodes.append(node_name)
        return start_nodes

    @staticmethod
    def _get_dock_file_nodes(g: nx.classes.digraph.DiGraph):
        dock_file_names = list(BlasterFileNames().dock_file_identifier_to_dock_file_name_dict.values())
        end_nodes = []
        for node_name, node_data in g.nodes.items():
            if node_data.get("blaster_file") is not None:
                if node_data["blaster_file"].name in dock_file_names:
                    end_nodes.append(node_name)
        return end_nodes

    @staticmethod
    def _run_unrun_steps_needed_to_create_this_blaster_file_node(
        blaster_file_node: str,
        g: nx.classes.digraph.DiGraph,
    ):
        blaster_file = g.nodes[blaster_file_node].get("blaster_file")

        if blaster_file is not None:
            if not blaster_file.exists:
                for parent_node in g.predecessors(blaster_file_node):
                    Step._run_unrun_steps_needed_to_create_this_blaster_file_node(
                        parent_node, g
                    )
                a_parent_node = list(g.predecessors(blaster_file_node))[0]
                step_instance = g[a_parent_node][blaster_file_node]["step_instance"]
                if step_instance.is_done:
                    raise Exception(
                        f"blaster file {blaster_file.path} does not exist but step instance is_done=True"
                    )
                step_instance.run()


def get_parameters_with_next_step_reference_value_replaced(parameters: dict, nested_target_keys: str, new_ref: float, old_ref: str = '^') -> dict:
    """Takes a set of parameters, finds the next nested step to be run, and, if it
    contains numerical operators, replaces the `reference_value` of the `target_key`
     with the specified float `new_ref` if `reference_value` matches the string
     `old_ref`."""

    def get_nested_dict_item(dic, nested_keys):
        """Get item in nested dictionary"""
        return reduce(getitem, nested_keys, dic)

    def set_nested_dict_item(dic, nested_keys, value):
        """Set item in nested dictionary"""
        reduce(getitem, nested_keys[:-1], dic)[nested_keys[-1]] = value
        return dic

    def traverse(obj):
        if isinstance(obj, dict):  # obj is step
            nested_target = get_nested_dict_item(obj['step'], nested_target_keys)
            if isinstance(nested_target, dict):
                if 'reference_value' in nested_target and 'arguments' in nested_target and 'operator' in nested_target:  # numerical operator detected
                    # replace old ref with new ref
                    if nested_target['reference_value'] == old_ref:
                        obj = set_nested_dict_item(step, nested_target_keys + ['reference_value'], new_ref)
            return obj
        elif isinstance(obj, list):  # obj is sequence
            obj[0] = traverse(obj[0])  # only change next step to be run, which will be found in the first element
            return obj
        else:
            raise ValueError("Expected type `list` or `dict`.")

    return traverse(deepcopy(parameters))


def get_parameters_with_next_step_numerical_operators_applied(parameters: dict) -> dict:
    """Takes a set of parameters, finds the next nested step to be run, and, if it
    contains numerical operators, applies them."""

    def traverse(obj):
        if isinstance(obj, dict):  # obj is step
            if 'reference_value' in obj and 'arguments' in obj and 'operator' in obj:  # numerical operator detected
                # apply operators
                if obj['operator'] == '+':
                    obj = [obj['reference_value'] + x for x in obj['arguments']]
                elif obj['operator'] == '-':
                    obj = [obj['reference_value'] - x for x in obj['arguments']]
                elif obj['operator'] == '*':
                    obj = [obj['reference_value'] * x for x in obj['arguments']]
                elif obj['operator'] == '/':
                    obj = [obj['reference_value'] / x for x in obj['arguments']]
                else:
                    raise ValueError(f"Witnessed operator `{obj['operator']}`. Only the following numerical operators are supported: `+`, `-`, `*`, `/`")
            return obj
        elif isinstance(obj, list):  # obj is sequence
            obj[0] = traverse(obj[0])  # only change next step to be run, which will be found in the first element
            return obj
        else:
            return obj

    return traverse(deepcopy(parameters))


def get_dock_files_to_copy_from_previous_step_dict_for_next_step(parameters: dict) -> dict:
    """Takes a set of parameters, finds the next nested step to be run, and returns the dict under its
    `dock_files_to_copy_from_previous_step` key."""

    def traverse(obj):
        if isinstance(obj, dict):  # obj is step
            if 'dock_files_to_copy_from_previous_step' in obj:
                return obj['dock_files_to_copy_from_previous_step']
            else:
                raise ValueError(f"Expected key `dock_files_to_copy_from_previous_step`. Witnessed dict: {obj}")
        elif isinstance(obj, list):  # obj is sequence
            return traverse(obj[0])  # next step to be run will be found in the first element
        else:
            raise ValueError("Expected type `list` or `dict`.")


    return traverse(deepcopy(parameters))


def load_nested_target_keys_and_value_tuples_from_dataframe_row(row, identifier_prefix: str = 'parameters.'):
    """Loads the parameters in a dataframe row according to the column names."""

    dic = row.to_dict('records')[0]
    for key in dic:
        if key.startswith(identifier_prefix):
            del dic[key]

    nested_target_keys_and_value_tuples = [((key.strip(identifier_prefix).split('.')), value) for key, value in dic.items()]

    return nested_target_keys_and_value_tuples


def load_dock_file_names_dict_from_dataframe_row(row, identifier_prefix: str = 'dockfiles.'):
    """Loads the dock file names from dataframe row according to the column names."""

    dic = row.to_dict('records')[0]
    for key in dic:
        if not key.startswith(identifier_prefix):
            del dic[key]

    return dic


class Sequence(PipelineComponentSequence):
    def __init__(
        self,
        component_id: str,
        param_dict: dict,
        dir_path: str,
        criterion: str,
        top_n: int,
        results_manager: ResultsManager,
        components: Iterable[dict],
        num_repetitions: int,
        max_iterations_with_no_improvement: int,
        blaster_files_to_copy_in: Iterable[BlasterFile],
    ):
        super().__init__(
            component_id=component_id,
            param_dict=param_dict,
            dir_path=dir_path,
            criterion=criterion,
            top_n=top_n,
            results_manager=results_manager,
            components=components,
            num_repetitions=num_repetitions,
            max_iterations_with_no_improvement=max_iterations_with_no_improvement,
        )

        self.blaster_files_to_copy_in = blaster_files_to_copy_in

    def run(self, retrodock_args_set: RetrodockArgsSet) -> pd.core.frame.DataFrame:
        #
        dock_file_identifier_to_default_dock_file_name_dict = BlasterFileNames().dock_file_identifier_to_dock_file_name_dict

        #
        df = pd.DataFrame()
        last_component_completed = None
        best_criterion_value_witnessed = -float('inf')
        num_iterations_left_with_no_improvement = self.max_iterations_with_no_improvement
        for i in range(self.num_repetitions):
            df_iteration = pd.DataFrame()
            component_id = f"{self.component_id}.iter={i+1}"
            iter_dir_path = os.path.join(self.dir.path, f"iter={i+1}")
            for j, kwargs in enumerate(self.components):
                #
                if "components" in kwargs:
                    component_identifier = "sequence"
                else:
                    component_identifier = "step"

                #
                kwargs['component_id'] = f"{component_id}.{j+1}"
                kwargs['dir_path'] = os.path.join(iter_dir_path, str(j+1))
                kwargs['results_manager'] = self.results_manager
                kwargs['blaster_files_to_copy_in'] = self.blaster_files_to_copy_in

                #
                if last_component_completed is None:
                    kwargs['dock_files_to_copy_from_previous_step'] = []
                else:
                    dock_files_to_copy_from_previous_step = []
                    for row_index, row in last_component_completed.load_results_dataframe().head(self.top_n).iterrows():
                        dock_file_names_dict = load_dock_file_names_dict_from_dataframe_row(row, identifier_prefix="dockfiles.")
                        dock_files_to_copy_from_previous_step_dict = get_dock_files_to_copy_from_previous_step_dict_for_next_step(kwargs)
                        for dock_file_identifier, should_be_copied in dock_files_to_copy_from_previous_step_dict.items():
                            if should_be_copied:
                                dock_file_name = dock_file_names_dict[dock_file_identifier]
                                dock_file_path = os.path.join(component.working_dir.path, dock_file_name)
                                dock_files_to_copy_from_previous_step.append(dock_file_path)
                    kwargs['dock_files_to_copy_from_previous_step'] = dock_files_to_copy_from_previous_step

                #
                if last_component_completed is not None:
                    for row_index, row in last_component_completed.load_results_dataframe().head(self.top_n).iterrows():
                        nested_target_keys_and_value_tuples = load_nested_target_keys_and_value_tuples_from_dataframe_row(row, identifier_prefix='parameters.')
                        for nested_target_keys, value in nested_target_keys_and_value_tuples:
                            kwargs = get_parameters_with_next_step_reference_value_replaced(nested_target_keys, value, old_ref='^')

                #
                kwargs = get_parameters_with_next_step_numerical_operators_applied(kwargs)

                #
                if component_identifier == "step":
                    component = Step(**kwargs)
                elif component_identifier == "sequence":
                    component = Sequence(**kwargs)
                else:
                    raise ValueError(
                        f"Only `step` and `sequence` are component identifiers. Witnessed `{component_identifier}`")

                #
                component.run(retrodock_args_set)

                #
                df_component = component.load_results_dataframe()
                df_component = df_component.head(component.top_n)
                df_component["pipeline_component_id"] = [
                    component.component_id for _ in range(len(df_component))
                ]
                df_iteration = pd.concat([df_iteration, df_component], ignore_index=True)

            #
            df = pd.concat([df, df_iteration], ignore_index=True)

            #
            best_criterion_value_witnessed_this_iteration = df_iteration[component.criterion.name].max()
            if best_criterion_value_witnessed_this_iteration <= best_criterion_value_witnessed:
                if num_iterations_left_with_no_improvement == 0:
                    break
                else:
                    num_iterations_left_with_no_improvement -= 1

            #
            last_component_completed = component

        return df


class DockoptPipeline(Pipeline):
    def __init__(
            self,
            dir_path: str,
            criterion: str,
            top_n: int,
            results_manager: ResultsManager,
            components: Iterable[dict],
            blaster_files_to_copy_in: Iterable[BlasterFile],
    ):
        super().__init__(
            dir_path=dir_path,
            criterion=criterion,
            top_n=top_n,
            results_manager=results_manager,
            components=components,
        )

        #
        self.blaster_files_to_copy_in = blaster_files_to_copy_in

    def run(
            self,
            retrodock_args_set: RetrodockArgsSet
    ) -> pd.core.frame.DataFrame:
        #
        df = pd.DataFrame()
        last_component_completed = None
        best_criterion_value_witnessed = -float('inf')
        for i, kwargs in enumerate(self.components):
            #
            if "components" in kwargs:
                component_identifier = "sequence"
            else:
                component_identifier = "step"

            #
            kwargs['component_id'] = f"{i+1}"
            kwargs['dir_path'] = os.path.join(self.dir.path, str(i+1))
            kwargs['results_manager'] = self.results_manager
            kwargs['blaster_files_to_copy_in'] = self.blaster_files_to_copy_in

            #
            if last_component_completed is None:
                kwargs['dock_files_to_copy_from_previous_step'] = []
            else:
                dock_files_to_copy_from_previous_step = []
                for row_index, row in last_component_completed.load_results_dataframe().head(
                        self.top_n).iterrows():
                    dock_file_names_dict = load_dock_file_names_dict_from_dataframe_row(
                        row, identifier_prefix="dockfiles.")
                    dock_files_to_copy_from_previous_step_dict = get_dock_files_to_copy_from_previous_step_dict_for_next_step(
                        kwargs)
                    for dock_file_identifier, should_be_copied in dock_files_to_copy_from_previous_step_dict.items():
                        if should_be_copied:
                            dock_file_name = dock_file_names_dict[
                                dock_file_identifier]
                            dock_file_path = os.path.join(
                                component.working_dir.path,
                                dock_file_name)
                            dock_files_to_copy_from_previous_step.append(dock_file_path)
                kwargs['dock_files_to_copy_from_previous_step'] = dock_files_to_copy_from_previous_step

            #
            if last_component_completed is not None:
                for row_index, row in last_component_completed.load_results_dataframe().head(
                        self.top_n).iterrows():
                    nested_target_keys_and_value_tuples = load_nested_target_keys_and_value_tuples_from_dataframe_row(
                        row, identifier_prefix='parameters.')
                    for nested_target_keys, value in nested_target_keys_and_value_tuples:
                        kwargs = get_parameters_with_next_step_reference_value_replaced(
                            nested_target_keys, value, old_ref='^')

            #
            kwargs = get_parameters_with_next_step_numerical_operators_applied(kwargs)

            #
            if component_identifier == "step":
                component = Step(**kwargs)
            elif component_identifier == "sequence":
                component = Sequence(**kwargs)
            else:
                raise ValueError(
                    f"Only `step` and `sequence` are component identifiers. Witnessed `{component_identifier}`")

            #
            component.run(retrodock_args_set)

            #
            df_component = component.load_results_dataframe()
            df_component = df_component.head(component.top_n)
            df_component["pipeline_component_id"] = [
                component.component_id for _ in range(len(df_component))
            ]
            df = pd.concat([df, df_component], ignore_index=True)

            #
            last_component_completed = component

        return df
