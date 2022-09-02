import collections
import logging
import os
import shutil
import pathlib
from datetime import datetime
import tarfile
import gzip
import re
import uuid

import numpy as np
import pandas as pd
from rdkit import Chem

from pydock3.util import validate_variable_type

from abc import ABC, abstractmethod
from collections.abc import Iterable

# aws prereq
import boto3

#
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


#
INDOCK_FILE_NAME = "INDOCK"

class FileSystemEntity(ABC):
    @abstractproperty
    def path(self) -> str:
        pass

    @abstractmethod
    def exists(self) -> bool:
        pass

    @abstractmethod
    def rm(self) -> None:
        pass

class FileBase(FileSystemEntity):
    def __init__(self, path):
        self._path = path

    @abstractmethod
    def open(self, mode) -> IOBase:
        pass

    # abstract copy method- used to transfer files between different platforms
    @staticmethod
    def copy(f1 : FileBase, f2: FileBase):
        with f1.open('rb') as fr, f2.open('wb') as fw:
            chunk = fr.read(65536)
            while chunk:
                fw.write(chunk)
                chunk = fr.read(65536)

class DirBase(FileSystemEntity):
    def __init__(self, path):
        self._path = path

    # "listall" in this context means to list *all* objects beneath the directory, not just one level below (as in os.path.listdir)
    @abstractmethod
    def listall(self) -> list[FileBase]:
        pass

    @abstractmethod
    def create(self) -> None:
        pass
    
class S3Path:
    def __init__(self, path):
        assert(path.startswith("s3://"))
        self.bucket = path.split('/')[2]
        self.object = '/'.join(path.split('/')[3:])
        self.path = path

    def __init__(self, bucket, key):
        self.bucket = bucket
        self.object = key
        self.path = '/'.join([bucket, key])

class S3IOWrapper(IOBase):
    def __init__(self, s3path : S3Path, session : boto3.Session , mode : str):

        assert(mode in ['r', 'rb', 'w', 'wb', 'a'])
        self.mode = mode
        self.s3path = s3path
        self.session = session

        if session:
            s3 = session.client('s3')
        else:
            s3 = boto3.client('s3')

        self.name = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        if mode in ['r', 'rb', 'a']:
            # something of an inelegant solution- if we are copying a file, we will need to write it twice (once to a tempfile, once to its actual destination)
            # this could be solved if we were able to get a file stream from s3, but this involves some extra complication (see "smart_open" python package)
            # if we ever expect to perform large file tranfsers with this utility, we should use smart_open
            s3.download_fileobj(s3path.bucket, s3path.object, self.name)
            self.fobj = open(self.name, mode)
        else:
            self.fobj = open(self.name, mode)

    # can't give specific type hints here as file can be in bytes or string mode
    def read(self, n : int, **kwargs) -> Iterable:
        return self.fobj.read(n, **kwargs)

    def write(self, b, **kwargs) -> int:
        return self.fobj.write(b, **kwargs)

    # perform all writing of data to s3 after local file is closed
    def close(self) -> None:
        self.fobj.close()
        self.closed = True
        if self.mode in ['w', 'wb', 'a']:
            if self.session:
                s3 = self.session.client('s3')
            else:
                s3 = boto3.client('s3')
            s3.upload_fileobj(self.name, self.s3path.bucket, self.s3path.object)

    def __iter__(self):
        return self.fobj.__iter__()
    
    def __next__(self):
        return self.fobj.__next__()

    def __exit__(self):
        self.close()

class S3File(FileBase):

    def __init__(self, path : str, properties=None, session=None):
        super().__init__(path)
        self.s3path = S3Path(path)
        self.session = session
        self.set_properties(properties)

    @property
    def path(self):
        return self._path

    def open(self, mode : str) -> S3IOWrapper:
        return S3IOWrapper(self.s3path, self.session, mode)

    def exists(self):
        if self.session:
            s3 = self.session.client('s3')
        else:
            s3 = boto3.client('s3')

        # lazy placeholder for now- not quite sure how to find the boto3 exception types
        try:
            response = s3.get_object_attributes(self.s3path.bucket, self.s3path.object)
        except:
            return False
        return True


