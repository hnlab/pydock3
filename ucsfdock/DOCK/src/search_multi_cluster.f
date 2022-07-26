c     This subroutine searches through a database of "ligands", and
c     returns the highest-scoring orientations found for the highest-
c     scoring molecules.
c     Addition of dock 3.0 features ECM 5/91, latest modifications 3/92.
c     Modified to support force-field score minimization DAG 4/94.
c     Added support for solvation info (BKS)
c     Rewritten to support different, more flexible call structure (RGC) 2011.
c-----------------------------------------------------------------------
      module search_multi_cluster

      implicit none
      integer signalflag
      contains

      subroutine run_search_multi_cluster(grids0, phimap0, 
     &    recdes0, ligdes0, gist0,
     &    solvmap0,rec_des_r0, vdwmap0, options0, allminlimits,
c     &    allmaxlimits,spheres0, MAXTYV, sra, srb, MAXOR, MAXCTR, 
     &    allmaxlimits,sphere_sets, MAXTYV, sra, srb, MAXOR, MAXCTR, 
c     &    fdlig, sph_idx)
     &    fdlig)

      use phimaptype
      use gisttype
      use solvmaptype
      use vdwmaptype
      use status
      use optionstype
      use gridstype
      use db2type
      use ligscoretype
      use matchtype
      use filenums
      use spheres
      use score_mol
      use atomscoretype

c these are the dynamically allocated grids
      type(flexgrids), intent(inout) :: grids0
c these are user-defined types that contain information about grids (usually)
      type(phimap), intent(inout) :: phimap0, recdes0, ligdes0
      type(gistparm), intent(inout) :: gist0, rec_des_r0
      type(solvmap), intent(inout) :: solvmap0
      type(vdwmap), intent(inout) :: vdwmap0
c options
      type(options), intent(inout) :: options0
c for outside grid checking
      real, dimension(3) :: allminlimits, allmaxlimits
c spheres & chemical matching data
c      type(spherest), intent(in) :: spheres0
      type(spherest), dimension(10) :: sphere_sets ! array to hold sph clusters
c vdw parameters
      integer, intent(in) :: MAXTYV ! vdw types
      real, dimension(MAXTYV), intent(in) :: sra, srb !square roots of vdw parms
      integer, intent(in) :: MAXOR ! max orientations
      integer, intent(in) :: MAXCTR !!how many centers match, 4 is fine
      integer (kind=8), intent(inout) :: fdlig !ligand file handle
      integer :: sph_idx
c     variables --
      type(db2) :: db2lig !ligand data stored here
      type(ligscoret) :: ligscore !saves many top poses
      type(ligscoret) :: ligscore_mini !saves top poses for minimizer
      type(ligscoret) :: ligscoreeach !saves one top pose for each flexible receptor combination
      type(atomscoret) :: atomscore !recalculate per atom scores
      type(matcht) :: match !stuff about matching
      type(matcht) :: match_mini !match object for minimizer
      character (len=80) molout !filename to save
      character (len=80) molout_premin !premin filename to save
      character (len=10) sph_idx_str !string version of sph_idx
      logical iend
c        iend:  indicator variable for end of ligand file.
c               is equal to zero if end not reached.
      integer molct
c        molct:  the number of ligands searched on this run.
      integer count !temp counter, don't use i,j,n or other one letter nonsense
c best scoring conformation for a given ligand
      integer flush_int
c        # of compounds interval to flush buffer to OUTDOCK
      real tcorr(3, MAXPTS) !used to hold the rigid component heavy atoms
      integer tcolor(MAXPTS)
      integer tcount !count of rigid heavy atoms
      integer tcountorig !not counting cloud additional match spheres
      real telaps, time2, time1 !times
      integer tot_match, tot_sets, tot_nodes, num_hier ! this are to keep track of stats, TEB
      integer(KIND=8) tot_complex
      integer total_iter
      integer final_iter
      integer mc_total_iter
      logical exists
      integer dock_status !uses status.h enums
      integer istat !ligand file status
      integer istat_premin !premin ligand file status
      integer tempsave, temprank !counter for multiple output
      integer tempmini !counter for minimizer
      integer temp_ori !counter for original matchnum
      integer cloudcount, cloudtotal !counter and overall # of times to run
      logical doing_cloud !whether or not the cloud is actually happening
      integer setstart, setend !controls which sets (complete confs) to score
      integer centrl !ligand seed (start) sphere
      integer centrr !receptor seed (start) sphere
      integer debug1 !temporary variable used in debugging loops
      integer current_match_num !temporry variable used to print matching spheres
      integer coord_counter, set_counter !temp vars for printing matching spheres

c variables for match_method choosing, control
      real curdislim !temporary variable, keeps track of current distance limit
      logical more_matches !true if we want to find more matches.
