import sys
import os
import csv
import spikeinterface.core as si
import spikeinterface.extractors as se
import spikeinterface.preprocessing as sp
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import signal
import time
import studyparams
import matplotlib.pyplot as plt

subject = 'FD006'
date = '260311'
dataRoot = Path(studyparams.DATA_PATH)

nonStimEdata = {
    'lidocaine1'    :   '183148',
    'lidocaine2'    :   '184549'
}

edataToUse = {
    'site1'     :   ('160803','182402'),   # original insertion
    # 'site2'     :   ''
}

bdataToUse = {
    'site1'     :   '160754',   # original insertion
    # 'site2'     :   ''
}

def get_events_and_LFPs(recordingsEachSite, 
                          timeRange = [-0.5,1.5], 
                          highcut = 300, 
                          sampleRate = 30000,
                          downFactor = 1):

    downsampleRate = sampleRate//downFactor
    sampleRange = [1+int(t*downsampleRate) for t in timeRange]
    nSamplesToExtract = sampleRange[1]-sampleRange[0]

    bCoeff, aCoeff = signal.iirfilter(4, Wn=highcut, fs=downsampleRate, btype="low", ftype="butter")

    eventLockedLFP = np.empty((0,nSamplesToExtract,nChannels),dtype=np.int16)

    ### get traces ###
    nRecordingsThisSite = len(recordingsEachSite[site])
    channelStimEachTrial = []
    print(f'---- loading traces for {site} ----')
    for indr,recording in enumerate(recordingsEachSite[site]):
        data, stims = [recording[stream].get_traces() for stream in recording]

        stims = np.argmax(np.hstack([stims**2, np.ones((stims.shape[0],1))]),axis=1) - 32

        stimInds = np.nonzero(stims)[0]
        stimOnsetInds = np.concat([stimInds[:1],stimInds[1:][(np.diff(stimInds) > ISI*sampleRate)]])//downFactor
        channelStimEachTrial.extend(stims[stimOnsetInds])
        

        nTrials = len(stimOnsetInds)

        currEVLFPs = np.empty((nTrials,nSamplesToExtract,nChannels), dtype=np.int16)

        for indt, evSample in enumerate(stimOnsetInds):
            if evSample + sampleRange[0] < 0:
                break
            currEVLFPs[indt,:,:] = data[evSample+sampleRange[0]:evSample+sampleRange[1], :]

        eventLockedLFP = np.vstack([eventLockedLFP,currEVLFPs])

        if (100*indr/nRecordingsThisSite)%5 == 0:
            print(f"{(indr/nRecordingsThisSite):.0%} complete")
            
    eventLockedLFP = signal.filtfilt(bCoeff, aCoeff, eventLockedLFP, axis=0)

    return channelStimEachTrial,eventLockedLFP


# if __name__ == '__main__':

nChannels = 32
sampleRate = 30000
downsampleRate = 30000
ISI = 1.5
downFactor = sampleRate//downsampleRate

timeRange = [-0.5,1.5]
sampleRange = [int(t*downsampleRate)+1 for t in timeRange]
timeVec = np.arange(sampleRange[0], sampleRange[1])/downsampleRate
nSamplesToExtract = sampleRange[1]-sampleRange[0]

### get data filenames ###
edataFilenames = list(dataRoot.glob(f"**/*{subject}_{date}*/"))
bdataFilenames = list(dataRoot.glob(f"**/{subject}_stim_logs/*.csv"))

### get ephys times ###
ephysTimes = [str(f).split('_')[-1] for f in edataFilenames]
sortedEphysTimes = sorted(ephysTimes)
sortedEphysFiles = [edataFilenames[i] for i in np.argsort(ephysTimes)]

### load bdata ###
bdataAll = [pd.read_csv(f) for f in bdataFilenames]
bdataAll = pd.concat([df for df in bdataAll if len(df) > 0])

### load edata ###
recordingsEachSite = {}
concatEdataEachSite = {}
streamNames = ['RHS2000 amplifier channel', 
            #    'DC Amplifier channel', 
               'Stim channel']
streamKeys = {'RHS2000 amplifier channel':'amp',
            #   'DC Amplifier channel':'dc',
              'Stim channel':'stim'}

for site in edataToUse:
    startInd = sortedEphysTimes.index(edataToUse[site][0])
    stopInd = sortedEphysTimes.index(edataToUse[site][1])
    recordingsEachSite[site] = []
    for f in sortedEphysFiles[startInd:stopInd+1]:
        recordingThisFile = {}

        for stream in streamNames:
            recordingThisFile[streamKeys[stream]] = se.read_split_intan_files(f,stream_name=stream)

            if downFactor > 1 and stream != "Stim Channel":
                recordingThisFile[streamKeys[stream]] = sp.resample(sp.unsigned_to_signed(recordingThisFile[streamKeys[stream]]),downsampleRate)

        recordingsEachSite[site].append(recordingThisFile)

    channelStimEachTrial,eventLockedLFP = get_events_and_LFPs(recordingsEachSite)

    # eventLockedLFP = np.empty((0,nSamplesToExtract,nChannels),dtype=np.int16)

    # ### get traces ###
    # nRecordingsThisSite = len(recordingsEachSite[site])
    # print(f'---- loading traces for {site} ----')
    # for indr,recording in enumerate(recordingsEachSite[site]):
    # # for indr,recording in enumerate(recordingsEachSite[site][:1]):
    #     # data, stims = [signal.decimate(recording[stream].get_traces(),downFactor,axis=0) for stream in recording]
    #     data, stims = [recording[stream].get_traces() for stream in recording]

    #     stims = np.argmax(np.hstack([stims**2, np.ones((stims.shape[0],1))]),axis=1) - 32

    #     stimInds = np.nonzero(stims)[0]
    #     stimOnsetInds = np.concat([stimInds[:1],stimInds[1:][(np.diff(stimInds) > ISI*sampleRate)]])//downFactor
        

    #     nTrials = len(stimOnsetInds)

    #     currEVLFPs = np.empty((nTrials,nSamplesToExtract,nChannels), dtype=np.int16)

    #     for indt, evSample in enumerate(stimOnsetInds):
    #         if evSample + sampleRange[0] < 0:
    #             break
    #         currEVLFPs[indt,:,:] = data[evSample+sampleRange[0]:evSample+sampleRange[1], :]

    #     del data

    #     eventLockedLFP = np.vstack([eventLockedLFP,currEVLFPs])

    #     if indr%(nRecordingsThisSite//19) == 0:
    #         print(f"{(indr/nRecordingsThisSite):.0%} complete")


    # eventLockedLFP = signal.filtfilt(bCoeff, aCoeff, eventLockedLFP, axis=0)
        