class S3Dir(DirBase):

    def __init__(self, path, session=None):
        super().__init__(path)
        self.s3path = S3Path(path)
        self.session = session

    @property
    def path(self):
        return self._path

    # despite the fact that aws directories aren't really directories, we are still interested in listing objects starting with a given "directory" prefix
    def listall(self) -> list[S3File]:

        if self.session:
            s3 = self.session.client('s3')
        else:
            s3 = boto3.client('s3')
        
        response = s3.list_objects_v2(Bucket=self.s3path.bucket, Prefix=self.s3path.object)
        contents = [
            S3File(self.s3path.bucket + '/' + c['Key'], properties=c) for c in reponse['Contents']
        ]

        while reponse['IsTruncated']:
            conttoken = response['NextContinuationToken']
            response = s3.list_objects_v2(Bucket=self.s3path.bucket, Prefix=self.s3path.object, ContinuationToken=conttoken)

            new_contents = [
                S3File(self.s3path.bucket + '/' + c['Key'], properties=c) for c in response['Contents'])
            ]
            contents.extend(new_contents)

        return contents

    # directories aren't real in AWS, so we can ignore the "create()" command here
    def create(self) -> None:
        pass

class Dir(DirBase):
    """#TODO"""

    def __init__(self, path, create=False, reset=False):
        super().__init__(path=path)
        # set & validate path
        self.path = self._path

        if create:
            self.create(reset=reset)

    @property
    def path(self):
        return self._path

    ### btingle changes- abstract methods 
    def rm(self) -> None:
        shutil.rmtree(self.path)

    def listdir(self) -> list:
        return os.listdir(self.path)
    ###

    @property
    def name(self):
        return Dir.extract_dir_name_from_dir_path(self.path)

    @staticmethod
    def extract_dir_name_from_dir_path(dir_path):
        return os.path.basename(dir_path)

    @property
    def exists(self):
        return Dir.dir_exists(self.path)

    @property
    def validate_existence(self):
        if not self.exists:
            raise Exception(f"Dir {self.path} does not exist.")

    @staticmethod
    def dir_exists(dir_path):
        return os.path.isdir(dir_path)

    def create(self, reset=False):
        """#TODO"""
        if reset:
            if os.path.exists(self.path):
                shutil.rmtree(self.path)
                while os.path.isdir(self.path):
                    pass
                pathlib.Path(self.path).mkdir(parents=True)
                logger.info(f"Reset directory {self}.")
            else:
                pathlib.Path(self.path).mkdir(parents=True)
                logger.info(f"Created directory {self}.")
        else:
            if os.path.exists(self.path):
                logger.debug(
                    f"Tried to create directory {self} with reset=False but directory already exists."
                )
            else:
                pathlib.Path(self.path).mkdir(parents=True)
                logger.info(f"Created directory {self}")

    def delete(self):
        if os.path.exists(self.path):
            shutil.rmtree(self.path)
            while os.path.isdir(self.path):
                pass
            logger.info(f"Deleted directory {self}.")

    def copy_in_file(self, src_file_path, dst_file_name=None, overwrite=True):
        """#TODO"""
        File.validate_file_exists(src_file_path)

        if dst_file_name is None:
            dst_file_name = File.get_file_name_of_file(src_file_path)
        dst_file = File(path=os.path.join(self.path, dst_file_name))
        dst_file.copy_from(src_file_path=src_file_path, overwrite=overwrite)

        return dst_file

    @staticmethod
    def validate_obj_is_dir(obj):
        validate_variable_type(obj, allowed_instance_types=(Dir,))

    @path.setter
    def path(self, path):
        self.validate_path()
        self._path = os.path.abspath(path)

    @staticmethod
    def validate_path(file_path):
        validate_variable_type(file_path, allowed_instance_types=(str,))
        return file_path  # TODO: think more about this