c these are the new degeneracy controls. the 2 hashes are the sets of matching
c spheres, one for rec, one lig. the count is how many pairs have been added.
      integer hash(MAXOR, MAXCTR), hashcount
      integer (kind=8) :: fdmol !output mol2.gz file handle
      integer (kind=8) :: fdmol_premin !premin output mol2.gz file handle
      integer :: outcount

c format lines for output
      character (len=*), parameter :: molexam =
     &     '(i8,"  molecules examined on this run")'
      character (len=*), parameter :: outdockerr =
     &     '(i6,1x,a16,i8,1x,i10,1x,f7.2,1x,a)'
      character (len=*), parameter :: outdockline = '(i6,1x,a16,1x,a16,
     &       1x,i8,1x,i10,1x,f7.2,1x,i3,1x,i9,1x,i9,1x,i6,3x,f7.2,2x,
     &       f7.2,1x,f7.2,1x,f7.2,f7.2,1x,f7.2,1x,f7.2,1x,f7.2,1x,f7.2,
     &       1x,f7.2,f10.2)'

c    --- Benjamin Tingle 11/17, testing out signal handling & restart capabilities
      integer SIGUSR1
      integer ret
      ! restart mol count- how many db2 files were evaluated in the previous run
      integer redb2c
      ! restart lig count- how many ligand structures were evaluated from the 
      ! most recent db2 in the previous run 
      integer religc
      ! restart mol count- how many ligand structures were evaluated during the previous run
      integer remolc 

      integer ligc ! number of ligands evaluated for the current db2 file
      integer db2c ! number of db2 files evaluated
      
      ! dummy variables needed by certain functions
      integer n
      integer inputstatus   
      integer loc

      integer signal ! need for portland group

c   --- initialize restart variables (Ben) ---

      redb2c = 0
      religc = 0
      remolc = 0
      ligc = 0
      db2c = 0
      iend = .false.

c   --- move our file handles to the spot indicated by the restart file

      open(unit=RESTARTFILE, file="restart", err=999,
     &          status='old', action='read')
      read(RESTARTFILE, *) redb2c, religc, remolc
      close(RESTARTFILE, status='delete')

      do n = 1, redb2c
        read(SDIFILE, '(a255)') options0%ligfil
      enddo

      ! not entirely sure what the gztell does, but having it here
      ! seems to prevent a segfault from gzopen
      ! it may not be kosher to open a new file if the current one that hasn't
      ! been interacted with yet, but that's just my guess
      !call gzseek(fdlig, options0%pos, inputstatus)
      !all gztell(fdlig, loc)
      !call gzopen(fdlig, 'r', options0%ligfil, inputstatus)

      do n = 1, religc
        call ligread2(db2lig, options0, 
     &      iend, tcorr, tcolor, tcount, fdlig, ligc, db2c, .true.)
      enddo

      db2c = redb2c

c   --- initialize signal handler (Ben) ---

! if restart file is not found, we continue normal DOCK operations here
999   signalflag = 0
      SIGUSR1 = 10
      ret = signal(SIGUSR1, signalhandler) ! for gfortran
      !ret = signal(SIGUSR1, signalhandler, -1) ! for portland group

c     --- initialize variables ---
      call allocate_ligscore(ligscore, options0%nsav, OUTDOCK)
      call allocate_atomscore(atomscore, maxpts, OUTDOCK)
      if (options0%flexible_receptor .and.
     &    options0%score_each_flex) then
        call allocate_ligscore(ligscoreeach, grids0%total_combinations,
     &      OUTDOCK)
      endif

      !flush_int = 1000 !flush after every (this many) ligands
      flush_int = options0%input_flush_int !flush after every (this many) ligands
      molct = 0
      match%nmatch = 0 !initialize various things
      num_hier = 0
      tot_match = 0
      tot_sets = 0
      tot_nodes = 0
      tot_complex = 0
      call allocate_match(match, maxor, OUTDOCK)
      iend = .false.

c     open output files for the pre-minimizer
      if ((options0%minimize .eq. 1) .and.
     &    (options0%output_premin .eq. 1)) then
        open(unit=OUTDOCK_premin, file='OUTDOCK_premin', action='write')
        molout_premin = trim(options0%outfil)//'premin.mol2.gz'
        write(OUTDOCK, '(a,a)') 'output file: ', molout_premin
        call gzopen(fdmol_premin, 'w', molout_premin, istat_premin) !open output ligand file
      endif

c     open output files
c      write(sph_idx_str, '(I0.4)') sph_idx
c      molout = trim(options0%outfil)//sph_idx_str
      molout = trim(options0%outfil)//'mol2.gz'
c      molout = trim(molout)//'.mol2.gz'
      write(OUTDOCK, '(a,a)') 'output file: ', molout
      
