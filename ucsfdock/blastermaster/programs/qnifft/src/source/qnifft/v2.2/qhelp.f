	subroutine usage()

	print *,' '
	print *,'USAGE: '
	print *,'To run                       : qnifft parameter_file_name'
	print *,'for help                     : qnifft help'
	print *,'to list all valid parameters : qnifft all'
	print *,'for help on a parameter      : qnifft parameter_keyword'
	print *,' '
	stop
	end

	subroutine help()
	print *,'qnifft requires EITHER:'
	print *,'A minimum of 4 files: '
	print *,'	a pdb file (*.pdb),'
	print *,'	a radius file (*.siz), a charge file (*.crg) and a '
	print *,'	parameter file.  '
	print *,'                    OR:'
	print *,'	a pdb file with radii and charges in B-factor, occupancy fields (*.atm),'
	print *,'	a parameter file, with the option: input_atm_file=t'
	print *,'For formats of these files see examples.'
	print *,'Depending on the options set in the'
	print *,'parameter file an input potential map (*.phi) generated'
	print *,'from a previous run, & second *.crg, *.pdb files (for specifying'
	print *,'charges, coords for potential and field readout), may be required'
	print *,'The program tries to read a default'
	print *,'parameter file named delphi.def in the directory pointed'
	print *,'to by the environment variable DELDIR. It then tries to'
	print *,'read the parameter file named in the command line'
	print *,'from the current directory. At least one of these must'
	print *,'exist.  If both exist, parameters specified in the named'
	print *,'file will override those set in the default file.'
	print *,'Both parameter files have the'
	print *,'same format, as described in delphi.def. '
	stop
	end

	subroutine parlis()
	character*1 aopt

	print *,'Alphabetical list of Delphi parameters with valid values. '
	print *,'------------------------------------------------------------'
	print *,'Keywords are case insensitive. * indicates characters to'
	print *,'the right which may be omitted: when abbreviating do not include'
	print *,'the asterisk. '
	print *,'Most keyword can be abbreviated to the 1st 4 letters.'
	print *,'Filename strings are case sensitive'
	print *,'The syntax of a valid keyword assignment phrase is:'
	print *,' '
	print *,'keyword=value'
	print *,' '
	print *,'with no embedded blanks or commas. Phrases are delimited by '
	print *,'one or more spaces, commas or an end of line'
	print *,' '
	print *,'Valid values are indicated by'
	print *,'real =  any real number'
	print *,'+real =  positive real number'
	print *,'int =  integer'
	print *,'+int =  positive integer'
	print *,'t/f  = true/false for logical variable'
	print *,'string =  any ascii string without embedded space or commas'
	print *,'specific alternatives are separated by /'
	print *,' '
c	print *,'type return to continue'
c	read(5,'(a)')aopt
	print *,' '
	print *,'NAME				VALUE'
	print *,'------------------------------------------------------------'
	print *,'anal*lyse_map			t/f'
	print *,'ani_div*alent			real'
	print *,'ani_mon*ovalent		real'
	print *,'atom*_file_output		t/f'
	print *,'bord*er_solvent		real'
	print *,'boun*dary_condition		coul/focus/zero/dipol/field'
	print *,'cat_div*alent			real'
	print *,'cat_mon*ovalent		real'
	print *,'char*ge_file			string'
	print *,'chec*k_frequency		+int'
	print *,'conc*entration_output		t/f'
	print *,'conv*ergence			+real'
	print *,'diel*ectric_map_file		string'
	print *,'fast*_dielectric_map       t/f'
	print *,'fill*				+real'
	print *,'field*_boundary		+real'
	print *,'forc*e_calculation         t/f'
	print *,'grid*size			+int (odd, multiple of 16 + 1 from 17 to '
	print *,'     maximum compiled grid size given by ngrid in qdiffpar.h'
	print *,'inpu*t_atm_file  		t/f         '
	print *,'insi*ght_format		t/f         '
	print *,'ioni*c_radius			+real'
