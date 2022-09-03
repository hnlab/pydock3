#!/usr/bin/env python

# Ryan G. Coleman, Brian K. Shoichet Lab

import logging

from pydock3.blastermaster.util import ProgramFilePaths, BlasterStep
from pydock3.files import ProgramFile, File


#
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class MolecularSurfaceGenerationStep(BlasterStep):

    DENSITY = 1.0

    class MandatoryFileNames:
        RADII_FILE_NAME = "radii"

    def __init__(
        self,
        step_dir,
        charged_receptor_infile,
        binding_site_residues_infile,
        radii_infile,
        molecular_surface_outfile,
    ):
        super().__init__(step_dir=step_dir)

        #
        self.program_file = ProgramFile(path=ProgramFilePaths.DMS_PROGRAM_FILE_PATH)

        #
        self.process_infiles(
            (charged_receptor_infile, "charged_receptor_infile"),
            (binding_site_residues_infile, "binding_site_residues_infile"),
            (radii_infile, "radii_infile"),  # dms reads the elements and radii from a file in the current directory called 'radii'.
            new_file_names_tuple=(charged_receptor_infile.name, binding_site_residues_infile.name, self.MandatoryFileNames.RADII_FILE_NAME),
        )

        #
        self.process_outfiles(
            (molecular_surface_outfile, "molecular_surface_outfile"),
        )

        #
        self.process_parameters()

    @BlasterStep.handle_run_func
    def run(self):
        """run the dms program to produce molecular surface points
        https://www.cgl.ucsf.edu/chimera/docs/UsersGuide/midas/dms1.html
        """
        # if you have waters, DMS crashes. so, just take them out of any file DMS
        # reads. this should allow statically placed waters to work.
        # thanks to joel karpiak for finding these errors!

        # removing waters from receptors
        charged_receptor_no_waters_file = File(
            path=f"{self.infiles.charged_receptor_infile.path}.dms"
        )
        run_str = f"grep -a -v HOH {self.infiles.charged_receptor_infile.name} > {charged_receptor_no_waters_file.name}"
        self.run_command(run_str)

        # removing waters from binding site
        binding_site_residues_no_waters_file = File(
            path=f"{self.infiles.binding_site_residues_infile.path}.dms"
        )
        run_str = f"grep -a -v HOH {self.infiles.binding_site_residues_infile.name} > {binding_site_residues_no_waters_file.name}"
        self.run_command(run_str)

        #
        run_str = f"{self.program_file.path} {charged_receptor_no_waters_file.name} -a -d {self.DENSITY} -i {binding_site_residues_no_waters_file.name} -g {self.log_file.name} -p -n -o {self.outfiles.molecular_surface_outfile.name}"
        self.run_command(run_str)