c     calculation of receptor sphere-sphere distances.
      do sph_idx = 1, options0%k_clusters
        write(sph_idx_str, '(I0.4)') sph_idx
        call intdis(sphere_sets(sph_idx)%nsphr,
     &    sphere_sets(sph_idx)%spcorr,
     &    sphere_sets(sph_idx)%disr,
     &    match%dmaxr, MAXPTS)
        write(OUTDOCK, *) 'maximum receptor sphere-sphere distance',
     &    match%dmaxr
      enddo
      call gzopen(fdmol, 'w', molout, istat) !open output ligand file

      !top of main section of OUTDOCK file
      write(OUTDOCK, '(a,a,a,a)')
     & '  mol#           id_num     flexiblecode  matched    nscored  ',
     & '  time hac    setnum    matnum   rank charge    elect +  gist',
     & ' +   vdW + psol +  asol + tStrain + mStrain + rec_d + r_hyd =',
     & '    Total'
      if ((options0%minimize .eq. 1) .and.
     &    (options0%output_premin .eq. 1)) then
        write(OUTDOCK_premin, '(a,a,a,a)')
     & '  mol#           id_num     flexiblecode  matched    nscored  ',
     & '  time hac    setnum    matnum   rank charge    elect +  gist',
     & ' +   vdW + psol +  asol + tStrain + mStrain + rec_d + r_hyd =',
     & '    Total'
      endif

c     call doflush(OUTDOCK)
c     if ((options0%minimize .eq. 1) .and.
c    &    (options0%output_premin .eq. 1)) then
c       call doflush(OUTDOCK_premin)
c     endif
      final_iter = 0
      do while (.not. iend) !an actual loop

c       check for interrupt signal at the start of each loop (Ben)
        if (signalflag .eq. 1) then
          write(OUTDOCK, *)
     & 'interrupt signal detected since last ligand- ',
     & 'initiating clean exit & save'
          signalflag = 0
          ! write current progress stats out to restart file
          open(unit=RESTARTFILE, file="restart",
     &          status='new', action='write')
          write(RESTARTFILE, *) db2c, ligc, molct
          close(RESTARTFILE, status='keep')
          exit ! break out of main loop
        endif

        !total_iter = 0
        total_iter = 0
        
c       --- read a ligand structure from the dbase ---
        call ligread2(db2lig, options0,
     &      iend, tcorr, tcolor, tcount, fdlig, 
     &      ligc, db2c, .false.) !read one hierarchy 

        ! add the current number of conformations in the hierarchy to
        ! calaculate the total nuber docked.
        tot_sets = tot_sets + db2lig%total_sets
        tot_nodes = tot_nodes + db2lig%total_confs
        num_hier = num_hier + 1

        tcountorig = tcount !save the number of matching spheres here
        match%nmatch = 0 !initialize various things
        call allocate_match(match, maxor, OUTDOCK)
        dock_status = NOMATCH
        ligscore%savedcount = 0 !reset the number of poses saved
        ligscore%numscored = 0

        if (options0%flexible_receptor .and.
     &      options0%score_each_flex) then
          call reset_ligscore(ligscoreeach)
        endif

        telaps = 0.0

        if (iend) then !if end of file read, no more ligands
          exit !break out of do loop
        endif

        molct = molct + 1
        
c       check for minimum, maximum number of atoms.
        if ((db2lig%total_heavy_atoms .lt. options0%natmin)
     &      .or. (db2lig%total_heavy_atoms .gt. options0%natmax)) then
          write(OUTDOCK, outdockerr) molct, db2lig%refcod, match%nmatch,
     &                   ligscore%numscored, telaps, 'skip_size'
          if ((options0%minimize .eq. 1) .and.
     &        (options0%output_premin .eq. 1)) then
            write(OUTDOCK_premin, outdockerr) molct, db2lig%refcod,
     &                     match%nmatch, ligscore%numscored,
     &                     telaps, 'skip_size'
          endif
          cycle !skip to next molecule

        endif
c strategy for cloud matching. add extra match spheres to tcorr, tcount, tcolor
c run intdis, reord, makbin, the match loop after that.
c then dock each cluster. if not doing clusters or no cluster information
c is present for this ligand, treat whole ligand as a single cloud/cluster
        if (options0%do_clusters .and.
     &      (db2lig%total_clusters .gt. 0)) then
          cloudtotal = db2lig%total_clusters
          doing_cloud = .true.
        else
          cloudtotal = 1
          doing_cloud = .false.
        endif

c this loop is either run once (no clouds) or once for each cloud
        do cloudcount = 1, cloudtotal !for each cloud, or once for whole ligand
          do sph_idx = 1, options0%k_clusters
            call get_time(time1) !time before this ligand is scored saved now
            ligscore%numscored = 0
            if (doing_cloud) then !add to tcorr, tcolor, tcount
              tcount = tcountorig !reset to before adding cloud matching spheres
              call add_cloud_spheres(cloudcount, tcorr, tcolor, tcount,
     &            db2lig)
            endif
            call intdis(tcount, tcorr, sphere_sets(sph_idx)%disl,
     &         match%dmaxl, MAXPTS)
