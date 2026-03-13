import sys
import os
import csv
import spikeinterface.core as si
import spikeinterface.extractors as se
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import signal
import time
import studyparams
import matplotlib.pyplot as plt


from intanutil.header import (read_header,
                              header_to_result)
from intanutil.data import (calculate_data_size,
                            read_all_data_blocks,
                            check_end_of_file,
                            parse_data,
                            data_to_result)
from intanutil.filter import apply_notch_filter

subject = 'FD006'
date = '260311'
dataRoot = Path(studyparams.DATA_PATH)

nonStimEdata = {
    'lidocaine1'    :   '183148',
    'lidocaine2'    :   '184549'
}

edataToUse = {
    'site1'     :   ('160803','182602'),   # original insertion
    # 'site2'     :   ''
}

bdataToUse = {
    'site1'     :   '160754',   # original insertion
    # 'site2'     :   ''
}

# if __name__ == '__main__':

nChannels = 32
sampleRate = 30000
timeRange = [-0.5,1.5]
sampleRange = [int(t*sampleRate) for t in timeRange]
timeVec = np.arange(sampleRange[0], sampleRange[1])/sampleRate
nSamplesToExtract = sampleRange[1]-sampleRange[0]
highcut = 300
bCoeff, aCoeff = signal.iirfilter(4, Wn=highcut, fs=sampleRate, btype="low", ftype="butter")

### get data filenames ###
edataFilenames = list(dataRoot.glob(f"**/*{subject}*.rhs"))
bdataFilenames = list(dataRoot.glob(f"**/{subject}_stim_logs/*.csv"))

### get ephys times ###
ephysTimes = [str(f)[-10:-4] for f in edataFilenames]
sortedEphysTimes = sorted(ephysTimes)
sortedEphysFiles = [edataFilenames[i] for i in np.argsort(ephysTimes)]

### load bdata ###
bdataAll = [pd.read_csv(f) for f in bdataFilenames]
bdataAll = pd.concat([df for df in bdataAll if len(df) > 0])

### load edata ###
recordingsEachSite = {}
concatEdataEachSite = {}
streamNames = ['RHS2000 amplifier channel', 'DC Amplifier channel', 'Stim channel']
streamKeys = {'RHS2000 amplifier channel':'amp','DC Amplifier channel':'dc','Stim channel':'stim'}
for site in edataToUse:
    startInd = sortedEphysTimes.index(edataToUse[site][0])
    stopInd = sortedEphysTimes.index(edataToUse[site][1])
    recordingsEachSite[site] = [{streamKeys[stream]:se.read_intan(f,stream_name=stream) for stream in streamNames} for f in sortedEphysFiles[startInd:stopInd+1]] 
    # concatEdataEachSite[site] = si.concatenate_recordings([se.read_intan(str(f)) for f in sortedEphysFiles[startInd:stopInd+1]])
    # concatEdataEachSite[site] = {streamKeys[stream]:si.concatenate_recordings(recordingsEachSite[site][stream]) for stream in streamNames}


    eventLockedLFP = np.empty((0,nSamplesToExtract,nChannels),dtype=np.int16)
    ### get traces ###
    for recording in recordingsEachSite[site]:
        data, dc, stims = [recording[stream].get_traces() for stream in recording]

        stimOnsetInds = np.nonzero(np.argmax(stims,axis=1))[0]
        nTrials = len(stimOnsetInds)

        currEVLFPs = np.empty((nTrials,nSamplesToExtract,nChannels), dtype=np.int16)

        for indt, evSample in enumerate(stimOnsetInds):
            currEVLFPs[indt,:,:] = data[evSample+sampleRange[0]:evSample+sampleRange[1], :]

        eventLockedLFP = np.vstack([eventLockedLFP,currEVLFPs])
            


    eventlockedLFP = signal.filtfilt(bCoeff, aCoeff, eventlockedLFP, axis=0)
        




