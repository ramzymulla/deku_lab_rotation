import sys
import os
import spikeinterface.core as si
import spikeinterface.extractors as se
import spikeinterface.preprocessing as sp
from matplotlib import use,rcParams
from joblib import Parallel,delayed
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import signal
import studyparams
from studyutils import *
import matplotlib.pyplot as plt



LOAD = False
SAVEDAT = False
MAKEFIGS = False

for arg in sys.argv:
    if arg == 'load':
        LOAD = True
    elif arg == 'savedat':
        SAVEDAT = True
    elif arg == 'makefigs':
        MAKEFIGS = True
        use('agg')
        COLOR = 'white'  
        rcParams['text.color'] = COLOR         # General text color
        rcParams['axes.labelcolor'] = COLOR    # Axis label color
        rcParams['xtick.color'] = COLOR        # X-axis tick color
        rcParams['ytick.color'] = COLOR        # Y-axis tick color
        rcParams['axes.edgecolor'] = COLOR

subject = 'OHSU2'
date = '260320'
dataRoot = Path(studyparams.DATA_PATH)
outRoot = studyparams.OUTPUT_PATH
if not os.path.exists(outRoot):
    os.mkdir(outRoot)
outDir = os.path.join(outRoot,subject)
if not os.path.exists(outDir):
    os.mkdir(outDir)

processedDataPath = os.path.join(outDir,"FigData")
if not os.path.exists(processedDataPath):
    os.mkdir(processedDataPath)

mpd_graphsDir = os.path.join(outDir,'multiband_donut_figs')
if not os.path.exists(mpd_graphsDir):
    os.mkdir(mpd_graphsDir)

nonStimEdata = studyparams.nonStimEdata[subject]
nonStimBdata=studyparams.nonStimBdata[subject]
edataToUse = studyparams.edataToUse[subject]
bdataToUse = studyparams.bdataToUse[subject]

bandsToUse = ['Delta','Theta','Alpha','Beta','Low_Gamma','High_Gamma','HFO']
saveDatFilename = {site:os.path.join(processedDataPath,f"{subject}_{date}_{site}_processed.hdf") for site in edataToUse}