c           initialize variables for subgraph generation.
            match%nmatch = 0
            call allocate_match(match, maxor, OUTDOCK)
            dock_status = NOMATCH
            hashcount = 0 !reset the degeneracy counter to 0
            more_matches = .true. !always do at least once
            curdislim = options0%dislim !start at beginning no matter what

            do while (more_matches)
              do centrl = 1, tcount !use each ligand & receptor sphere as start
                do centrr = 1, sphere_sets(sph_idx)%nsphr !seed point for generating spheres
c                 this is the call that generates orientations, which proceeds to
c                 run through the hierarchy and scoring, etc
                  !match just puts things into coml, comr, rot now

                  call fullmatch(tcount, tcolor, centrl, centrr,
     &              sphere_sets(sph_idx)%scolor,
     &              sphere_sets(sph_idx)%lgspcl, options0%cmatch,
     &              curdislim, sphere_sets(sph_idx)%disl,
     &              sphere_sets(sph_idx)%disr,
! c                   fix buger here, jklyu, 2019.4.01
! c     &              spheres0%spcorr, db2lig%coords, tcount,
     &              sphere_sets(sph_idx)%spcorr, tcorr, tcount,
     &              sphere_sets(sph_idx)%nsphr,
     &              MAXPTS, MAXCOL, MAXOR, MAXCTR, db2lig%total_coords,
     &              options0%minnodes, options0%maxnodes,
     &              match,
     &              hash, hashcount)

                enddo
              enddo
              if (options0%match_method .eq. 1) then !quit now no matter what
                more_matches = .false.
              else if (options0%match_method .eq. 2) then !maybe quit, maybe continue
                if (match%nmatch .ge. options0%matchgoal) then
                  more_matches = .false.
                else if (curdislim .gt. options0%dismax) then
                  more_matches = .false.
                else !no if,  check time though
                  call get_time(time2)
                  telaps = time2 - time1
                  if (telaps .gt. options0%timeout) then !we don't want to waste
                    more_matches = .false. !more time than we already have
                  else !this means we want to do another run
                    curdislim = curdislim + options0%disstep !increment distance tolerance
                    !the hashes stay the same and aren't reset so we don't repeat
                    !work
                  endif
                endif
              ! jklyu, 20200213, test color matching
              else if (options0%match_method .eq. 3) then !maybe quit, maybe continue
                if (curdislim .gt. options0%dismax) then
                  more_matches = .false.
                else !no if,  check time though
                  call get_time(time2)
                  telaps = time2 - time1
                  if (telaps .gt. options0%timeout) then !we don't want to waste
                    more_matches = .false. !more time than we already have
                  else !this means we want to do another run
                    curdislim = curdislim + options0%disstep !increment distance tolerance
                    !the hashes stay the same and aren't reset so we don't repeat
                    !work                
                  endif
                endif
              endif
            enddo

            !calculating the total number of match or orientations obtained during docking run
            tot_match =  tot_match + match%nmatch
            ! calculating the total number of complexes attempted during
            ! the docking
            tot_complex = tot_complex + match%nmatch * db2lig%total_sets


c init the  se here???
            ligscore%savedcount = 0 !reset the number of poses saved
            if (options0%flexible_receptor .and.
     &          options0%score_each_flex) then
              call reset_ligscore(ligscoreeach)
            endif

c part of   clouds is to only score certain clusters of poses.. needs passed here
            if (doing_cloud) then !change setstart & setend
              setstart = db2lig%cluster_set_start(cloudcount)
              setend = db2lig%cluster_set_end(cloudcount)
            else !if not doing clouds
              setstart = 1
              setend = db2lig%total_sets !just do them all
            endif
            !next line actually calls scoring function now that matches are
            !all generated. no global variables used anymore.
c            write(6,*), "dockstatus before is",dock_status
            call calc_score_mol(dock_status, setstart, setend,
     &          db2lig, options0, ligscore, ligscoreeach, grids0,
     &          vdwmap0, phimap0, recdes0, ligdes0, gist0, solvmap0,
     &          rec_des_r0, match, allminlimits, allmaxlimits,
     &          sra, srb,
     &          MAXOR, db2lig%total_confs, db2lig%total_sets,
     &          db2lig%total_atoms, db2lig%total_coords,
     &          MAXTYV)
            call get_time(time2)
            telaps = time2 - time1
