#!/bin/bash 

DIRNAME="/icarus/data/users/amogan/cali_ntuples_for_diffusion/"
FILETEXT="cali_ntuple_corsika_20kEvts_elifetime.root"
RUNTYPE="XX"
PLANENUM=2
PLOTNAME="plot.pdf"

make 
./WaveformStudy $DIRNAME $FILETEXT $RUNTYPE $PLANENUM $PLOTNAME