if __name__ == '__main__':

    nChannels = 32
    sampleRate = 30000
    downsampleRate = 1000
    ISI = 1.5
    downFactor = sampleRate//downsampleRate
    highcut = 300
    nStimChansEachBlock = 8

    timeRange = [-1,2]
    sampleRange = [int(t*downsampleRate)+1 for t in timeRange]
    timeVec = np.arange(sampleRange[0], sampleRange[1])/downsampleRate
    nSamplesToExtract = sampleRange[1]-sampleRange[0]

    ### get data filenames ###
    edataFilenames = list(dataRoot.glob(f"**/*{subject}_{date}*/"))
    bdataFilenames = {site:list(dataRoot.glob(f"**/{subject}_stim_logs/*{bdataToUse[site]}.csv")) for site in bdataToUse}

    ### get ephys times ###
    ephysTimes = [str(f).split('_')[-1] for f in edataFilenames]
    sortedEphysTimes = sorted(ephysTimes)
    sortedEphysFiles = [edataFilenames[i] for i in np.argsort(ephysTimes)]

    ### load bdata ###
    bdataAll = {}
    for site in bdataFilenames:
        dfs = [pd.read_csv(f) for f in sorted(bdataFilenames[site])]
        bdataAll[site] = pd.concat([df for df in dfs if len(df) > 0])

    ### load edata ###
    recordingsEachSite = {}
    concatEdataEachSite = {}
    streamNames = ['RHS2000 amplifier channel', 
                'DC Amplifier channel', 
                'Stim channel']
    streamKeys = {'RHS2000 amplifier channel':'amp',
                'DC Amplifier channel':'dc',
                'Stim channel':'stim'}

    for site in edataToUse:
        startInd = sortedEphysTimes.index(edataToUse[site][0])
        stopInd = sortedEphysTimes.index(edataToUse[site][1])
        recordingsEachSite[site] = []
        bdata = bdataAll[site]
        edataFilesToUse = sortedEphysFiles[startInd:stopInd+1]
        if not LOAD:
            for f in edataFilesToUse:
                recordingThisFile = {}

                for stream in streamNames:
                    recordingThisFile[streamKeys[stream]] = se.read_split_intan_files(f,stream_name=stream)

                    if downFactor > 1 and 'amp' in stream:
                        recordingThisFile[streamKeys[stream]] = sp.resample(sp.unsigned_to_signed(recordingThisFile[streamKeys[stream]]),downsampleRate)

                    recordingsEachSite[site].append(recordingThisFile)

        ### get events and LFPs ### 
        print(f'---- loading events and LFP for {site} ----')
        if LOAD and os.path.exists(saveDatFilename[site]):
            channelStimEachBlock,eventLockedLFP,baselineEachBlock = [np.stack(list(series),axis=0) for _,series in pd.read_hdf(saveDatFilename[site]).items()]
            channelStimEachTrial = channelStimEachBlock.flatten()
        else:
            channelStimEachTrial,eventLockedLFP,baselineEachBlock = get_events_and_LFPs(recordingsEachSite,
                                                                                        site,
                                                                                        bdataAll[site],
                                                                                        timeRange=timeRange,
                                                                                        downFactor=downFactor)
            
            channelStimEachBlock = channelStimEachTrial.reshape(eventLockedLFP.shape[:2])
            # channelStimEachBlock = bdataAll[site]['Channel'].apply(lambda x: int(x[-2:])).reshape(eventLockedLFP.shape[:2])

        print('---- done extracting events and LFP ----')
        nBlocks,nTrialsEachBlock,nChannels,nSamples = eventLockedLFP.shape

        
        ### sort by channel stim ###
        sortingIndsEachBlock = np.argsort(channelStimEachBlock,axis = 1)
        sortedLFPs = np.array([eventLockedLFP[block,sortingIndsEachBlock[block],:,:] for block in range(nBlocks)])

        donutChans = studyparams.DONUT_ORDER
        

        ### combine stim channels to show all 16 ###
        combinedSortedLFPs = sortedLFPs.reshape(sortedLFPs.shape[0]//2,sortedLFPs.shape[1]*2,*sortedLFPs.shape[2:])


        if MAKEFIGS and 1:
            print("---- plotting spectral power densities ----")
            SPDdir = os.path.join(outDir,'SpectralPowerDonut')
            BPdir = os.path.join(outDir,'BroadbandPowerDonut')
            if not os.path.exists(SPDdir):
                os.mkdir(SPDdir)
            if not os.path.exists(BPdir):
                os.mkdir(BPdir)

            for block in range(32):
                currStimParams = bdataAll[site].iloc[block*combinedSortedLFPs.shape[1]]
                stimDur = currStimParams['Train_Dur_ms']/1000

                freqs,dataToPlot,fig,ax = plot_power_spectra(combinedSortedLFPs[block],timeVec,stimDur,freqRange=[0,200],nperseg=500)
                suptitleStr = f"Stim: {''.join(currStimParams['Waveform'].split()[-2:])}, {currStimParams['Train_Dur_ms']}ms, {currStimParams['Freq_Hz']}Hz, {currStimParams['Base_Amp_uA']:.2f}uA" 
                fig.suptitle(suptitleStr,fontsize=24, fontweight='bold');
                filename = f"{block:02d}_{''.join(currStimParams['Waveform'].split()[-2:])}_{currStimParams['Train_Dur_ms']}ms_{currStimParams['Freq_Hz']}Hz_{currStimParams['Base_Amp_uA']:.2f}uA_spectral_power.png"
                fig.savefig(os.path.join(SPDdir,filename),format='png',transparent=True);
                plt.close();
        


                # freqs,dataToPlot,fig,ax = plot_broadband_power(combinedSortedLFPs[block],timeVec,stimDur,freqRange=[0,200])
                # suptitleStr = f"Stim: {''.join(currStimParams['Waveform'].split()[-2:])}, {currStimParams['Train_Dur_ms']}ms, {currStimParams['Freq_Hz']}Hz, {currStimParams['Base_Amp_uA']:.2f}uA" 
                # fig.suptitle(suptitleStr,fontsize=24, fontweight='bold');
                # filename = f"{block:02d}_{''.join(currStimParams['Waveform'].split()[-2:])}_{currStimParams['Train_Dur_ms']}ms_{currStimParams['Freq_Hz']}Hz_{currStimParams['Base_Amp_uA']:.2f}uA_broadband_power.png"
                # fig.savefig(os.path.join(BPdir,filename),format='png',transparent=True);
                # plt.close();


        
        if MAKEFIGS and 0:
            print('---- separating into LFP bands ----')
            ### extract LFP bands ###
            bandedBaselines = [extract_lfp_bands(baselineEachBlock[block,:,:],downsampleRate) for block in range(nBlocks)]
            bandedLFPs = [extract_lfp_bands(sortedLFPs[block,:,:,:],downsampleRate) for block in range(nBlocks)]
            # for band in bandedLFPs:
            #     avgBL = np.mean(bandedBaselines[band],axis=1)
            #     bandedLFPs[band] = np.prod([bandedLFPs,avgBL],axis=)
            

            print('---- calculating average bandedLFPs ----')
            ### average by stim type ###
            avgBandedLFPs = [{band:np.zeros((nStimChansEachBlock,*eventLockedLFP.shape[2:])) for band in bandedLFPs[block]} for block in range(nBlocks)]
            # avgBandedBaselines = [{band:np.zeros((nStimChansEachBlock,*eventLockedLFP.shape[2:])}]
            for block,spectra in enumerate(bandedLFPs):
                for band in spectra:
                    lfp = spectra[band]
                    for chan in range(8):
                        avgBandedLFPs[block][band][chan,:,:] = np.mean(lfp[chan*5:chan*5+5,:,:],axis=0)
            print('---- extracting spectral power ----')
            bandPowerEachBlock = []
            avgBandPowerEachBlock = []
            baselinePowerEachBlock = []
            for block in range(64):
                if block%2==0:
                    shankChans = studyparams.SHANK_ORDER[::2]
                    chanDepths = studyparams.SHANK_DEPTHS[site][::2]
                else:
                    shankChans = studyparams.SHANK_ORDER[1::2]
                    chanDepths = studyparams.SHANK_DEPTHS[site][1::2]

                currStimParams = bdataAll[site].iloc[block*40]
                blockDir = os.path.join(mpd_graphsDir,f"{''.join(currStimParams['Waveform'].split()[-2:])}_{currStimParams['Train_Dur_ms']}ms_{currStimParams['Freq_Hz']}Hz_{currStimParams['Base_Amp_uA']:.2f}uA")
                if MAKEFIGS and (not os.path.exists(blockDir)):
                    os.mkdir(blockDir)

                # bandedLFPs[block] = {band:np.transpose(bandedLFPs[block][band],axes=[0,2,1]) for band in bandedLFPs[block]}         # reshape to (nTrials,nChannels,nSamples)
                bandPowerEachBlock.append({band:np.zeros_like(bandedLFPs[block][band]) for band in bandedLFPs[block]})              # shape (nTrials,nChannels,nSamples)
                avgBandPowerEachBlock.append({band:np.zeros_like(avgBandedLFPs[block][band]) for band in avgBandedLFPs[block]})     # shape (nStimChansEachBlock,nChannels,nSamples)
                baselinePowerEachBlock.append({band:np.zeros_like(bandedBaselines[block][band]) for band in bandedBaselines[block]})    # shape (nChannels,nSamplesBaseline)
                for stimChan in range(nStimChansEachBlock):
                    for band in bandedLFPs[block]:
                        bandPowerEachBlock[block][band][5*stimChan: 5*stimChan + 5,:,:] = np.abs(signal.hilbert(bandedLFPs[block][band][stimChan,:,:]))
                        avgBandPowerEachBlock[block][band][stimChan,:,:] = np.mean(bandPowerEachBlock[block][band][5*stimChan: 5*stimChan + 5,:,:],axis=0)
                        baselinePowerEachBlock[block][band] = np.abs(signal.hilbert(bandedBaselines[block][band]))

                    # plot_radial_multiband_power({band:np.abs(signal.hilbert(avgBandedLFPs[block][band][stimChan,donutChans.flatten(),:].reshape(2,8,-1))) for band in bandsToUse},timeVec)
                    
                    
                    fig = plot_radial_multiband_power({band:avgBandPowerEachBlock[block][band][stimChan,donutChans.flatten(),:].reshape(*donutChans.shape,-1) for band in bandsToUse},
                                                timeVec);

                    # fig = plot_radial_multiband_power({band:avgBandPowerEachBlock[block][band][stimChan,donutChans.flatten(),:].reshape(*donutChans.shape,-1) for band in bandsToUse},
                    #                             timeVec, baselineDict={band:baselinePowerEachBlock[block][band][stimChan,donutChans.flatten()].reshape(*donutChans.shape,-1) for band in bandsToUse});
                    
                    plt.gca();
                    suptitleStr = f"Stim: {shankChans[stimChan]} ({chanDepths[stimChan]} um from pia), {''.join(currStimParams['Waveform'].split()[-2:])}, {currStimParams['Train_Dur_ms']}ms, {currStimParams['Freq_Hz']}Hz, {currStimParams['Base_Amp_uA']:.2f}uA" 
                    fig.suptitle(suptitleStr,fontsize=24, fontweight='bold');
                    # fig.subplots_adjust(hspace=0.4)
                    filename = f"{chanDepths[stimChan]:04d}um_channel{shankChans[stimChan]:02d}_multiband_power_block{block}.png"
                    fig.savefig(os.path.join(blockDir,filename),format='png',transparent=True);
                    plt.close();

                if block%10 ==0:
                    print(f"plotting block {block}/{nBlocks}")

        if SAVEDAT:
                pd.DataFrame({
                    'channelStimsEachBlock': [channelStimEachBlock[block,:] for block in range(nBlocks)],
                    'lfpEachBlock': [eventLockedLFP[block,:,:,:] for block in range(nBlocks)],
                    'baselineEachBlock': [baselineEachBlock[block,:,:] for block in range(nBlocks)]
                }, dtype=object).to_hdf(saveDatFilename[site],key='df',complevel=4)
    
    
    print('---- estimating cortical layers ----')
    if 'OHSU' in subject:
        layerFile = edataFilenames[ephysTimes.index(nonStimEdata['whisk'])]
        layerRec = sp.resample(sp.unsigned_to_signed(se.read_split_intan_files(layerFile,stream_id="0")),downsampleRate)
        ttlRec = se.read_split_intan_files(layerFile,stream_id='5')     # get digital in data stream
        ttlOnsets = get_ttl_onsets(ttlRec.get_traces().T[0])//downFactor
        layerDat = np.array([layerRec.get_traces().T[:,int(event+0.08*downsampleRate):int(event+0.2*downsampleRate)] for event in ttlOnsets])
        layersEachChan,csd_obj = estimate_layers(np.mean(layerDat,axis=0))

    else:
        layersEachChan = np.array(['deep', 'deep', 'deep', 'deep', 'granule', 'granule', 'granule',
            'superficial', 'superficial', 'superficial', 'superficial',
                'superficial', 'superficial', 'superficial', 'superficial',
                'superficial'], dtype='<U16')

    
    print('---- comparing layers ----')
    powerEachBlockEachLayer = {}
    timeVec = np.arange(sampleRange[0], sampleRange[1])/downsampleRate
    nStimChans = len(studyparams.SHANK_ORDER)
    stimChanIndOrder = np.stack([np.arange(nStimChans//2), np.arange(nStimChans//2, nStimChans)]).ravel('F')
    stimChanIndOrder = np.concat([np.arange(i*5,i*5+5) for i in stimChanIndOrder])
    layersEachChan = np.concat([[i]*5 for i in layersEachChan])

    # Prepare task list
    tasks = []
    for block in range(combinedSortedLFPs.shape[0]):
        for layer in studyparams.LAYERS:
            tasks.append((
                combinedSortedLFPs[block,(layersEachChan==layer),:,:], timeVec
            ))

    # Configure parallel processing
    n_workers = -2  # Use all but one core
    # n_workers = -1  # Use all cores
    powerEachBlockEachLayer = Parallel(n_jobs=n_workers,verbose=10)(
        delayed(calc_broadband_power)(*task) for task in tasks
    )

    powerEachBlockEachLayer = [{layer:powerEachBlockEachLayer[i*3+j]for j,layer in enumerate(studyparams.LAYERS)} for i in range(combinedSortedLFPs.shape[0])]

    # for layer in studyparams.LAYERS:
    #     powerEachBlockEachLayer[layer] = np.full((nBlocks,sum((layersEachChan == layer)),*eventLockedLFP.shape[-2:]),np.nan,dtype=float)
    #     for block in range(nBlocks):
    #         powerEachBlockEachLayer[layer][block,:,:,:] = calc_broadband_power(combinedSortedLFPs[block,(layersEachChan==layer),:,:], timeVec)

    meansEachBlock = {layer:[np.mean(powerEachBlockEachLayer[block][layer],axis=0)] for block in range(combinedSortedLFPs.shape[0]) for layer in studyparams.LAYERS}
    stdsEachBlock = {layer:[np.std(powerEachBlockEachLayer[block][layer],axis=0)] for block in range(combinedSortedLFPs.shape[0]) for layer in studyparams.LAYERS}

    # downsampleRate = sampleRate//downFactor
    # sampleRange = [1+int(t*downsampleRate) for t in timeRange]
    # nSamplesToExtract = sampleRange[1]-sampleRange[0]

    # bCoeff, aCoeff = signal.iirfilter(4, Wn=highcut, fs=downsampleRate, btype="low", ftype="butter")

    # eventLockedLFP = np.empty((0,nSamplesToExtract,nChannels),dtype=np.int16)
    # channelStimEachTrial = []

    # ### get traces ###
    # nRecordingsThisSite = len(recordingsEachSite[site])
    
    # print(f'---- loading events and LFP for {site} ----')
    # for indr,recording in enumerate(recordingsEachSite[site]):
    #     stims = recording['stim'].get_traces()
    #     nChannels = stims.shape[1]
    #     stims = np.argmax(np.hstack([stims**2, np.ones((stims.shape[0],1))]),axis=1) - 32

    #     if np.sum(stims) == 0:

    #         ### trials zero-amplitude stims don't show up in the intan traces, so get get that from the bdata timestamps ###
    #         indt = eventLockedLFP.shape[0]
    #         stimTimes = bdata[indt:indt+40]['Timestamp'].apply(lambda x: (datetime.strptime(x.split()[-1],"%H:%M:%S.%f") \
    #                                                                         - datetime(1900,1,1)).total_seconds()).values
            
    #         stimTimes = ((30 + stimTimes - stimTimes[0]))
    #         stimChans = bdata[indt:indt+40]['Channel'].apply(lambda x: int(x[2:])).values
    #         stimOnsetInds = (downsampleRate*stimTimes).astype(int)

    #     else:
    #         stimInds = np.nonzero(stims)[0]
    #         stimOnsetInds = np.concat([stimInds[:1],stimInds[1:][(np.diff(stimInds) > 0.5*ISI*sampleRate)]])//downFactor
    #         stimChans = stims[stimOnsetInds]+32


    #     channelStimEachTrial.extend(stimChans)
    #     currStimDur = bdata['Train_Dur_ms'][eventLockedLFP.shape[0]]

    #     nTrials = len(stimOnsetInds)
    #     if nTrials !=40:
    #         print(f"Error, {nTrials} stims detected for recording #{indr} ({edataFilesToUse[indr].name})")
    #         continue

    #     currEVLFPs = np.empty((nTrials,nSamplesToExtract,nChannels), dtype=np.int16)


    #     data = sp.remove_artifacts(sp.notch_filter(sp.unsigned_to_signed(recording['amp']),60),
    #                                 stimOnsetInds,ms_before=25,ms_after=currStimDur).get_traces()

    #     for indt, evSample in enumerate(stimOnsetInds):
    #         if evSample + sampleRange[0] < 0:
    #             break
    #         currEVLFPs[indt,:,:] = data[evSample+sampleRange[0]:evSample+sampleRange[1], :]

    #     eventLockedLFP = np.vstack([eventLockedLFP,currEVLFPs])

    #     if (indr)%10 == 0:
    #         print(f"{indr}/{nRecordingsThisSite} recordings processed")
    # print('done extracting events and LFP')
    # eventLockedLFP = signal.filtfilt(bCoeff, aCoeff, eventLockedLFP, axis=0)

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
        