c            write(6,*), "dockstatus is",dock_status
            if (dock_status .eq. NOMATCH) then
              write(OUTDOCK, outdockerr) molct, db2lig%refcod,
     &            match%nmatch, ligscore%numscored, telaps, 'no_match'
              if ((options0%minimize .eq. 1) .and.
     &            (options0%output_premin .eq. 1)) then
                write(OUTDOCK_premin, outdockerr) molct, db2lig%refcod,
     &              match%nmatch, ligscore%numscored, telaps, 'no_match'
              endif
              cycle !next ligand
            endif

c            write(6,*) "num nmatches is ",match%nmatch
c    --if   no good poses of this ligand are found goto the next ligand --
            if (dock_status .eq. OUTSIDEGRIDS) then
              write(OUTDOCK, outdockerr) molct, db2lig%refcod,
     &            match%nmatch, ligscore%numscored, telaps,
     &            'outside_grids'
              if ((options0%minimize .eq. 1) .and.
     &            (options0%output_premin .eq. 1)) then
                write(OUTDOCK_premin, outdockerr) molct, db2lig%refcod,
     &              match%nmatch, ligscore%numscored, telaps,
     &              'outside_grids'
              endif
              cycle !next ligand
            else if (dock_status .eq. BUMPED) then
              write(OUTDOCK, outdockerr) molct, db2lig%refcod,
     &            match%nmatch, ligscore%numscored, telaps, 'bump'
              if ((options0%minimize .eq. 1) .and.
     &            (options0%output_premin .eq. 1)) then
                write(OUTDOCK_premin, outdockerr) molct, db2lig%refcod,
     &              match%nmatch, ligscore%numscored, telaps, 'bump'
              endif
              cycle !next ligand
            else if (dock_status .eq. CLASHES) then
              write(OUTDOCK, outdockerr) molct, db2lig%refcod,
     &            match%nmatch, ligscore%numscored, telaps, 'clashes'
              if ((options0%minimize .eq. 1) .and.
     &            (options0%output_premin .eq. 1)) then
                write(OUTDOCK_premin, outdockerr) molct, db2lig%refcod,
     &              match%nmatch, ligscore%numscored, telaps, 'clashes'
              endif
              cycle !next ligand
            else if (dock_status .eq. NOTCHECKED) then
              write(OUTDOCK, outdockerr) molct, db2lig%refcod,
     &            match%nmatch, ligscore%numscored, telaps,
     &            'clashes/notchecked'
              if ((options0%minimize .eq. 1) .and.
     &            (options0%output_premin .eq. 1)) then
                write(OUTDOCK_premin, outdockerr) molct, db2lig%refcod,
     &              match%nmatch, ligscore%numscored, telaps,
     &              'clashes/notchecked'
              endif
              cycle !next ligand
            else if (dock_status .ne. ALLOKAY .or.
     &         ligscore%savedcount == 0 ) then
              write(OUTDOCK, outdockerr) molct, db2lig%refcod,
     &            match%nmatch, ligscore%numscored, telaps,
     &            'No viable poses.  Grids might be too small.  '
              if ((options0%minimize .eq. 1) .and.
     &            (options0%output_premin .eq. 1)) then
                write(OUTDOCK_premin, outdockerr) molct, db2lig%refcod,
     &              match%nmatch, ligscore%numscored, telaps,
     &              'No viable poses.  Grids might be too small.  '
              endif
              cycle !next ligand
            endif

            if (dock_status .eq. ALLOKAY) then
c              if ((options0%minimize .ne. 1) .and.
c     &             options0%mol2_minimizer .ne. 1  .or.
c     &             (ligscore%pose_score(tempsave) .gt.
c     &             options0%bmptotal)) then ! if the minimizer is off or if ! the score is above the bump ! cutoff, write into OUTDOCK ! (because mol2write is not ! called) ! Minimizer is call in the ! mol2write function and then ! OUTDOCK is writen
              if ((options0%minimize .ne. 1) .and.
     &             (options0%mol2_minimizer .ne. 1) .and.
     &             (options0%mc_minimize .ne. 1)) then
c                 write(6,*), "minimize is off"
                 do tempsave = 1, ligscore%savedcount

                  write(OUTDOCK, outdockline) molct, db2lig%refcod,
     &              ligscore%pose_reccode(tempsave),
     &              match%nmatch, ligscore%numscored,
     &              telaps, db2lig%total_heavy_atoms,
     &              ligscore%setsave(tempsave),
     &              ligscore%orientsave(tempsave),
     &              tempsave, db2lig%total_charge, 
     &              ligscore%pose_es(tempsave),
     &              ligscore%pose_gi(tempsave),
     &              ligscore%pose_vs(tempsave),
     &              ligscore%pose_ps(tempsave),
     &              ligscore%pose_as(tempsave),
     &              ligscore%pose_is(tempsave),
     &              ligscore%pose_rs(tempsave),