class File(FileBase):
    """#TODO"""

    def __init__(self, path):
        super().__init__(path=path)

    @property
    def name(self):
        return File.get_file_name_of_file(self.path)

    @property
    def datetime_last_modified(self):
        return self.get_datetime_file_was_last_modified(self.path)

    @staticmethod
    def get_file_name_of_file(file_path):
        File.validate_path(file_path)
        return os.path.basename(os.path.abspath(file_path))

    @staticmethod
    def get_dir_path_of_file(file_path):
        File.validate_path(file_path)
        return os.path.dirname(os.path.abspath(file_path))

    @property
    def exists(self):
        return File.file_exists(self.path)

    ### btingle changes
    def rm(self) -> None:
        os.remove(self.path)

    def open(self, mode) -> IOBase:
        return open(self.path, mode)
    ### 

    @property
    def validate_existence(self):
        if not self.exists:
            raise Exception(f"File {self.path} does not exist.")

    @property
    def is_empty(self):
        return self.file_is_empty(self.path)

    def copy_from(self, src_file_path, overwrite=True):
        self.copy_file(src_file_path=src_file_path, dst_file_path=self.path, overwrite=overwrite)

    def delete(self):
        self.delete_file(self.path)

    def validate_is_not_empty(self):
        if self.is_empty:
            raise Exception(f"File is empty: {self}")

    def read_lines(self):
        return self.read_file_lines(self.path)

    @property
    def is_gzipped(self):
        return self.file_is_gzipped(self.path)

    @staticmethod
    def get_datetime_file_was_last_modified(file_path):
        File.validate_file_exists(file_path)

        datetime_last_modified = datetime.fromtimestamp(os.stat(file_path).st_mtime)
        logger.debug(f"File {file_path} was last modified at: {datetime_last_modified}")
        return datetime_last_modified

    @staticmethod
    def get_file_size(file_path):
        File.validate_file_exists(file_path)

        file_size = os.path.getsize(file_path)
        logger.debug(f"File {file_path} has file size: {file_size}")
        return file_size

    @staticmethod
    def file_is_empty(file_path):
        file_size = File.get_file_size(file_path)
        return file_size == 0

    @staticmethod
    def copy_file(src_file_path, dst_file_path, overwrite=True):
        """#TODO"""
        File.validate_file_exists(src_file_path)
        File.validate_path(dst_file_path)

        #
        if os.path.isfile(dst_file_path):
            if overwrite:
                os.remove(dst_file_path)
                shutil.copyfile(
                    src_file_path,
                    dst_file_path,
                )
                logger.debug(f"File {dst_file_path} overwritten by {src_file_path}.")
        else:
            logger.debug(f"File {src_file_path} copied to {dst_file_path}")
            shutil.copyfile(
                src_file_path,
                dst_file_path,
            )

    @staticmethod
    def delete_file(file_path):
        File.validate_path(file_path)
        if File.file_exists(file_path):
            os.remove(file_path)
            logger.debug(f"Deleted file {file_path}.")
        else:
            logger.debug(f"Tried to delete file {file_path} but it doesn't exist.")

    @staticmethod
    def files_differ(file_path_1, file_path_2, verbose=False):
        """#TODO"""
        File.validate_file_exists(file_path_1)
        File.validate_file_exists(file_path_2)

        with open(file_path_1, 'r') as f:
            a = set(f.readlines())
        with open(file_path_2, 'r') as f:
            b = set(f.readlines())

        diff = [f'-\t{x}' if x in a else f'+\t{x}' for x in list(a ^ b)]

        if verbose:
            diff_str = '\n'.join(diff)
            logger.debug(f"Diff between {file_path_1} and {file_path_2}:\n{diff_str}")

        return len(diff) != 0

    @staticmethod
    def file_exists(file_path):
        File.validate_path(file_path)
        return os.path.isfile(file_path)

    @staticmethod
    def read_file_lines(file_path):
        with open(file_path, 'r') as f:
            lines = [line.strip() for line in f.readlines()]
        return lines

    @staticmethod
    def file_is_gzipped(file_path):
        with open(file_path, 'rb') as f:
            return f.read(2) == b'\x1f\x8b'

    @staticmethod
    def validate_file_exists(file_path):
        if not File.file_exists(file_path):
            raise FileNotFoundError(f"File {file_path} does not exist.")

    @staticmethod
    def validate_file_is_not_empty(file_path):
        File.validate_file_exists(file_path)
        if File.file_is_empty(file_path):
            raise Exception(f"File {file_path} is empty.")

    


class SMIFile(File):
    def __init__(self, path):
        super().__init__(path=path)

    def read_dataframe(self):
        self.read_dataframe_from_smi_file(self.path)

    @staticmethod
    def read_dataframe_from_smi_file(smi_file_path):
        File.validate_file_exists(smi_file_path)

        #
        data = []
        with open(smi_file_path, 'r') as f:
            for line in f.readlines():
                line_elements = line.strip().split()
                if len(line_elements) != 2:
                    raise Exception(f"Line in .smi file does not contain expected number of columns (2): {line_elements}")
                smiles_string, zinc_id = line_elements
                SMIFile.validate_smiles_string(smiles_string)
                # TODO: validate zinc_id
                data.append({
                    'zinc_id': zinc_id,
                    'smiles': smiles_string,
                })
        df = pd.DataFrame.from_records(data)

        return df

    @staticmethod
    def validate_smiles_string(smiles_string):
        m = Chem.MolFromSmiles(smiles_string, sanitize=False)
        if m is None:
            raise Exception(f"Invalid SMILES: {smiles_string}")
        else:
            try:
                Chem.SanitizeMol(m)
            except:
                raise Exception(f"Invalid chemistry in SMILES: {smiles_string}")