c	print *,' '
c	print *,'type return to continue'
c	read(5,'(a)')aopt
c	print *,' '
	print *,'isalt*_conc    		+real'
	print *,'imemb*rane_position		real'
	print *,'leng*th_smooth			+real'     
	print *,'level0*_multi_grid_it		+int'
	print *,'level1*_multi_grid_it		+int'
	print *,'level2*_multi_grid_it		+int'
	print *,'level3*_multi_grid_it		+int'
	print *,'newt*on_iterations		+int'
	print *,'nonl*inear_equation		t/f'
	print *,'osalt*_conc    		+real'
	print *,'omemb*rane_position		real'
	print *,'pdb_in*put_file		string'
	print *,'pdb2_in*put_file		string'
	print *,'pdb_out*put_file		string'
	print *,'phi_in*put_file		string'
	print *,'phi_out*put_file		string'
	print *,'prob*e_radius			+real'
	print *,'radi*us_file			string'
	print *,'rela*xation_parameter		+real (between 0.5 and 2.)'
	print *,'salt*_concentration		+real  NOTE- now obsolete- use cat_mon etc to specify ion concs'
	print *,'scal*e				+real'
	print *,'site_ch*arge_file		string'
	print *,'site_in*put_file		string'
	print *,'site_out*put_file		string'
	print *,'site_pot*entials		t/f'
c	print *,' '
c	print *,'type return to continue'
c	read(5,'(a)')aopt
c	print *,' '
	print *,'sizi*ng			scale/fill/border'
	print *,'smoo*th_dielectric		0/1/2'
	print *,'solu*te_dielectric		+real'
	print *,'solv*ent_dielectric		+real'
	print *,'sphe*rical_charge_dist		t/f'
	print *,'temp*erature			+real'
	print *,'titl*e				string'
	print *,'xcen*ter			+real'
	print *,'xper*iodic			t/f'
	print *,'ycen*ter			+real'
	print *,'yper*iodic			t/f'
	print *,'zcen*ter			+real'
	print *,'zper*iodic			t/f'
	print *,' '
	stop
	end

	subroutine parhlp(line)
	character*80 line
	logical ifound