c    &              ligscore%pose_ds(tempsave),
     &              ligscore%pose_rd(tempsave),
     &              ligscore%pose_hs(tempsave),
     &              ligscore%pose_score(tempsave)
                 enddo
              
              else if (options0%mc_minimize .eq. 1) then
c                write(6,*), "Monte Carlo is on"
                match_mini%nmatch = match%nmatch
                call allocate_match(match_mini, ligscore%savedcount,
     &             OUTDOCK)
                call allocate_ligscore(ligscore_mini,
     &             ligscore%savedcount,
     &             OUTDOCK)
                ligscore_mini%numscored = ligscore%numscored
                ligscore_mini%savedcount = 0
                do tempmini = 1, ligscore%savedcount
                  call run_montecarlo(options0, db2lig, ligscore,
     &                ligscore_mini, match, match_mini,
     &                molct, cloudcount,
     &                MAXOR, fdmol, tempmini, tempmini,
     &                atomscore, grids0, vdwmap0, phimap0,
     &                recdes0, ligdes0, gist0, solvmap0,
     &                rec_des_r0, sra, srb, maxtyv,
     &                allminlimits, allmaxlimits, time1,
     &                mc_total_iter)
                  final_iter  = final_iter + mc_total_iter
                enddo
c                write(OUTDOCK, '(a16,i6)') 'count_mini: ',
c     &            ligscore_mini%savedcount
                ! write the results to OUTDOCK
                do tempmini = 1, ligscore_mini%savedcount
                  ! get the original rank info
                  temp_ori = ligscore_mini%orientsave(tempmini)
c                  write(6,*), "WRITING OUTDOCK"
                  write(OUTDOCK, outdockline) molct, db2lig%refcod,
     &              ligscore_mini%pose_reccode(tempmini),
     &              match_mini%nmatch, ligscore_mini%numscored,
     &              telaps, db2lig%total_heavy_atoms,
     &              ligscore_mini%setsave(tempmini),
     &              ligscore%orientsave(temp_ori),
     &              tempmini, temp_ori,
     &              ligscore_mini%pose_es(tempmini),
     &              ligscore_mini%pose_gi(tempmini),
     &              ligscore_mini%pose_vs(tempmini),
     &              ligscore_mini%pose_ps(tempmini),
     &              ligscore_mini%pose_as(tempmini),
     &              ligscore_mini%pose_is(tempmini),
     &              ligscore_mini%pose_rs(tempmini),
c     &              ligscore_mini%pose_ds(tempmini),
     &              ligscore_mini%pose_rd(tempmini),
     &              ligscore_mini%pose_hs(tempmini),
     &              ligscore_mini%pose_score(tempmini)
                enddo
              !run minimizer on topX scoring poses
              else if ( options0%minimize .eq. 1) then
c                 write(6,*), "minimize is on"
                !output the scores and poses before running the minimizer
                if ( options0%output_premin .eq. 1) then
                 !output scores first
                  do tempsave = 1, ligscore%savedcount

                   write(OUTDOCK_premin, outdockline) molct,
     &               db2lig%refcod,
     &               ligscore%pose_reccode(tempsave),
     &               match%nmatch, ligscore%numscored,
     &               telaps, db2lig%total_heavy_atoms,
     &               ligscore%setsave(tempsave),
     &               ligscore%orientsave(tempsave),
     &               tempsave, db2lig%total_charge, 
     &               ligscore%pose_es(tempsave),
     &               ligscore%pose_gi(tempsave),
     &               ligscore%pose_vs(tempsave),
     &               ligscore%pose_ps(tempsave),
     &               ligscore%pose_as(tempsave),
     &               ligscore%pose_is(tempsave),
     &               ligscore%pose_rs(tempsave),
c     &               ligscore%pose_ds(tempsave),
     &               ligscore%pose_rd(tempsave),
     &               ligscore%pose_hs(tempsave),
     &               ligscore%pose_score(tempsave)
                  enddo
                 !output poses second
                  do outcount = 1, ligscore%savedcount
c                    write(6,*), "score is", ligscore%pose_score(outcount)
c                    write(6,*), "posescore:",ligscore%pose_score(outcount)
c                    write(6,*), "savelimit:",options0%save_limit
c                    write(6,*), "bmptotal",options0%bmptotal
c                    write(6,*), "outcount",outcount
c                    write(6,*), "nwrite",options0%nwrite
                    if (ligscore%pose_score(outcount) .lt.
     &                  options0%save_limit .and.
     &                  ligscore%pose_score(outcount) .lt.
     &                  options0%bmptotal .and.
     &                  outcount .le. options0%nwrite) then
                      call mol2write(options0, db2lig, ligscore, match,
     &                    molct, cloudcount, MAXOR,
     &                    fdmol_premin, outcount,
     &                    outcount, atomscore, grids0, vdwmap0, phimap0,
     &                    recdes0, ligdes0, gist0, solvmap0, rec_des_r0,
     &                    sra, srb, maxtyv, allminlimits, allmaxlimits,
     &                    time1, total_iter)
                      final_iter = final_iter + total_iter
                    endif
                  enddo
                endif
                !initiate a new match object and a new ligscore object
                match_mini%nmatch = match%nmatch
                call allocate_match(match_mini, ligscore%savedcount,
     &              OUTDOCK)
                call allocate_ligscore(ligscore_mini,
     &              ligscore%savedcount,
     &              OUTDOCK)
                ligscore_mini%numscored = ligscore%numscored
                ligscore_mini%savedcount = 0