class SDIFile(File):
    def __init__(self, path):
        super().__init__(path=path)

    def write_tgz(self, tgz_file_name, archive_dir_name=None, filter_regex="(.*?)"):
        if archive_dir_name is None:
            archive_dir_name = File.get_file_name_of_file(tgz_file_name)
            archive_dir_name = re.sub('.tgz$', '', archive_dir_name)
            archive_dir_name = re.sub('.tar.gz$', '', archive_dir_name)
        db2_file_paths = self.read_lines()
        pattern = re.compile(filter_regex)
        temp_dir_name = str(uuid.uuid4())
        os.mkdir(temp_dir_name)
        with tarfile.open(tgz_file_name, 'w:gz') as tar:
            i = 0
            for db2_file_path in db2_file_paths:
                if pattern.match(db2_file_path):
                    dst_file_name = f"{i+1}.db2"
                    dst_file_path = os.path.join(temp_dir_name, dst_file_name)
                    file_path_in_archive = os.path.join(archive_dir_name, dst_file_name)
                    if File.file_is_gzipped(db2_file_path):
                        with gzip.open(db2_file_path, 'rb') as f_in:
                            with open(dst_file_path, 'wb') as f_out:
                                shutil.copyfileobj(f_in, f_out)
                    else:
                        with open(db2_file_path, 'r') as f_in:
                            with open(dst_file_path, 'w') as f_out:
                                shutil.copyfileobj(f_in, f_out)
                    tar.add(dst_file_path, arcname=file_path_in_archive)
                    i += 1
        shutil.rmtree(temp_dir_name)


class ProgramFile(File):
    def __init__(self, path):
        super().__init__(path=path)


class LogFile(File):
    """#TODO"""

    def __init__(self, path):
        super().__init__(path=path)