c-----------------------------------------------------------
	ifound = .false.
	if(line(1:4).eq.'ANAL')then
	 print *,' '
	 print *,'Keyword     : anal*yse_map'
	 print *,'valid values: t/f'
	 print *,'flag for whether a program analyses potential map'
	 print *,'calculating integrated energy density integrals'
	 print *,'reaction field energies etc'
	 ifound = .true.
      end if
	if((line(1:4).eq.'ANI_').or.(line(1:4).eq.'CAT_'))then
	 print *,' '
	 print *,'Keywords     : ani_mon*ovalent, cat_mon*ovalent, ani_div*alent, cat_div*alent'
	 print *,'valid values: real >0'
	 print *,'concentration (M) of -,+,-- and ++ salt ions'
	 print *,'supersede the salt_concentration variable, which is overridden'
	 ifound = .true.
      end if
	if(line(1:4).eq.'ATOM')then
	 print *,' '
	 print *,'Keyword     : atom_file_output'
	 print *,'valid values: t/f'
	 print *,'flag for whether a pdb format output file is written'
	 print *,'with the assigned radius and charge'
	 print *,'written in the occupancy & B-factor fields'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'BORD')then
	 print *,' '
	 print *,'Keyword     : bord*er_solvent'
	 print *,'valid values: any real number'
	 print *,'Applicable when the sizing=border'
	 print *,'option is used, otherwise is ignored.'
	 print *,'The molecule(s) are scaled so that'
	 print *,'the geometric center is at the grid center, and the'
	 print *,'minimum distance of any part of the molecule to the'
	 print *,'the edge of the grid is this value in Angstroms' 
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'BOUN')then
	 print *,' '
	 print *,'Keyword     : boundary_condition'
	 print *,'valid values: coul/zero/focus/dipolar/field'
	 print *,'Boundary condition that is used to assign potentials'
	 print *,'on the grid boundary: coulombic uses sum of Debye'
	 print *,'like potentials phi = sum(q.exp(-r/l)/eps.r where'
	 print *,'r is distance, eps is solvent dielectric, l is debye'
	 print *,'length, where sum is over charges assigned to the '
	 print *,'molecule. Dipolar is like coulombic except the '
	 print *,'average positions of the + and - chagrges are used'
	 print *,'Focussing interpolates potentials from a previous'
	 print *,'map, which must completely enclose current grid'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'CHAR')then
	 print *,' '
	 print *,'Keyword     : char*ge_file'
	 print *,'valid values: name of charge assignment file which '
	 print *,'contains a list of rules used to assign charges to'
	 print *,'the atoms- see example file for format. Usually'
	 print *,'named like *.crg. '
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'CHEC')then
	 print *,' '
	 print *,'Keyword     : check_frequency'
	 print *,'valid values: positive integer > 0'
	 print *,'a fairly esoteric parameter that controls how frequently'
	 print *,'the program checks for convergence in the potential'
	 print *,'correction iterations.  Usually this should be left'
	 print *,'at the default value of 2.  Changing this to 1'
	 print *,'will have the effect of switching off multigridding, '
	 print *,'whatever the number of multigridding iterations'
	 ifound = .true.
      end if
	if(line(1:4).eq.'CONC')then
	 print *,' '
	 print *,'Keyword     : conc*entration_output'
	 print *,'valid values: t/f'
	 print *,'Flag which controls the form of output. False will'
	 print *,'result in a potential map, true will result in a'
	 print *,'mobile ion charge density map output (M/L). ignored'
	 print *,'when the salt concentration is zero'
	 print *,'only applies if the salt concentration is non-zero'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'CONV')then
	 print *,' '
	 print *,'Keyword     : conv*ergence'
	 print *,'valid values: positive real number'
	 print *,'this is the value of the normal of the residual'
	 print *,'potential, in kT/e used to judge when the solution to the PB'
	 print *,'equation has converged.  Usually: 0.001 is sufficient'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'DIEL')then
	 print *,' '
	 print *,'Keyword     : diel*ectric_map_file'
	 print *,'valid values: name for dielectric map file output,'
	 print *,'usually *.eps'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'FORC')then
	 print *,' '
	 print *,'Keyword     : forc*e_calculation  '
	 print *,'valid values: t/f'
	 print *,'true: calculate rxn field forces'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'FAST')then
	 print *,' '
	 print *,'Keyword     : fast*_dielectric_map'
	 print *,'valid values: t/f'
	 print *,'false: use new, more accurate surfacing algorithm'
	 print *,'for the dielectric map- uses more time, but is almost grid '
	 print *,'scale independent, and the surface induced charge positions'
	 print *,'are corrected, so reaction field energies are more accurate'
	 print *,'true = use old inkblot method for generating'
	 print *,'the dielectric map- fast, but not so accurate at coarser scales'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'FILL')then
	 print *,' '
	 print *,'Keyword     : fill*'
	 print *,'valid values: positive real number'
	 print *,'applicable when the sizing=fill option is used, '
	 print *,'otherwise ignored.  The molecule is scaled so that'
	 print *,'its geometric center is at the grid center, and its'
	 print *,'longest x/y/z dimension is this value in % of the grid size'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'FIEL')then
	 print *,' '
	 print *,'Keyword     : field*_boundary'
	 print *,'valid values: real number'
	 print *,'applicable when the boundary=ext.field (5) option is used, '
	 print *,'otherwise ignored.   A field of "field" kT/A is applied'
	 print *,'along the Z direction of the grid'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'GRID')then
	 print *,' '
	 print *,'Keyword     : grid*size'
	 print *,'valid values: positive odd integer in range 17-ngrid'
	 print *,'This is the lattice dimension-it must be an odd number.'
	 print *,'The maximum grid dimension is set at compile time thru the '
	 print *,'parameter ngrid in the include file. This value is printed out'
	 print *,'above the date at run time'
	 print *,'For multgridding, gridsize-1 must be a multiple of 4,8, or 16'
	 print *,'depending on whether 1, 2, or 3 sublevels of multigridding'
	 print *,'are required'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'INPU')then
	 print *,' '
	 print *,'Keyword     : inpu*t_atm_format'
	 print *,'valid values: t/f'
	 print *,'set to true a pdb file in atm format (usually named *.atm)'
	 print *,'with radii and charges written in the occupancy and B_factor'
	 print *,'fields is read instead of the input and site'
	 print *,'pdb/siz/crg files'
	 print *,'and used to assign coords, radii and atoms'
	 print *,'radius is in columns 55-60, in format f6.2'
	 print *,'charge is in columns 62-67, in format f7.3'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'INSI')then
	 print *,' '
	 print *,'Keyword     : insi*ght_format'
	 print *,'valid values: t/f'
	 print *,'set to true the output is written in Biosyms INSIGHT'
	 print *,'readable format, otherwise it is written in DelPhi'
	 print *,'format'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'IONI')then
	 print *,' '
	 print *,'Keyword     : ioni*c_radius'
	 print *,'valid values: positive real number'
	 print *,'size of ion exclusion layer around molecule in angstroms'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:6).eq.'LEVEL0')then
	 print *,' '
	 print *,'Keyword     : level0*_multigrid_it'
	 print *,'valid values: positive integer > 0'
	 print *,'number of iterations at 0th level of multigridding'
	 print *,'used to refine estimate of correction in potential'
	 print *,'Along with the relaxation_parameter, the '
	 print *,'number and depth of multigridding iterations are the'
	 print *,'main parameters one should play with to improve'
	 print *,'the convergence rate'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:6).eq.'LEVEL1')then
	 print *,' '
	 print *,'Keyword     : level1*_multigrid_it'
	 print *,'valid values: positive integer'
	 print *,'number of iterations at 1st level of multigridding'
	 print *,'used to refine estimate of correction in potential'
	 print *,'if zero there is no multigridding'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:6).eq.'LEVEL2')then
	 print *,' '
	 print *,'Keyword     : level2*_multigrid_it'
	 print *,'valid values: positive integer'
	 print *,'number of iterations at 2nd level of multigridding'
	 print *,'used to refine estimate of correction in potential'
	 print *,'if zero there is only 2 layer multigridding'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:6).eq.'LEVEL3')then
	 print *,' '
	 print *,'Keyword     : level3*_multigrid_it'
	 print *,'valid values: positive integer'
	 print *,'number of iterations at 3rd level of multigridding'
	 print *,'used to refine estimate of correction in potential'
	 print *,'if zero there is only 3 layer multigridding'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'NEWT')then
	 print *,' '
	 print *,'Keyword     : newt*on_iterations'
	 print *,'valid values: positive integer'
	 print *,'number of iterations at outer, newton level '
	 print *,'used to refine potential. Each iteration will'
	 print *,'perform level0 etc. iterations. Generally'
	 print *,'convergence should be reach in less than 10 iterations'
	 print *,'so this is really to prvent to program from cycling'
	 print *,'for ever in the unlikely event something goes wrong'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'NONL')then
	 print *,' '
	 print *,'Keyword     : nonl*inear_equation'
	 print *,'valid values: t/f'
	 print *,'flag for either nonlinear or linear pb equation '
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:6).eq.'PDB_IN')then
	 print *,' '
	 print *,'Keyword     : pdb_in*put_file'
	 print *,'valid values: file name of input atom coordinate file'
	 print *,'used for coordinates of molecule(s) '
	 ifound = .true.
      end if
	if(line(1:6).eq.'PDB2_IN')then
	 print *,' '
	 print *,'Keyword     : pdb2_in*put_file'
	 print *,'valid values: file name of input atom coordinate file'
	 print *,'used for additional coordinates of molecule(s) '
	 ifound = .true.
      end if
	if(line(1:7).eq.'PDB_OUT')then
	 print *,' '
	 print *,'Keyword     : pdb_out*put_file'
	 print *,'valid values: file name for an output file in pdb'
	 print *,'format, with the coordinates of pdb_input_file'
	 print *,'but with the assigned radius and charge'
	 print *,'written in the occupancy & B-factor fields'
	 print *,'usual name *.atm. Ignored if atom_file_output option'
	 print *,'is false'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:6).eq.'PHI_IN')then
	 print *,' '
	 print *,'Keyword     : phi_in*put_file'
	 print *,'valid values: file name of input potential map file'
	 print *,'usual extension *.phi, used for focussing boundary'
	 print *,'conditions. Ignored if boundary_condition not focussing'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:7).eq.'PHI_OUT')then
	 print *,' '
	 print *,'Keyword     : phi_out*put_file'
	 print *,'valid values: file name of potential map output'
	 print *,'usual extension *.phi for delphi format, *.grd for'
	 print *,'Insight format'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'PROB')then
	 print *,' '
	 print *,'Keyword     : probe_radius'
	 print *,'valid values: positive real'
	 print *,'radius of probe sphere used to generate molecular volume'
	 print *,'that defines the inside dielectric region of molecule(s)'
	 print *,'usual value is 1.4angstroms, the standard water radius'
	 print *,'or slightly larger 1.6-1.8 to eliminate small cavities' 
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'RADI')then
	 print *,' '
	 print *,'Keyword     : radi*us_file'
	 print *,'valid values: name of radius assignment file which '
	 print *,'contains a list of rules used to assign radii to'
	 print *,'the atoms- see example file for format'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'RELA')then
	 print *,' '
	 print *,'Keyword     : rela*xation_parameter'
	 print *,'valid values: positive number'
	 print *,'this is the gauss-seidel relaxation parameter for the'
	 print *,'correction potential iterations. >1 is overrelaxation'
	 print *,'<1 is underrelaxation.  A reasonable value is 1.4 to 1.6'
	 print *,'however the best value for optimal convergence will vary'
	 print *,'dependeing on salt concentration, scale and how highly'
	 print *,'charged the molecule is.  This parameter, and the '
	 print *,'number and depth of multigridding iterations are the'
	 print *,'main parameters one should play with to improve'
	 print *,'the convergence rate'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'SALT')then
	 print *,' '
	 print *,'Keyword     : salt*_concentration'
	 print *,'NOW OBSOLETE- USE cat_mon, cat_div, ani_mon, ani_div to specify salt ion concs.'
	 print *,' valid values: positive real. '
	 print *,'the concentration of 1-1 salt in the solvent '
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'SCAL')then
	 print *,' '
	 print *,'Keyword     : scal*e'
	 print *,'valid values: positive real '
	 print *,'scale, in grids/per angstrom, used to map molecule'
	 print *,'into the box.  applicable when sizing=scale, otherwise'
	 print *,'it is ignored'
	 ifound = .true.
      end if
	if(line(1:7).eq.'SITE_CH')then
	print *,'Keyword   : site_ch*arge_file'
	print *,'valid values: file name of 2nd charge file which will be'
	print *,'used with site potential option to calculate interaction'
	print *,'energy'
	 ifound = .true.
      end if
	if(line(1:7).eq.'SITE_IN')then
	 print *,' '
	 print *,'Keyword     : site_in*put_file'
	 print *,'valid values: file name of pdb format file containing'
	 print *,'coordinates where potential and field will be'
	 print *,'calculated. Ignored if site_potential flag is false'
	 print *,'usual extension: *.pdb '
	 ifound = .true.
      end if
	if(line(1:8).eq.'SITE_OUT')then
	 print *,' '
	 print *,'Keyword     : site_out*put_file'
	 print *,'valid values: file name where potentials and fields will be'
	 print *,'written. ignored if site_potential flag is false.'
	 print *,'usual extension *.frc'
	 ifound = .true.
      end if
	if(line(1:8).eq.'SITE_POT')then
	 print *,' '
	 print *,'Keyword     : site_pot*entials'
	 print *,'valid values: t/f'
	 print *,' flag for whether potentials and fields will be written '
	 ifound = .true.
      end if
	if(line(1:4).eq.'SIZI')then
	 print *,' '
	 print *,'Keyword     : sizi*ng'
	 print *,'valid values: scale/fill/border'
	 print *,'method used to scale molecule into grid. scale requires'
	 print *,'explicit scale, and x,y,z for center of grid. fill will'
	 print *,'put geometric center of molecule in center of grid'
	 print *,'such that longest of x/y/z dimensions fills fill % of grid.'
	 print *,'border puts center of molecule at center, and leaves at least'
	 print *,'border angstroms distance to edge of box'
	 ifound = .true.
      end if
	if(line(1:4).eq.'SOLU')then
	 print *,' '
	 print *,'Keyword     : solu*te_dielectric'
	 print *,'valid values: positive real'
	 print *,'value of dielectric assigned to points inside molecules'
	 print *,'molecular volume'
	 ifound = .true.
      end if
	if(line(1:4).eq.'SOLV')then
	 print *,' '
	 print *,'Keyword     : solv*ent_dielectric'
	 print *,'valid values: positive real'
	 print *,'value of dielectric assigned to points outside molecules'
	 print *,'molecular volume, i.e. in solvent'
	 ifound = .true.
      end if
	if(line(1:4).eq.'SPHE')then
	 print *,' '
	 print *,'Keyword     : sphe*rical_charge_dist'
	 print *,'valid values: t/f'
	 print *,'flag specifying whether to use anti-aliasing to'
	 print *,'distribute charge on grid. otherwise normal trilinear'
	 print *,'scheme is used.'
	 ifound = .true.
      end if
	if(line(1:4).eq.'TITL')then
	 print *,' '
	 print *,'Keyword     : titl*e'
	 print *,'valid values: string with no embbedded blanks or commas'
	 print *,' '
	 ifound = .true.
      end if
	if(line(1:4).eq.'TEMP')then
	 print *,' '
	 print *,'Keyword     : temp*erature'
	 print *,'valid values: positive real'
	 print *,'temperature in Kelvin '
	 ifound = .true.
      end if
	if(line(1:4).eq.'XCEN')then
	 print *,' '
	 print *,'Keyword     : xcen*ter, ycen*ter, zcen*ter'
	 print *,'valid values: real'
	 print *,'position of center of grid, in angstroms. used with the'
	 print *,'sizing=scale option, otherwise ignored'
	 ifound = .true.
      end if
	if(line(1:4).eq.'XPER')then
	 print *,' '
	 print *,'Keyword     : xper*iodic, yper*iodic, zper*iodic'
	 print *,'valid values: t/f'
	 print *,'three flags specifying whether periodic boundary '
	 print *,'conditions are applied at x,y,z box boundaries'
	 ifound = .true.
      end if
	if(line(1:4).eq.'SMOO')then
	 print *,' '
	 print *,'Keyword     : smoo*th_dielectric'
	 print *,'valid values: 0/1/2'
	 print *,'0: no dielectric smoothing, 1: 9 point smoothing'
	 print *,'2: 15 point smoothing using Gaussian weighted'
	 print *,'harmonic average, decay length length_smooth (Ang)'
	 ifound = .true.
      end if
	if(line(1:4).eq.'LENG')then
	 print *,' '
	 print *,'Keyword     : leng*th_smooth'
	 print *,'valid values: + real'
	 print *,'decay length in angstroms for dielectric smoothing'
	 ifound = .true.
      end if
	if(line(1:5).eq.'ISALT')then
	 print *,' '
	 print *,'Keyword     : isalt*_concentration'
	 print *,'valid values: + real'
	 print *,'the concentration of 1-1 salt in the solvent '
	 print *,'in the region of a channel in membrane '
	 print *,' where IMEMB*rane_position < Z < OMEMB*rane_position'
	 print *,' For Z < IMEMB*rane_position , salt conc is salt*_concentration'
	 ifound = .true.
      end if
	if(line(1:5).eq.'OSALT')then
	 print *,' '
	 print *,'Keyword     : osalt*_concentration'
	 print *,'valid values: + real'
	 print *,'the concentration of 1-1 salt in the solvent '
	 print *,'in the region outside the membrane'
	 print *,' where OMEMB*rane_position < Z'
	 print *,' For Z < IMEMB*rane_position , salt conc is salt*_concentration'
	 ifound = .true.
      end if
	if(line(1:5).eq.'IMEMB')then
	 print *,' '
	 print *,'Keyword     : imemb*rane_position'
	 print *,'valid values:  real'
	 print *,'z (in angstroms) defining left boundary'
	 print *,'of inner region in membrane channel'
	 ifound = .true.
      end if
	if(line(1:5).eq.'OMEMB')then
	 print *,' '
	 print *,'Keyword     : omemb*rane_position'
	 print *,'valid values:  real'
	 print *,'z (in angstroms) defining right boundary'
	 print *,'of inner region in membrane channel'
	 ifound = .true.
      end if
	if(ifound)then
	  stop
	else
	  return
	end if
	end