c                write(OUTDOCK, '(a16,i6)') 'count: ',
c     &            ligscore%savedcount
                do tempmini = 1, ligscore%savedcount
                  call run_minimizer(options0, db2lig, ligscore,
     &                ligscore_mini, match, match_mini,
     &                molct, cloudcount,
     &                MAXOR, fdmol, tempmini, tempmini,
     &                atomscore, grids0, vdwmap0, phimap0,
     &                recdes0, ligdes0, gist0, solvmap0,
     &                rec_des_r0, sra, srb, maxtyv,
     &                allminlimits, allmaxlimits, time1,
     &                total_iter)
                  !write(OUTDOCK, '(a16,i6)') 'tempmini: ', tempmini
c                  write(OUTDOCK, '(a16,i6)') 'temp_mini: ',
c     &            ligscore_mini%savedcount
                  final_iter = final_iter + total_iter
                enddo
c                write(OUTDOCK, '(a16,i6)') 'count_mini: ',
c     &            ligscore_mini%savedcount
                ! write the results to OUTDOCK
                do tempmini = 1, ligscore_mini%savedcount
                  ! get the original rank info
                  temp_ori = ligscore_mini%orientsave(tempmini)

                  write(OUTDOCK, outdockline) molct, db2lig%refcod,
     &              ligscore_mini%pose_reccode(tempmini),
     &              match_mini%nmatch, ligscore_mini%numscored,
     &              telaps, db2lig%total_heavy_atoms,
     &              ligscore_mini%setsave(tempmini), !setnum
     &              ligscore%orientsave(temp_ori), !matnum
     &              tempmini, db2lig%total_charge,
     &              ligscore_mini%pose_es(tempmini),
     &              ligscore_mini%pose_gi(tempmini),
     &              ligscore_mini%pose_vs(tempmini),
     &              ligscore_mini%pose_ps(tempmini),
     &              ligscore_mini%pose_as(tempmini),
     &              ligscore_mini%pose_is(tempmini),
     &              ligscore_mini%pose_rs(tempmini),
c     &              ligscore_mini%pose_ds(tempmini),
     &              ligscore_mini%pose_rd(tempmini),
     &              ligscore_mini%pose_hs(tempmini),
     &              ligscore_mini%pose_score(tempmini)

                enddo
              end if
              if ((options0%minimize .ne. 1) .and.
     &          (options0%mc_minimize .ne. 1)) then
                do outcount = 1, ligscore%savedcount
                  if (ligscore%pose_score(outcount) .lt.
     &                options0%save_limit .and.
     &                ligscore%pose_score(outcount) .lt.
     &                options0%bmptotal .and.
     &                outcount .le. options0%nwrite) then
                    call mol2write(options0, db2lig, ligscore, match,
     &                  molct, cloudcount, MAXOR, fdmol, outcount,
     &                  outcount, atomscore, grids0, vdwmap0, phimap0,
     &                  recdes0, ligdes0, gist0, solvmap0, rec_des_r0,
     &                  sra, srb, maxtyv, allminlimits, allmaxlimits,
     &                  time1, total_iter)
                    final_iter = final_iter + total_iter
                  endif
                enddo
                temprank = ligscore%savedcount + 1 !start here
              else
                do outcount = 1, ligscore_mini%savedcount
                  if (ligscore_mini%pose_score(outcount) .lt.
     &                options0%save_limit .and.
     &                ligscore_mini%pose_score(outcount) .lt.
     &                options0%bmptotal .and.
     &                outcount .le. options0%nwrite) then