class IndockFile(File):
    """
    The INDOCK file is the main parameters file for the DOCK program.

    `config_param_dict` corresponds to the key-values of blastermaster_config.yaml
    """

    def __init__(self, path):
        super().__init__(path=path)

    def write(
        self,
        dock_files,
        config_param_dict,
        dock_files_dir_name,
        flex_groups=None,
        flex_0_file=None,
        use_flex=False,
        flexible_penalty_m=None,
    ):
        """takes a bunch of config, writes an appropriate INDOCK file"""
        if flex_groups is None:
            flex_groups = []

        def get_yes_or_no(boolean):
            if boolean:
                return 'yes'
            else:
                return 'no'

        #
        File.validate_file_exists(dock_files.electrostatics_phi_size_file.path)
        with open(dock_files.electrostatics_phi_size_file.path, 'r') as f:
            try:
                phi_size = int(f.readline().strip())
            except Exception as e:
                raise Exception("Problem encountered while reading electrostatics phi size file. Check electrostatics phi size file.")

        # TODO: parametrize dock version
        header = f"""DOCK 3.8 parameter
#####################################################
# NOTE: split_database_index is reserved to specify a list of files
# defults for large scale docking.
ligand_atom_file               {config_param_dict['indock.ligand_atom_file']}
#####################################################
#                             OUTPUT
output_file_prefix            {config_param_dict['indock.output_file_prefix']}
#####################################################
#                             MATCHING
match_method                  {config_param_dict['indock.match_method']}
distance_tolerance            {config_param_dict['indock.distance_tolerance']}
match_goal                    {config_param_dict['indock.match_goal']}
distance_step                 {config_param_dict['indock.distance_step']}
distance_maximum              {config_param_dict['indock.distance_maximum']}
timeout                       {config_param_dict['indock.timeout']}
nodes_maximum                 {config_param_dict['indock.nodes_maximum']}
nodes_minimum                 {config_param_dict['indock.nodes_minimum']}
bump_maximum                  {config_param_dict['indock.bump_maximum']}
bump_rigid                    {config_param_dict['indock.bump_rigid']}
mol2_score_maximum            {config_param_dict['indock.mol2_score_maximum']}
#####################################################
#                             COLORING
chemical_matching             {get_yes_or_no(config_param_dict['indock.chemical_matching'])}
case_sensitive                {get_yes_or_no(config_param_dict['indock.case_sensitive'])}
#####################################################
#                             SEARCH MODE
atom_minimum                  {config_param_dict['indock.atom_minimum']}
atom_maximum                  {config_param_dict['indock.atom_maximum']}
number_save                   {config_param_dict['indock.number_save']}
number_write                  {config_param_dict['indock.number_write']}
flush_int                     {config_param_dict['indock.flush_int']}
#molecules_maximum            100000
check_clashes                 {get_yes_or_no(config_param_dict['indock.check_clashes'])}
do_premax                     {get_yes_or_no(config_param_dict['indock.do_premax'])}
do_clusters                   {get_yes_or_no(config_param_dict['indock.do_clusters'])}
#####################################################
#                             SCORING
ligand_desolvation            {config_param_dict['indock.ligand_desolvation']}
#vdw_maximum                   1.0e10
ligand_desolv_scale           {config_param_dict['indock.ligand_desolv_scale']}
electrostatic_scale           {config_param_dict['indock.electrostatic_scale']}
vdw_scale                     {config_param_dict['indock.vdw_scale']}
internal_scale                {config_param_dict['indock.internal_scale']}
per_atom_scores               {get_yes_or_no(config_param_dict['indock.per_atom_scores'])}
##################################################### 
#                             DOCKovalent 
dockovalent                   {get_yes_or_no(config_param_dict['indock.dockovalent'])}
bond_len                      {config_param_dict['indock.bond_len']}
bond_ang1                     {config_param_dict['indock.bond_ang1']}
bond_ang2                     {config_param_dict['indock.bond_ang2']}
len_range                     {config_param_dict['indock.len_range']}
len_step                      {config_param_dict['indock.len_step']}
ang1_range                    {config_param_dict['indock.ang1_range']}
ang2_range                    {config_param_dict['indock.ang2_range']}
ang1_step                     {config_param_dict['indock.ang1_step']}
ang2_step                     {config_param_dict['indock.ang2_step']}
#####################################################
#                    MINIMIZATION
minimize                      {get_yes_or_no(config_param_dict['indock.minimize'])}
sim_itmax                     {config_param_dict['indock.sim_itmax']}
sim_trnstep                   {config_param_dict['indock.sim_trnstep']}
sim_rotstep                   {config_param_dict['indock.sim_rotstep']}
sim_need_to_restart           {config_param_dict['indock.sim_need_to_restart']}
sim_cnvrge                    {config_param_dict['indock.sim_cnvrge']}
min_cut                       {config_param_dict['indock.min_cut']}
iseed                         {config_param_dict['indock.iseed']}
##################################################### 
##                 Monte Carlo OPTIMIZATION
#monte_carlo                   no 
#mc_itmax                      500
#mc_accpt                      250
#mc_temp                       298.15
#mc_trnstep                    0.2
#mc_rotstep                    5.0
#mc_iseed                      777
#####################################################
# INPUT FILES / THINGS THAT CHANGE
"""

        #
        with open(self.path, "w") as f:
            f.write(header)
            f.write(
                f"receptor_sphere_file          {os.path.join('..', dock_files_dir_name, dock_files.matching_spheres_file.name)}\n"
            )
            f.write(
                f"vdw_parameter_file            {os.path.join('..', dock_files_dir_name, dock_files.vdw_parameters_file.name)}\n"
            )
            f.write(f"delphi_nsize                  {phi_size}\n")
            if not use_flex:  # normal docking, no flexible sidechains
                f.write(f"flexible_receptor             {get_yes_or_no(config_param_dict['indock.flexible_receptor'])}\n")
                f.write(f"total_receptors               {config_param_dict['indock.total_receptors']}\n")
                f.write("############## grids/data for one receptor\n")
                f.write(f"rec_number                    {config_param_dict['indock.rec_number']}\n")
                f.write(f"rec_group                     {config_param_dict['indock.rec_group']}\n")
                f.write(f"rec_group_option              {config_param_dict['indock.rec_group_option']}\n")
                f.write(
                    f"solvmap_file                  {os.path.join('..', dock_files_dir_name, dock_files.ligand_desolvation_heavy_file.name)}\n"
                )
                f.write(
                    f"hydrogen_solvmap_file         {os.path.join('..', dock_files_dir_name, dock_files.ligand_desolvation_hydrogen_file.name)}\n"
                )
                f.write(
                    f"delphi_file                   {os.path.join('..', dock_files_dir_name, dock_files.electrostatics_trim_phi_file.name)}\n"
                )
                f.write(f"chemgrid_file                 {os.path.join('..', dock_files_dir_name, dock_files.vdw_file.name)}\n")
                f.write(
                    f"bumpmap_file                  {os.path.join('..', dock_files_dir_name, dock_files.vdw_bump_map_file.name)}\n"
                )
                f.write("#####################################################\n")
                f.write("#                             STRAIN\n")
                f.write(f"check_strain                  {get_yes_or_no(config_param_dict['indock.check_strain'])}\n")
                f.write(f"total_strain                  {config_param_dict['indock.total_strain']}\n")
                f.write(f"max_strain                    {config_param_dict['indock.max_strain']}\n")
                f.write("############## end of INDOCK\n")
            else:  # flexible docking
                raise NotImplementedError
                # TODO
                """
                # flex_groups contains relevant data
                total_groups = [len(sub_group) for sub_group in flex_groups]
                f.write("flexible_receptor             yes\n")
                f.write("score_each_flex               yes\n")
                f.write(f"total_receptors               {str(total_groups)}\n")
                for i, sub_group in enumerate(flex_groups):
                    for j, one_rec in enumerate(sub_group):
                        energy = util.occupancy_to_energy(one_rec[1], flexible_penalty_m)
                        f.write("############## grids/data for one receptor\n")
                        f.write(f"## residues: {str(one_rec[2])}{one_rec[3]}\n")
                        f.write(f"## occupancy: {str(one_rec[1])}\n")
                        f.write(
                            f"## energy: {str(util.occupancy_to_energy(one_rec[1], 1.0))}\n"
                        )
                        f.write(f"## multiplier: {str(flexible_penalty_m)}\n")
                        f.write(f"## penalty: {str(energy)}\n")
                        f.write(f"rec_number                    {str(one_rec[0])}\n")
                        f.write(f"rec_group                     {str(i + 1)}\n")
                        f.write(f"rec_group_option              {str(j + 1)}\n")
                        f.write(f"rec_energy                    {str(energy)}\n")
                        f.write(
                            f"solvmap_file                  {os.path.join(output_dir.path, str(one_rec[0]), ligand_desolvation_pdb_outfile.path + ligand_desolvation_heavy_name)}\n"
                        )
                        f.write(
                            f"hydrogen_solvmap_file         {os.path.join(output_dir.path, str(one_rec[0]), ligand_desolvation_pdb_outfile.path + ligand_desolvation_hydrogen_name)}\n"
                        )
                        if (flex_0_file is None) or (
                            (str(one_rec[0]), "electrostatics")
                            not in flex_0_file  # TODO: this will cause an error since flex_0_file is potentially None
                        ):
                            f.write(
                                f"delphi_file                   {os.path.join(output_dir.path, str(one_rec[0]), dock_files.electrostatics_trim_phi_file.path)}\n"
                            )
                        else:  # means we are using implicitly 0 grid here, just write 0
                            f.write("delphi_file                   0\n")
                        f.write(
                            f"chemgrid_file                 {os.path.join(output_dir.path, str(one_rec[0]), vdw_prefix + '.vdw')}\n"
                        )
                        f.write(
                            f"bumpmap_file                  {os.path.join(output_dir.path, str(one_rec[0]), vdw_prefix + '.bmp')}\n"
                        )
                f.write("############## end of INDOCK\n")
                """


