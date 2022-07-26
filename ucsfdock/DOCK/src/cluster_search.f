c     This subroutine searches through a database of "ligands" with the
c     same rigid segment, and
c     returns the highest-scoring orientations found for the highest-
c     scoring molecules.  
c     Addition of dock 3.0 features ECM 5/91, latest modifications 3/92.
c     Modified to support force-field score minimization DAG 4/94.
c     Added support for solvation info (BKS)
c     Rewritten to support different, more flexible call structure (RGC) 2011.
c-----------------------------------------------------------------------
      module cluster_search

      implicit none
      contains

      subroutine run_cluster_search(grids0, phimap0, recdes0, ligdes0,
     &    gist0, solvmap0, rec_des_r0, vdwmap0, options0, allminlimits,
     &    allmaxlimits, spheres0, MAXTYV, sra, srb, MAXOR, MAXCTR,
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
      type(options), intent(in) :: options0
c for outside grid checking
      real, dimension(3) :: allminlimits, allmaxlimits
c spheres & chemical matching data
      type(spherest), intent(in) :: spheres0
c vdw parameters
      integer, intent(in) :: MAXTYV ! vdw types
      real, dimension(MAXTYV), intent(in) :: sra, srb !square roots of vdw parms
      integer, intent(in) :: MAXOR ! max orientations
      integer, intent(in) :: MAXCTR !!how many centers match, 4 is fine
      integer (kind=8), intent(inout) :: fdlig !ligand file handle

c     variables --
      type(db2) :: db2lig !ligand data stored here
      type(ligscoret) :: ligscore !saves many top poses
      type(ligscoret) :: ligscoreeach !saves one top pose for each flexible receptor combination
      type(atomscoret) :: atomscore !recalculate per atom scores
      type(matcht) :: match !stuff about matching
      character (len=80) molout !filename to save
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
      integer total_iter
      integer final_iter
      logical exists
      integer dock_status !uses status.h enums
      integer istat !ligand file status
      integer temp1, temp2 ! ligread2, for counting  ligc and db2c
      logical sp ! ligread2, skip_processing 
      integer tempsave, temprank !counter for multiple output
      integer cloudcount, cloudtotal !counter and overall # of times to run
      logical doing_cloud !whether or not the cloud is actually happening
      integer setstart, setend !controls which sets (complete confs) to score
      integer centrl !ligand seed (start) sphere
      integer centrr !receptor seed (start) sphere
      integer debug1 !temporary variable used in debugging loops
c variables for match_method choosing, control
      real curdislim !temporary variable, keeps track of current distance limit
      logical more_matches !true if we want to find more matches.
c these are the new degeneracy controls. the 2 hashes are the sets of matching
c spheres, one for rec, one lig. the count is how many pairs have been added.
      integer hash(MAXOR, MAXCTR), hashcount
      integer (kind=8) :: fdmol !output mol2.gz file handle
      integer :: outcount

c format lines for output
      character (len=*), parameter :: molexam = 
     &     '(i8,"  molecules examined on this run")'
      character (len=*), parameter :: outdockerr = 
     &     '(i6,1x,a16,i8,1x,i10,1x,f7.2,1x,a)'
      character (len=*), parameter :: outdockline = '(i6,1x,a16,1x,a16,
     &       1x,i8,1x,i10,1x,f7.2,1x,i3,1x,i9,1x,i9,1x,i6,3x,i3,2x,
     &       f7.2,1x,f7.2,1x,f7.2,f7.2,1x,f7.2,1x,f7.2,1x,f7.2,1x,f7.2,
     &       1x,f7.2,f10.2)'

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
      sp = .false.
      match%nmatch = 0 !initialize various things
      call allocate_match(match, maxor, OUTDOCK)
      iend = .false.
c     open output files
      molout = trim(options0%outfil)//'mol2.gz'
      write(OUTDOCK, '(a,a)') 'output file: ', molout
c     calculation of receptor sphere-sphere distances.
      call intdis(spheres0%nsphr, spheres0%spcorr, spheres0%disr, 
     &    match%dmaxr, MAXPTS)
      write(OUTDOCK, *) 'maximum receptor sphere-sphere distance',
     &    match%dmaxr
      call gzopen(fdmol, 'w', molout, istat) !open output ligand file
      !top of main section of OUTDOCK file
      write(OUTDOCK, '(a,a,a,a)') 
     & '  mol#           id_num     flexiblecode  matched    nscored  ',
     & '  time hac    setnum    matnum   rank cloud    elect +  gist',
     & ' +   vdW + psol +  asol + inter + rec_e + rec_d + r_hyd =',
     & '    Total'

      call doflush(OUTDOCK)
      final_iter = 0
      do while (.not. iend) !an actual loop
        total_iter = 0
