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
from scipy import signal,stats
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

subject = sys.argv[1]
date = studyparams.DATES[subject]
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
nonStimstimlog=studyparams.nonStimstimlog[subject]
edataToUse = studyparams.edataToUse[subject]
stimlogToUse = studyparams.stimlogToUse[subject]

bandsToUse = ['Delta','Theta','Alpha','Beta','Low_Gamma','High_Gamma','HFO']
saveDatFilename = {site:os.path.join(processedDataPath,f"{subject}_{date}_{site}_processed.hdf") for site in edataToUse}
combosaveDatFilename = {site:os.path.join(processedDataPath,f"combined_blocks_{subject}_{date}_{site}_processed.hdf") for site in edataToUse}

if __name__ == '__main__':
    sampleRate = studyparams.SAMPLE_RATE
    downsampleRate = studyparams.DOWNSAMPLE_RATE
    ISI = studyparams.ISI
    downFactor = sampleRate//downsampleRate
    highcut = studyparams.HIGHCUT
    nStimChansEachBlock = studyparams.N_STIM_CHANS_EACH_BLOCK

    timeRange = studyparams.TIMERANGE
    sampleRange = [int(t*downsampleRate)+1 for t in timeRange]
    timeVec = np.arange(sampleRange[0], sampleRange[1])/downsampleRate
    nSamplesToExtract = sampleRange[1]-sampleRange[0]

    ### get data filenames ###
    edataFilenames = list(dataRoot.glob(f"**/{subject}_data/*{date}*/"))
    stimlogFilenames = {site:list(dataRoot.glob(f"**/{subject}_stim_logs/*{stimlogToUse[site]}.csv")) for site in stimlogToUse}

    ### get ephys times ###
    ephysTimes = [str(f).split('_')[-1] for f in edataFilenames]
    sortedEphysTimes = sorted(ephysTimes)
    sortedEphysFiles = [edataFilenames[i] for i in np.argsort(ephysTimes)]

    ### load stimlog ###
    stimlogAll = {}
    for site in stimlogFilenames:
        dfs = [pd.read_csv(f) for f in sorted(stimlogFilenames[site])]
        stimlogAll[site] = pd.concat([df for df in dfs if len(df) > 0])

    ### load edata ###
    recordingsEachSite = {}
    concatEdataEachSite = {}
    streamNames = ['0', 
                '10', 
                '11']
    streamKeys = {'0':'amp',
                '10':'dc',
                '11':'stim'}
    stimParamsEachBlock = {}
    suptitleEachBlock = {}

    for site in edataToUse:
        startInd = sortedEphysTimes.index(edataToUse[site][0])
        stopInd = sortedEphysTimes.index(edataToUse[site][1])
        recordingsEachSite[site] = []
        stimlog = stimlogAll[site]
        edataFilesToUse = sortedEphysFiles[startInd:stopInd+1]
        if not (LOAD and os.path.exists(saveDatFilename[site])):
            for f in edataFilesToUse:
                recordingThisFile = {}

                for stream in streamNames:
                    try:
                        recordingThisFile[streamKeys[stream]] = se.read_split_intan_files(f,stream_id=stream)
                    except:
                        stimFile = Path(str(f).replace(f"{subject}_data",f"{subject}_stimdata"))
                        recordingThisFile[streamKeys[stream]] = se.read_split_intan_files(stimFile,stream_id=stream)
                    if downFactor > 1 and stream=='0':
                        recordingThisFile[streamKeys[stream]] = sp.resample(sp.unsigned_to_signed(recordingThisFile[streamKeys[stream]]),downsampleRate)

                recordingsEachSite[site].append(recordingThisFile)

        ### get events and LFPs ### 
        print(f'---- loading events and LFP for {site} ----')
        if LOAD and os.path.exists(saveDatFilename[site]):
            channelStimEachBlock,eventLockedLFP,baselineEachBlock = [np.stack(list(series),axis=0) for key,series in pd.read_hdf(saveDatFilename[site]).items() if 'layer' not in str(key).lower()]
            channelStimEachTrial = channelStimEachBlock.flatten()
        else:
            channelStimEachTrial,eventLockedLFP,baselineEachBlock = get_events_and_LFPs(recordingsEachSite,
                                                                                        site,
                                                                                        stimlogAll[site],
                                                                                        timeRange=timeRange,
                                                                                        downFactor=downFactor)
            
            channelStimEachBlock = channelStimEachTrial.reshape(eventLockedLFP.shape[:2])
            # channelStimEachBlock = stimlogAll[site]['Channel'].apply(lambda x: int(x[-2:])).reshape(eventLockedLFP.shape[:2])

        print('---- done extracting events and LFP ----')
        nBlocks,nTrialsEachBlock,nChannels,nSamples = eventLockedLFP.shape
    
        
        ### sort by channel stim ###
        sortingIndsEachBlock = np.argsort(channelStimEachBlock,axis = 1)
        sortedLFPs = np.array([eventLockedLFP[block,sortingIndsEachBlock[block],:,:] for block in range(nBlocks)])

        donutChans = studyparams.DONUT_ORDER
        

        ### combine stim channels to show all 16 ###
        combinedSortedLFPs = sortedLFPs.reshape(sortedLFPs.shape[0]//2,sortedLFPs.shape[1]*2,*sortedLFPs.shape[2:])
        stimParamsEachBlock[site] = [stimlogAll[site].iloc[block*combinedSortedLFPs.shape[1]] for block in range(combinedSortedLFPs.shape[0])]
        suptitleEachBlock[site] = [f"Stim: {''.join(currStimParams['Waveform'].split()[-2:])}, {currStimParams['Train_Dur_ms']}ms, {currStimParams['Freq_Hz']}Hz, {currStimParams['Base_Amp_uA']:.2f}uA" for currStimParams in stimParamsEachBlock[site]] 
            

        if MAKEFIGS and 1:
            print("---- plotting spectral power densities ----")
            SPDdir = os.path.join(outDir,'SpectralPowerDonut')
            BPdir = os.path.join(outDir,'BroadbandPowerDonut')
            if not os.path.exists(SPDdir):
                os.mkdir(SPDdir)
            if not os.path.exists(BPdir):
                os.mkdir(BPdir)

            for block in range(combinedSortedLFPs.shape[0]):
                currStimParams = stimParamsEachBlock[site][block]
                stimDur = currStimParams['Train_Dur_ms']/1000

                freqs,dataToPlot,fig,ax = plot_power_spectra(combinedSortedLFPs[block],timeVec,stimDur,freqRange=[0,200],nperseg=400)
                suptitleStr =  suptitleEachBlock[site][block]
                fig.suptitle(suptitleStr,fontsize=24, fontweight='bold');
                filename = f"{block:02d}_{''.join(currStimParams['Waveform'].split()[-2:])}_{currStimParams['Train_Dur_ms']}ms_{currStimParams['Freq_Hz']}Hz_{currStimParams['Base_Amp_uA']:.2f}uA_spectral_power.png"
                fig.savefig(os.path.join(SPDdir,filename),format='png',transparent=True);
                plt.close();
        


                freqs,dataToPlot,fig,ax = plot_broadband_power(combinedSortedLFPs[block],timeVec,stimDur,freqRange=[1.5,100])
                suptitleStr = f"Stim: {''.join(currStimParams['Waveform'].split()[-2:])}, {currStimParams['Train_Dur_ms']}ms, {currStimParams['Freq_Hz']}Hz, {currStimParams['Base_Amp_uA']:.2f}uA" 
                fig.suptitle(suptitleStr,fontsize=24, fontweight='bold');
                filename = f"{block:02d}_{''.join(currStimParams['Waveform'].split()[-2:])}_{currStimParams['Train_Dur_ms']}ms_{currStimParams['Freq_Hz']}Hz_{currStimParams['Base_Amp_uA']:.2f}uA_broadband_power.png"
                fig.savefig(os.path.join(BPdir,filename),format='png',transparent=True);
                plt.close();


        
        if MAKEFIGS and 1:
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
            for block in range(eventLockedLFP.shape[0]):
                if block%2==0:
                    shankChans = studyparams.SHANK_ORDER[::2]
                    chanDepths = studyparams.SHANK_DEPTHS[subject][site][::2]
                else:
                    shankChans = studyparams.SHANK_ORDER[1::2]
                    chanDepths = studyparams.SHANK_DEPTHS[subject][site][1::2]

                currStimParams = stimlogAll[site].iloc[block*40]
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

       
    
    
    print('---- estimating cortical layers ----')
    if 'OHSU' in subject:
        layerFile = edataFilenames[ephysTimes.index(nonStimEdata['whisk'])]
        layerRec = sp.resample(sp.unsigned_to_signed(se.read_split_intan_files(layerFile,stream_id="0")),downsampleRate)
        ttlRec = se.read_split_intan_files(layerFile,stream_id='5')   # get digital in data stream
        ttlData = ttlRec.get_traces().T[0].astype(int)  
        ttlOnsets = get_ttl_onsets(ttlData)//downFactor
        layerDat = layerRec.get_traces().T[studyparams.SHANK_ORDER,:]
        layerDat = np.array([layerDat[:,int(event+0.02*downsampleRate):int(event+0.04*downsampleRate)] for event in ttlOnsets])
        layersEachChan,csd_obj,meanCSDs = estimate_layers(np.mean(layerDat,axis=0))

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
        stimDur = int(stimParamsEachBlock['main'][block]['Train_Dur_ms'])/1000
        for layer in studyparams.LAYERS:
            tasks.append((
                combinedSortedLFPs[block,(layersEachChan==layer),:,:], 
                timeVec,
                stimDur,
                [1.5,100],
                100,
                downsampleRate,
                'cmor1.5-1.0'
            ))

    if not LOAD or 0:
        # Configure parallel processing
        n_workers = -2  # Use all but one core
        # n_workers = -1  # Use all cores
        powerEachBlockEachLayer = Parallel(n_jobs=n_workers,verbose=10)(
            delayed(calc_broadband_power)(*task) for task in tasks
        )

        powerEachBlockEachLayer = [{layer:powerEachBlockEachLayer[i*3+j]for j,layer in enumerate(studyparams.LAYERS)} for i in range(combinedSortedLFPs.shape[0])]
    else:
        powerEachBlockEachLayer = pd.read_hdf(combosaveDatFilename[site])['powerEachBlockEachLayer'].values

    # for layer in studyparams.LAYERS:
    #     powerEachBlockEachLayer[layer] = np.full((nBlocks,sum((layersEachChan == layer)),*eventLockedLFP.shape[-2:]),np.nan,dtype=float)
    #     for block in range(nBlocks):
    #         powerEachBlockEachLayer[layer][block,:,:,:] = calc_broadband_power(combinedSortedLFPs[block,(layersEachChan==layer),:,:], timeVec)

    meansEachBlock = {layer:[np.mean(powerEachBlockEachLayer[block][layer],axis=0) for block in range(combinedSortedLFPs.shape[0])] for layer in studyparams.LAYERS}
    stdsEachBlock = {layer:[np.std(powerEachBlockEachLayer[block][layer],axis=0) for block in range(combinedSortedLFPs.shape[0])] for layer in studyparams.LAYERS}

    # meansEachLayer = {layer:np.array([np.mean(combinedSortedLFPs[block,layersEachChan==layer,:,stimParamsEachBlock['main'][block]['Train_Dur_ms']-timeRange[0]*downsampleRate:],axis=-1) \
    #                                     for block in range(combinedSortedLFPs.shape[0])]) for layer in studyparams.LAYERS}
    
    meansEachLayer = {layer:np.array([np.mean(powerEachBlockEachLayer[block][layer][:,:,(timeVec>stimParamsEachBlock['main'][block]['Train_Dur_ms']/1000)],axis=-1) \
                                        for block in range(combinedSortedLFPs.shape[0])]) for layer in studyparams.LAYERS}
    
    if SAVEDAT:
            pd.DataFrame({
                    'channelStimsEachBlock': [channelStimEachBlock[block,:] for block in range(nBlocks)],
                    'lfpEachBlock': [eventLockedLFP[block,:,:,:] for block in range(nBlocks)],
                    'baselineEachBlock': [baselineEachBlock[block,:,:] for block in range(nBlocks)]
                }, dtype=object).to_hdf(saveDatFilename[site],key='df',complevel=4)
            
            pd.DataFrame({
                    'powerEachBlockEachLayer': [powerEachBlockEachLayer[block] for block in range(combinedSortedLFPs.shape[0])]
                }, dtype=object).to_hdf(combosaveDatFilename[site],key='df',complevel=4)
            
    # yrangeEachBlock = []
    # for block in range(combinedSortedLFPs.shape[0]):
    #     ymin = np.min(np.array([*meansEachBlock.values()])[:,block,:,(timeVec>0.25 + stimParamsEachBlock['main'][block]['Train_Dur_ms']/1000)])
    #     ymax = np.max(np.array([*meansEachBlock.values()])[:,block,:,(timeVec>0.25 + stimParamsEachBlock['main'][block]['Train_Dur_ms']/1000)])
    #     yrangeEachBlock.append([ymin,ymax])
    # yminEachBlock = [np.min(np.array([*meansEachBlock.values()])[:,block,:,(timeVec>stimParamsEachBlock['main'][block]['Train_Dur_ms'])]) for block in range(combinedSortedLFPs.shape[0])]
    # ymaxEachBlock = np.min(np.array([*meansEachBlock.values()]))
    simpleKrusk = []
    for block in range(combinedSortedLFPs.shape[0]):
        simpleKrusk.append([])
        for recChan in donutChans.flatten():
            simpleKrusk[block].append(stats.kruskal(*[meansEachLayer[layer][block][:,recChan] for layer in studyparams.LAYERS]))

    
    if MAKEFIGS and 1:
        layerColors = plt.cm.tab10(np.linspace(0,1,5))
        compDir = os.path.join(outDir,'LayerComparisons')
        if not os.path.exists(compDir):
            os.mkdir(compDir)
        for block in range(combinedSortedLFPs.shape[0]):
            fig,axs = make_donut_axes()
            for inda,ax in enumerate(axs.flatten()):
                for indl,layer in enumerate(studyparams.LAYERS):
                    ax.plot(timeVec,
                                meansEachBlock[layer][block][donutChans.flatten()[inda]], color = layerColors[indl],
                                label=layer if inda==0 else '')
            leg = fig.legend(loc='lower left', frameon=False, prop={'size':18,'weight':'bold'}, markerscale=4);
            plt.setp(leg.get_lines(),linewidth=4)
            fig.suptitle(suptitleEachBlock['main'][block])
            currStimParams = stimParamsEachBlock['main'][block]
            filename = f"{block:02d}_{''.join(currStimParams['Waveform'].split()[-2:])}_{currStimParams['Train_Dur_ms']}ms_{currStimParams['Freq_Hz']}Hz_{currStimParams['Base_Amp_uA']:.2f}uA_broadband_layer_comparison.png"
            fig.savefig(os.path.join(compDir,filename),format='png',transparent=True);
            plt.close();
        
        layersylab = 'Mean Evoked Resposne (uV)'
        layersxlab = 'Stim Amplitude (uA)'

        fig,axs = make_donut_axes()
        for inda,ax in enumerate(axs.flatten()):
            for indl,layer in enumerate(studyparams.LAYERS):
                ax.errorbar([0,10,20,40,80], np.mean(meansEachLayer[layer][[9,5,6,7,8],:,inda],axis=1),
                            np.std(meansEachLayer[layer][[9,5,6,7,8],:,inda],axis=1),color=layerColors[indl],label=layer if inda==0 else "")

        leg = fig.legend(loc='lower left', frameon=False, prop={'size':18,'weight':'bold'}, markerscale=4);
        plt.setp(leg.get_lines(),linewidth=4)
        fig.suptitle('Single Pulse Response vs Amplitude')
        currStimParams = stimParamsEachBlock['main'][block]
        fig.supylabel(layersylab,fontsize=24)
        fig.supxlabel(layersxlab,fontsize=24)
        fig.subplots_adjust(wspace=0.6) 
        filename = f"Single_pulse_mean_broadband_layer_comparison.png"
        fig.savefig(os.path.join(compDir,filename),format='png',transparent=True);
        plt.close();

        fig,axs = make_donut_axes()
        for inda,ax in enumerate(axs.flatten()):
            for indl,layer in enumerate(studyparams.LAYERS):
                ax.errorbar([0,1,2,4,8], np.mean(meansEachLayer[layer][[4,0,1,2,3],:,inda],axis=1),
                        np.std(meansEachLayer[layer][[4,0,1,2,3],:,inda],axis=1),color=layerColors[indl],label=layer if inda==0 else "")

        leg = fig.legend(loc='lower left', frameon=False, prop={'size':18,'weight':'bold'}, markerscale=4);
        plt.setp(leg.get_lines(),linewidth=4)
        fig.suptitle('Pulse Train Response vs Amplitude')
        currStimParams = stimParamsEachBlock['main'][block]
        fig.supylabel(layersylab,fontsize=24)
        fig.supxlabel(layersxlab,fontsize=24)
        fig.subplots_adjust(wspace=0.6)
        filename = f"Pulse_Train_mean_broadband_layer_comparison.png"
        fig.savefig(os.path.join(compDir,filename),format='png',transparent=True);
        plt.close();

        

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

        #         ### trials zero-amplitude stims don't show up in the intan traces, so get get that from the stimlog timestamps ###
        #         indt = eventLockedLFP.shape[0]
        #         stimTimes = stimlog[indt:indt+40]['Timestamp'].apply(lambda x: (datetime.strptime(x.split()[-1],"%H:%M:%S.%f") \
        #                                                                         - datetime(1900,1,1)).total_seconds()).values

        #         stimTimes = ((30 + stimTimes - stimTimes[0]))
        #         stimChans = stimlog[indt:indt+40]['Channel'].apply(lambda x: int(x[2:])).values
        #         stimOnsetInds = (downsampleRate*stimTimes).astype(int)

        #     else:
        #         stimInds = np.nonzero(stims)[0]
        #         stimOnsetInds = np.concat([stimInds[:1],stimInds[1:][(np.diff(stimInds) > 0.5*ISI*sampleRate)]])//downFactor
        #         stimChans = stims[stimOnsetInds]+32


        #     channelStimEachTrial.extend(stimChans)
        #     currStimDur = stimlog['Train_Dur_ms'][eventLockedLFP.shape[0]]

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


if MAKEFIGS:
    use('qtagg')
    plt.close()