class OutdockFile(File):

    COLUMN_NAMES = [
        "mol#",
        "id_num",
        "flexiblecode",
        "matched",
        "nscored",
        "time",
        "hac",
        "setnum",
        "matnum",
        "rank",
        "charge",
        "elect",
        "gist",
        "vdW",
        "psol",
        "asol",
        "tStrain",
        "mStrain",
        "rec_d",
        "r_hyd",
        "Total",
    ]

    def __init__(self, path):
        super().__init__(path=path)

    def get_dataframe(self):
        File.validate_file_exists(self.path)
        with open(self.path, 'r', errors='ignore') as f:
            #
            lines = [x.strip() for x in f.readlines()]

            # find first ligand line ("Input ligand: [...]")
            first_lig_line_index = None
            for i, line in enumerate(lines):
                if line.strip().startswith("Input ligand"):
                    first_lig_line_index = i
                    break

            #
            header_line_index = None
            for i, line in enumerate(lines):
                if all([column_name in line for column_name in self.COLUMN_NAMES]):
                    header_line_index = i
                    break
            if header_line_index is None:
                raise Exception(f"Header line not found when reading OutdockFile: {self.path}")

            #
            lines = [lines[first_lig_line_index]] + lines[header_line_index+1:]

            #
            open_file_line_indices = [i for i, line in enumerate(lines) if line.startswith("open the file:") or line.startswith("Input ligand:")]

            #
            close_file_line_indices = []
            new_open_file_line_indices = []
            for i in open_file_line_indices:
                open_file_line = lines[i]
                db2_file_path = open_file_line.replace("open the file:", "").replace("Input ligand:", "").strip()
                close_file_line_index = None
                for j, line in enumerate(lines[i:]):
                    if line.startswith("close the file:"):
                        close_file_line_index = i + j
                        if line.replace("close the file:", "").strip() != db2_file_path:
                            raise Exception(f"Open file line {i+1} and close file line {close_file_line_index+1} do not match in OutdockFile: {self.path}")
                        break
                if close_file_line_index is None:
                    raise Exception(f"Corresponding close file line not found for open file line {i+1} in OutdockFile {self.path} : {open_file_line}")
                new_open_file_line_indices.append(i)
                close_file_line_indices.append(close_file_line_index)
            open_file_line_indices = new_open_file_line_indices

            #
            if len(open_file_line_indices) != len(close_file_line_indices):
                raise Exception(f"# of open file lines and # of close file lines do not match in OutdockFile: {self.path}")

            #
            db2_file_paths = []
            data = []
            df_column_names = ["db2_file_path"] + self.COLUMN_NAMES
            for open_file_line_index, close_file_line_index in zip(open_file_line_indices, close_file_line_indices):
                db2_file_path = lines[open_file_line_index].replace("open the file:", "").replace("Input ligand:", "").strip()
                db2_file_paths.append(db2_file_path)
                for data_row_line_index in range(open_file_line_index + 1, close_file_line_index):
                    data_row_line = lines[data_row_line_index]
                    data_row = data_row_line.strip().split()
                    if data_row[0].isdigit():
                        data_row = [db2_file_path] + data_row
                    else:
                        data_row = [db2_file_path] + [np.nan for _ in range(len(self.COLUMN_NAMES))]

                    # pad missing columns with NaN
                    if len(data_row) != len(df_column_names):
                        num_missing = len(df_column_names) - len(data_row)
                        data_row += [np.nan for _ in range(num_missing)]

                    #
                    data_row_dict = {column_name: data_row[i] for i, column_name in enumerate(df_column_names)}
                    data.append(data_row_dict)

            return pd.DataFrame.from_records(data)