c       --- read a ligand structure from the dbase ---
        call ligread2(db2lig, options0, 
     &      iend, tcorr, tcolor, tcount, fdlig,temp1,temp2,sp) !read one hierarchy 
        tcountorig = tcount !save the number of matching spheres here
        if (molct .eq. 0) then
          match%nmatch = 0 !initialize various things
          call allocate_match(match, maxor, OUTDOCK)
          dock_status = NOMATCH
        endif
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
          call get_time(time1) !time before this ligand is scored saved now
          ligscore%numscored = 0
          if (doing_cloud) then !add to tcorr, tcolor, tcount
            tcount = tcountorig !reset to before adding cloud matching spheres
            call add_cloud_spheres(cloudcount, tcorr, tcolor, tcount,
     &          db2lig)
          endif
          if (molct .eq. 1) then
            call intdis(tcount, tcorr, spheres0%disl, match%dmaxl,
     &          MAXPTS)
c           initialize variables for subgraph generation.
            match%nmatch = 0
            call allocate_match(match, maxor, OUTDOCK)
            dock_status = NOMATCH
            hashcount = 0 !reset the degeneracy counter to 0
            more_matches = .true. !always do at least once
            curdislim = options0%dislim !start at beginning no matter what

            do while (more_matches)
              do centrl = 1, tcount !use each ligand & receptor sphere as start
                do centrr = 1, spheres0%nsphr !seed point for generating spheres
