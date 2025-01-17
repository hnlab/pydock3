import os
import logging

from pydock3.blastermaster.util import ProgramFilePaths, BlasterStep
from pydock3.files import File


#
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class VDWScoringGridGenerationStep(BlasterStep):
    class MandatoryFileNames:
        CHEMGRID_PARAMETERS_FILE_NAME = (
            "INCHEM"  # hardwired, stupid. fix in chemgrid sometime
        )
        CHEMGRID_OUTPUT_FILE_NAME_PREFIX = "vdw"
        VDW_FILE = f"{CHEMGRID_OUTPUT_FILE_NAME_PREFIX}.vdw"
        VDW_BUMP_MAP_FILE = f"{CHEMGRID_OUTPUT_FILE_NAME_PREFIX}.bmp"

    GRID_SPACING = 0.2

    def __init__(
        self,
        working_dir,
        protein_table_infile,
        vdw_parameters_infile,
        box_infile,
        charged_receptor_infile,
        vdw_outfile,
        bump_map_outfile,
    ):
        super().__init__(
            working_dir=working_dir,
            infile_tuples=[
                (protein_table_infile, "protein_table_infile", None),
                (vdw_parameters_infile, "vdw_parameters_infile", None),
                (charged_receptor_infile, "charged_receptor_infile", None),
                (box_infile, "box_infile", None),
            ],
            outfile_tuples=[
                (vdw_outfile, "vdw_outfile", self.MandatoryFileNames.VDW_FILE),
                (bump_map_outfile, "bump_map_outfile", self.MandatoryFileNames.VDW_BUMP_MAP_FILE),
            ],
            parameter_tuples=[],
            program_file_path=ProgramFilePaths.CHEMGRID_PROGRAM_FILE_PATH,
        )

    @BlasterStep.handle_run_func
    def run(self):
        """run the vdw program chemgrid"""

        #
        # TODO validate infiles

        # first make chemgrid parameters file
        chemgrid_parameters_file = File(
            os.path.join(
                self.step_dir.path,
                self.MandatoryFileNames.CHEMGRID_PARAMETERS_FILE_NAME,
            )
        )

        #
        with open(chemgrid_parameters_file.path, "w") as f:
            f.write(f"{self.infiles.charged_receptor_infile.name}\n")
            f.write(f"{self.infiles.protein_table_infile.name}\n")
            f.write(f"{self.infiles.vdw_parameters_infile.name}\n")
            f.write(f"{self.infiles.box_infile.name}\n")
            f.write(f"{self.GRID_SPACING}\n")  # gridsize
            f.write("1\n")  # no idea
            f.write("4\n")  # no idea
            f.write("10\n")  # no idea
            f.write("2.3 2.6\n")  # i think this is bump distances
            f.write(
                f"{self.MandatoryFileNames.CHEMGRID_OUTPUT_FILE_NAME_PREFIX}\n"
            )  # output prefix

        #
        self.log_parameters_file(chemgrid_parameters_file)

        # run
        run_str = f"{self.program_file.path}"
        self.run_command(run_str)