class Mol2File(File):
    MOLECULE_HEADER = "@<TRIPOS>MOLECULE"
    ATOM_HEADER = "@<TRIPOS>ATOM"
    BOND_HEADER = "@<TRIPOS>BOND"

    def __init__(self, path):
        super().__init__(path=path)

    def read_mols(self, sanitize=True):
        mols = [Chem.MolFromMol2Block(mol2_block_str, sanitize=sanitize) for mol2_block_str in self.read_mol2_block_strings()]

        return mols

    def read_mol2_blocks(self):
        mol2_block_strings = self.read_mol2_block_strings()

        mol2_blocks = []
        for mol2_block_str in mol2_block_strings:
            molecule_section_str, remaining_str = mol2_block_str.replace(self.MOLECULE_HEADER, '').split(self.ATOM_HEADER)
            atom_section_str, bond_section_str = remaining_str.split(self.BOND_HEADER)

            molecule_section = [line.split() for line in molecule_section_str.split('\n') if line]
            atom_section = [line.split() for line in atom_section_str.split('\n') if line]
            bond_section = [line.split() for line in bond_section_str.split('\n') if line]

            mol2_blocks.append((molecule_section, atom_section, bond_section))

        return mol2_blocks

    def read_mol2_block_strings(self):
        with open(self.path, 'r') as f:
            lines = [line for line in f.readlines() if not line.startswith("#")]

        mol2_block_strings = [self.MOLECULE_HEADER + block_str for block_str in '\n'.join(lines).split(self.MOLECULE_HEADER)[1:]]

        return mol2_block_strings

    def write_mol2_file_with_molecules_cloned_and_transformed(self, rotation_matrix, translation_vector, write_path, num_applications=1, bidirectional=False):

        #
        def transform(xyz, rot_mat, transl_vec):
            return np.dot(rot_mat, xyz) + transl_vec

        def get_inverse_transform(rot_mat, transl_vec):
            a = np.array([[1., 0., 0., 0.]])
            for i in range(3):
                a = np.concatenate((a, np.array([np.concatenate((np.array([transl_vec[i]]), rot_mat[i, :]))])), axis=0)
            a_inv = np.linalg.inv(a)
            rot_mat_inv = a_inv[1:, 1:]
            transl_vec_inv = a_inv[1:, 0]

            return rot_mat_inv, transl_vec_inv

        #
        def get_section_text_block(rows, alignment='right', num_spaces_before_line=5, num_spaces_between_columns=2):
            return get_text_block(rows, alignment=alignment, num_spaces_before_line=num_spaces_before_line, num_spaces_between_columns=num_spaces_between_columns)

        #
        mol2_blocks = self.read_mol2_blocks()

        #
        if bidirectional:
            rotation_matrix_inv, translation_vector_inv = get_inverse_transform(rotation_matrix, translation_vector)

        #
        with open(write_path, 'w') as f:

            for molecule_section, atom_section, bond_section in mol2_blocks:
                #
                new_molecule_section = []
                new_molecule_section.append(molecule_section[0])
                molecule_row = molecule_section[1]
                if bidirectional:
                    multiplier = (2 * num_applications) + 1
                else:
                    multiplier = num_applications + 1
                new_molecule_row = [int(molecule_row[0]) * multiplier, int(molecule_row[1]) * multiplier] + molecule_row[2:]
                new_molecule_section.append(new_molecule_row)

                #
                atom_element_to_id_nums_dict = collections.defaultdict(list)
                atom_names = [atom_row[1] for atom_row in atom_section]
                for atom_name in atom_names:
                    element, id_num = [token for token in re.split(r'(\d+)', atom_name) if token]
                    atom_element_to_id_nums_dict[element].append(int(id_num))

                #
                num_atoms = len(atom_section)
                new_atom_section = []
                for atom_row in atom_section:
                    new_atom_section.append(atom_row)

                def apply_to_atoms(rot_mat, transl_vec, n, num_app):
                    for atom_row in atom_section:
                        atom_id = atom_row[0]
                        new_atom_id = f"{int(atom_id) + (n * num_atoms)}"
                        atom_name = atom_row[1]
                        element, id_num = [token for token in re.split(r'(\d+)', atom_name) if token]
                        new_atom_name = f"{element}{int(id_num) + (n * max(atom_element_to_id_nums_dict[element]))}"
                        current_xyz = np.array([float(coord) for coord in atom_row[2:5]])
                        for j in range(num_app):
                            new_xyz = transform(current_xyz, rot_mat, transl_vec)
                            current_xyz = new_xyz
                        new_atom_row = [new_atom_id, new_atom_name] + list(new_xyz) + atom_row[5:]
                        new_atom_section.append(new_atom_row)

                #
                for i, n in enumerate(list(range(1, num_applications+1))):
                    apply_to_atoms(rotation_matrix, translation_vector, n, num_app=i+1)

                #
                if bidirectional:
                    for i, n in enumerate(list(range(num_applications+1, (2*num_applications)+1))):
                        apply_to_atoms(rotation_matrix_inv, translation_vector_inv, n, num_app=i+1)

                #
                num_bonds = len(bond_section)
                new_bond_section = []
                for bond_row in bond_section:
                    new_bond_section.append(bond_row)

                def apply_to_bonds(n):
                    for bond_row in bond_section:
                        new_bond_row = [int(bond_row[1]) + (n * num_bonds)] + [int(num) + (n * num_atoms) for num in bond_row[1:3]] + bond_row[3:]
                        new_bond_section.append(new_bond_row)

                #
                for n in range(1, num_applications+1):
                    apply_to_bonds(n)

                #
                if bidirectional:
                    for n in range(num_applications+1, (2*num_applications)+1):
                        apply_to_bonds(n)

                #
                f.write(f"{self.MOLECULE_HEADER}\n{get_section_text_block(new_molecule_section)}\n")
                f.write(f"{self.ATOM_HEADER}\n{get_section_text_block(new_atom_section)}\n")
                f.write(f"{self.BOND_HEADER}\n{get_section_text_block(new_bond_section)}\n")


def get_text_block(rows, alignment='left', num_spaces_between_columns=1, num_spaces_before_line=0):
    rows = [[str(token) for token in row] for row in rows]

    max_row_size = max([len(row) for row in rows])
    columns = [[row[i] if i < len(row) else "" for row in rows] for i in range(max_row_size)]
    column_max_token_length_list = [max([len(token) for token in column]) for column in columns]
    spacing_between_columns = " " * num_spaces_between_columns
    formatted_lines = []
    for row in rows:
        formatted_tokens = []
        for i, token in enumerate(row):
            if alignment == 'left':
                formatted_token = token.ljust(column_max_token_length_list[i])
            elif alignment == 'right':
                formatted_token = token.rjust(column_max_token_length_list[i])
            else:
                formatted_token = token
            formatted_tokens.append(formatted_token)
        spacing_before_line = num_spaces_before_line * " "
        formatted_line = spacing_before_line + spacing_between_columns.join(formatted_tokens)
        formatted_lines.append(formatted_line)
    text_block = "\n".join(formatted_lines)

    return text_block