c                 this is the call that generates orientations, which proceeds to 
c                 run through the hierarchy and scoring, etc
                  !match just puts things into coml, comr, rot now

                  call fullmatch(tcount, tcolor, centrl, centrr, 
     &              spheres0%scolor, spheres0%lgspcl, options0%cmatch, 
     &              curdislim, spheres0%disl, spheres0%disr,
c                   fix a bug here, jklyu, 2019.04.01
c     &             spheres0%spcorr, db2lig%coords, tcount, 
     &              spheres0%spcorr, tcorr, tcount, 
     &              spheres0%nsphr,
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
              endif
            enddo
          endif
c init these here???
          ligscore%savedcount = 0 !reset the number of poses saved
          if (options0%flexible_receptor .and. 
     &        options0%score_each_flex) then
            call reset_ligscore(ligscoreeach)
          endif
c part of clouds is to only score certain clusters of poses.. needs passed here
          if (doing_cloud) then !change setstart & setend
            setstart = db2lig%cluster_set_start(cloudcount)
            setend = db2lig%cluster_set_end(cloudcount)
          else !if not doing clouds
            setstart = 1
            setend = db2lig%total_sets !just do them all
          endif
          !next line actually calls scoring function now that matches are
          !all generated. no global variables used anymore.
          call calc_score_mol(dock_status, setstart, setend, 
     &        db2lig, options0, ligscore, ligscoreeach, grids0,
     &        vdwmap0, phimap0, recdes0, ligdes0, gist0, solvmap0,
     &        rec_des_r0, match, allminlimits, allmaxlimits,
     &        sra, srb, 
     &        MAXOR, db2lig%total_confs, db2lig%total_sets, 
     &        db2lig%total_atoms, db2lig%total_coords,
     &        MAXTYV) 
          call get_time(time2)
          telaps = time2 - time1
          if (dock_status .eq. NOMATCH) then
            write(OUTDOCK, outdockerr) molct, db2lig%refcod, 
     &          match%nmatch, ligscore%numscored, telaps, 'no_match'
            cycle !next ligand
          endif
c    --if no good poses of this ligand are found goto the next ligand --
          if (dock_status .eq. OUTSIDEGRIDS) then
            write(OUTDOCK, outdockerr) molct, db2lig%refcod, 
     &          match%nmatch, ligscore%numscored, telaps, 
     &          'outside_grids'
            cycle !next ligand
          else if (dock_status .eq. BUMPED) then 
            write(OUTDOCK, outdockerr) molct, db2lig%refcod, 
     &          match%nmatch, ligscore%numscored, telaps, 'bump'
            cycle !next ligand
          else if (dock_status .eq. CLASHES) then 
            write(OUTDOCK, outdockerr) molct, db2lig%refcod, 
     &          match%nmatch, ligscore%numscored, telaps, 'clashes'
            cycle !next ligand
          else if (dock_status .eq. NOTCHECKED) then 
            write(OUTDOCK, outdockerr) molct, db2lig%refcod, 
     &          match%nmatch, ligscore%numscored, telaps, 
     &          'clashes/notchecked'
            cycle !next ligand
          else if (dock_status .ne. ALLOKAY .or.
     &       ligscore%savedcount == 0 ) then
            write(OUTDOCK, outdockerr) molct, db2lig%refcod,
     &          match%nmatch, ligscore%numscored, telaps,
     &          'No viable poses.  Grids might be too small.  '
            cycle !next ligand
          endif
          if (dock_status .eq. ALLOKAY) then 
            if (options0%minimize .ne. 1) then
              do tempsave = 1, ligscore%savedcount
                write(OUTDOCK, outdockline) molct, db2lig%refcod,
     &            ligscore%pose_reccode(tempsave), 
     &            match%nmatch, ligscore%numscored, 
     &            telaps, db2lig%total_heavy_atoms, 
     &            ligscore%setsave(tempsave), 
     &            ligscore%orientsave(tempsave),
     &            tempsave, cloudcount, ligscore%pose_es(tempsave), 
     &            ligscore%pose_gi(tempsave), 
     &            ligscore%pose_vs(tempsave), 
     &            ligscore%pose_ps(tempsave), 
     &            ligscore%pose_as(tempsave), 
     &            ligscore%pose_is(tempsave), 
     &            ligscore%pose_rs(tempsave), 
     &            ligscore%pose_ds(tempsave), 
     &            ligscore%pose_hs(tempsave), 
     &            ligscore%pose_score(tempsave)
              enddo
            end if
            do outcount = 1, ligscore%savedcount
              if (ligscore%pose_score(outcount) .lt. 
     &            options0%save_limit .and. 
     &            ligscore%pose_score(outcount) .lt.
     &            options0%bmptotal) then
                call mol2write(options0, db2lig, ligscore, match,
     &              molct, cloudcount, MAXOR, fdmol, outcount, outcount,
     &              atomscore, grids0, vdwmap0, phimap0,
     &              recdes0, ligdes0, gist0, solvmap0, sra, srb,
     &              maxtyv, allminlimits, allmaxlimits, time1,
     &              total_iter)
                final_iter = final_iter + total_iter
              endif
            enddo
            temprank = ligscore%savedcount + 1 !start here
            if (options0%flexible_receptor .and. 
     &           options0%score_each_flex) then
              !write out to outdock again and mol2write
              do tempsave = 1, grids0%total_combinations !each receptor combo
                if (ligscoreeach%good_pose(tempsave)) then !if good pose
                  temprank = temprank + 1 !advance this counter
                  write(OUTDOCK, outdockline) molct, db2lig%refcod, 
     &                ligscoreeach%pose_reccode(tempsave), 
     &                match%nmatch, ligscore%numscored, 
     &                telaps, db2lig%total_heavy_atoms, 
     &                ligscoreeach%setsave(tempsave), 
     &                ligscoreeach%orientsave(tempsave),
     &                temprank, cloudcount, 
     &                ligscoreeach%pose_es(tempsave), 
     &                ligscoreeach%pose_gi(tempsave), 
     &                ligscoreeach%pose_vs(tempsave), 
     &                ligscoreeach%pose_ps(tempsave), 
     &                ligscoreeach%pose_as(tempsave), 
     &                ligscoreeach%pose_is(tempsave), 
     &                ligscoreeach%pose_rs(tempsave), 
     &                ligscoreeach%pose_ds(tempsave), 
     &                ligscoreeach%pose_hs(tempsave), 
     &                ligscoreeach%pose_score(tempsave)
c                 if (ligscore%pose_score(outcount) .lt. 
c    &                options0%save_limit) then
                  if (ligscoreeach%pose_score(tempsave) .lt. 
     &                options0%save_limit .and.
     &                ligscoreeach%pose_score(tempsave) .lt.
     &                options0%bmptotal) then
                    call mol2write(options0, db2lig, ligscoreeach, 
     &                  match, molct, cloudcount, MAXOR, fdmol, 
     &                  tempsave, temprank, atomscore, grids0, vdwmap0, 
     &                  phimap0, recdes0, ligdes0, gist0, solvmap0,
     &                  sra, srb, maxtyv, allminlimits, allmaxlimits,
     &                  time1, total_iter)
                    final_iter = final_iter + total_iter
                  endif
                endif
              enddo
            endif
          endif
        enddo !end of clouds loop
c       flush buffer to OUTDOCK so user can see progress 
        if (mod(molct, flush_int) .eq. 0) then
          call doflush(OUTDOCK)
        endif
      enddo
      if (iend) then
        !if (options0%minimize .gt. 0) then
        write (OUTDOCK, *) "total minimization steps = ", final_iter
        !endif
        write(OUTDOCK, *) "end of file encountered"
      endif
      call gzclose(fdmol, istat) !close ligand output file
      return
      end subroutine run_cluster_search

      end module cluster_search

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
