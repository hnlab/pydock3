from dataclasses import dataclass, fields
import subprocess
import logging
import os
import sys
import traceback

import pandas as pd
import yamale
import oyaml as yaml

from ucsfdock.files import File


#
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

#
logging_formatter = logging.Formatter(
    "%(asctime)s;%(levelname)s;%(message)s", "%Y-%m-%d %H:%M:%S"
)


def validate_variable_type(var, allowed_instance_types):
    if not isinstance(var, allowed_instance_types):
        raise Exception(
            f"Variable '{var}' must be an instance of one of allowed_instance_types={allowed_instance_types}. Type witnessed: {type(var)}"
        )


def get_dataclass_as_dict(data_cls):
    return {field.name: getattr(data_cls, field.name) for field in fields(data_cls)}


def system_call(command_str, cwd=os.getcwd(), timeout_seconds=None, env_vars_dict=None):
    logger.debug(f"Running system call.\nCurrent working directory: {cwd}\n Command:\n{command_str}")
    return subprocess.run(
        command_str,
        cwd=cwd,
        shell=True,
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_seconds,
        env=env_vars_dict,
    )


def get_logger_for_script(log_file_path, debug=False):
    # get highest-level logger
    logger = logging.getLogger()

    #
    sh = logging.StreamHandler(sys.stdout)
    if debug:
        sh.setLevel(logging.DEBUG)
    else:
        sh.setLevel(logging.INFO)
    sh.setFormatter(logging_formatter)
    logger.addHandler(sh)

    #
    fh = logging.FileHandler(log_file_path)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging_formatter)
    logger.addHandler(fh)

    return logger


class Parameter(object):
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __bool__(self):
        if self.value:
            return True
        else:
            return False

    def __str__(self):
        return str(self.value)

    def __eq__(self, other):
        if type(other) == type(self):
            return self.value == other.value
        return False

    def __hash__(self):
        return hash((self.name, self.value))


class ParametersConfiguration:

    def __init__(self, config_file_path, schema_file_path):
        #
        File.validate_file_exists(config_file_path)
        self.config_file_path = config_file_path

        #
        self.schema_file_path = schema_file_path
        self.schema = yamale.make_schema(schema_file_path)

        #
        data = yamale.make_data(self.config_file_path)
        try:
            yamale.validate(self.schema, data)
            logger.debug('Config validation success!')
        except ValueError as e:
            logger.exception('Config validation failed!\n%s' % str(e))

        #
        param_dict, = pd.json_normalize(data[0][0]).to_dict('records')  # TODO: add validation
        self.param_dict = {key: Parameter(name=key, value=value) for key, value in param_dict.items()}

        #
        logger.debug(f"Parameters:\n{self.param_dict}")

    @staticmethod
    def write_config_file(save_path, src_file_path, overwrite=False):
        File.validate_path(src_file_path)
        if File.file_exists(save_path):
            if overwrite:
                logger.info(f"Overwriting existing config file: {save_path}")
            else:
                logger.info(f"A config file already exists: {save_path}")
        else:
            logger.info(f"Writing config file: {save_path}")
        with open(src_file_path, 'r') as infile:
            with open(save_path, "w") as outfile:
                yaml.dump(yaml.safe_load(infile), outfile)


class CleanExit(object):
    def __init__(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        if exc_type is not None:
            logger.info(f"Shutting down job due to exception: {exc_type}")
            logger.debug(traceback.format_tb(exc_tb))
            logger.debug(str(exc_value))
            return True
        return exc_type is None