c                    write(6,*), "WRITING MOL2 because minimize = 1"
                    if (options0%minimize .eq. 1) then
                        call mol2write(options0, db2lig, ligscore_mini,
     &                     match_mini, molct, cloudcount, MAXOR, fdmol,
     &                     outcount, outcount, atomscore,
     &                     grids0, vdwmap0,
     &                     phimap0, recdes0, ligdes0, gist0, solvmap0,
     &                     rec_des_r0, sra, srb, maxtyv, allminlimits,
     &                     allmaxlimits, time1, total_iter)
                        final_iter = final_iter + total_iter
                    else if (options0%mc_minimize .eq. 1) then
                        call mol2write(options0, db2lig, ligscore_mini,
     &                     match_mini, molct, cloudcount, MAXOR, fdmol,
     &                     outcount, outcount, atomscore,
     &                     grids0, vdwmap0,
     &                     phimap0, recdes0, ligdes0, gist0, solvmap0,
     &                     rec_des_r0, sra, srb, maxtyv, allminlimits,
     &                     allmaxlimits, time1, mc_total_iter)
                        final_iter = final_iter + mc_total_iter
                    endif
                  endif
                enddo
                temprank = ligscore_mini%savedcount + 1 !start here
              endif
              if (options0%flexible_receptor .and.
     &             options0%score_each_flex) then
                !write out to outdock again and mol2write
                do tempsave = 1, grids0%total_combinations !each receptor combo
                  if (ligscoreeach%good_pose(tempsave)) then !if good pose
                    temprank = temprank + 1 !advance this counter
                    write(OUTDOCK, outdockline) molct, db2lig%refcod,
     &                  ligscoreeach%pose_reccode(tempsave),
     &                  match%nmatch, ligscore%numscored,
     &                  telaps, db2lig%total_heavy_atoms,
     &                  ligscoreeach%setsave(tempsave),
     &                  ligscoreeach%orientsave(tempsave),
     &                  temprank, db2lig%total_charge,
     &                  ligscoreeach%pose_es(tempsave),
     &                  ligscoreeach%pose_gi(tempsave),
     &                  ligscoreeach%pose_vs(tempsave),
     &                  ligscoreeach%pose_ps(tempsave),
     &                  ligscoreeach%pose_as(tempsave),
     &                  ligscoreeach%pose_is(tempsave),
     &                  ligscoreeach%pose_rs(tempsave),
c     &                  ligscoreeach%pose_ds(tempsave),
     &                  ligscoreeach%pose_rd(tempsave),
     &                  ligscoreeach%pose_hs(tempsave),
     &                  ligscoreeach%pose_score(tempsave)
c                   if (ligscore%pose_score(outcount) .lt.
c    &                  options0%save_limit) then
                    if (ligscoreeach%pose_score(tempsave) .lt.
     &                  options0%save_limit .and.
     &                  ligscoreeach%pose_score(tempsave) .lt.
     &                  options0%bmptotal) then
                      call mol2write(options0, db2lig, ligscoreeach,
     &                    match, molct, cloudcount, MAXOR, fdmol,
     &                    tempsave, temprank, atomscore,
     &                    grids0, vdwmap0,
     &                    phimap0, recdes0, ligdes0, gist0,solvmap0,
     &                    rec_des_r0, sra, srb, maxtyv,
     &                    allminlimits, allmaxlimits,
     &                    time1, total_iter)
                      final_iter = final_iter + total_iter
                    endif
                  endif
                enddo
              endif
            endif
          enddo !end of k_clusters 
        enddo !end of clouds loop
c       flush buffer to OUTDOCK so user can see progress
        if (mod(molct, flush_int) .eq. 0) then
          !write(OUTDOCK,*) "I AM HERE"
          call doflush(OUTDOCK)
          if ((options0%minimize .eq. 1) .and.
     &        (options0%output_premin .eq. 1)) then
            call doflush(OUTDOCK_premin)
          endif
        endif
      enddo
      if (iend) then
        !if (options0%minimize .gt. 0) then
        write (OUTDOCK, *) "total minimization steps = ", final_iter
        !endif
        write (OUTDOCK, *) "total number of hierarchies: ",
     &       (num_hier-1) ! added one to meny
        write (OUTDOCK, *) "total number of orients (matches): ",
     &       tot_match
        write (OUTDOCK, *) "total number of conformations (sets): ",
     &       tot_sets
        write (OUTDOCK, *) "total number of nodes (confs): ",
     &       tot_nodes
        write (OUTDOCK, *) "total number of complexes: ",
     &       tot_complex
        write(OUTDOCK, *) "end of file encountered"
      endif
      call gzclose(fdmol, istat) !close ligand output file
      if ((options0%minimize .eq. 1) .and.
     &    (options0%output_premin .eq. 1)) then
        call gzclose(fdmol_premin, istat_premin) !close premin ligand output file
      endif
      return
      end subroutine run_search_multi_cluster

      subroutine signalhandler(signum)
        integer, intent(in) :: signum
        signalflag = 1 
      end subroutine signalhandler

      end module search_multi_cluster

c---------------------------------------------------------------------
c
c       Copyright (C) 2001 David M. Lorber and Brian K. Shoichet
c              Northwestern University Medical School
c                         All Rights Reserved.
c----------------------------------------------------------------------
c
c-----------------------------------------------------------------------
c
c       Copyright (C) 1991 Regents of the University of California
c                         All Rights Reserved.
c
