import numpy as np
import sys
import os
import matplotlib.pyplot as plt
import pandas as pd
from scipy import signal
from datetime import datetime
import spikeinterface.core as si
import spikeinterface.extractors as se
import spikeinterface.preprocessing as sp
from matplotlib import use,rcParams
from pathlib import Path
from scipy.ndimage import gaussian_filter1d
import pywt
import studyparams
import quantities as pq
import neo
from elephant.current_source_density import icsd,estimate_csd

def get_ttl_onsets(ttldata):
    return np.nonzero(np.diff(ttldata)==-1)[0]

def get_events_and_LFPs(recordingsEachSite, site,bdata,
                          timeRange = [-0.5,1.5], 
                          highcut = 300, 
                          sampleRate = 30000,
                          downFactor = 1,
                          ISI = 2.5,
                          nChannels = 32,
                          baselineDur = 30):

    downsampleRate = sampleRate//downFactor ################################
    sampleRange = [1+int(t*downsampleRate) for t in timeRange]
    nSamplesToExtract = sampleRange[1]-sampleRange[0]
    nRecordingsThisSite = len(recordingsEachSite[site])
    nTrialsEachBlock = len(bdata)//nRecordingsThisSite


    if downFactor !=1:
        bCoeff, aCoeff = signal.iirfilter(4, Wn=highcut, fs=downsampleRate, btype="low", ftype="butter")

    eventLockedLFP = np.empty((nRecordingsThisSite,nTrialsEachBlock,nSamplesToExtract,nChannels),dtype=np.int16)
    baselineEachBlock = np.empty((nRecordingsThisSite,downsampleRate*30,nChannels),dtype=np.int16)
    channelStimEachTrial = []

    ### get traces ###
    for indr,recording in enumerate(recordingsEachSite[site]):
        stims = recording['stim'].get_traces()
        nChannels = stims.shape[1]
        
        if np.sum(np.abs(stims)) == 0:
            
            # ### trials zero-amplitude stims don't show up in the intan traces, so get get that from the bdata timestamps ###
            indt = indr*nTrialsEachBlock
            stimTimes = bdata[indt:indt+nTrialsEachBlock]['Timestamp'].apply(lambda x: (datetime.strptime(x.split()[-1],"%H:%M:%S.%f") \
                                                                            - datetime(1900,1,1)).total_seconds()).values
            
            stimTimes = ((baselineDur + stimTimes - stimTimes[0]))
            stimChans = bdata[indt:indt+nTrialsEachBlock]['Channel'].apply(lambda x: int(x[2:])).values
            stimOnsetInds = (sampleRate*stimTimes).astype(int)//downFactor

            # dc = recording['dc'].get_traces()
            # sumDC = np.sum(dc,axis=1)
            # medsumDC = np.median(sumDC)
            # prop=1.01
            # stimOnsetInds = np.nonzero((sumDC>prop*medsumDC))[0]//downFactor
            
            
            # if len(stimOnsetInds) != 40:
            #     for prop in np.linspace(1,np.max(sumDC)/np.median(sumDC),500)[1:]:
            #         stimOnsetInds = np.nonzero((sumDC>prop*medsumDC))[0]//downFactor
            #         if len(stimOnsetInds) == 40:
            #             break
                    
        else:
            stims = np.argmax(np.hstack([np.abs(stims), np.ones((stims.shape[0],1))]),axis=1) - nChannels
            stimInds = np.nonzero(stims)[0]
            stimOnsetInds = np.concat([stimInds[:1],stimInds[1:][(np.diff(stimInds) > 0.5*ISI*sampleRate)]])//downFactor
            stimChans = stims[stimOnsetInds*downFactor]+nChannels

        
        channelStimEachTrial.extend(stimChans)
        

        nTrials = len(stimOnsetInds)
        currStimDur = bdata['Train_Dur_ms'][indr*nTrialsEachBlock]

        if nTrials !=40:
            print(f"Error, {nTrials} stims detected for recording #{indr} ({recording['amp'].name})")
            continue

        currEVLFPs = np.empty((nTrials,nSamplesToExtract,nChannels), dtype=np.int16)

        if downFactor == 1:
            data = sp.remove_artifacts(sp.notch_filter(sp.unsigned_to_signed(recording['amp']),60),
                                        stimOnsetInds,ms_before=0,ms_after=currStimDur+5,mode='zeros').get_traces()
        else:
            data = sp.remove_artifacts(sp.notch_filter(recording['amp'],60),
                                        stimOnsetInds,ms_before=0,ms_after=currStimDur+5,mode='zeros').get_traces()
            
        # if downFactor == 1:
        #     data = sp.notch_filter(sp.unsigned_to_signed(recording['amp']),60).get_traces()
        # else:
        #     data = sp.notch_filter(recording['amp'],60).get_traces()
            
        baselineEachBlock[indr,:,:] = data[:downsampleRate*downFactor,:]

        for indt, evSample in enumerate(stimOnsetInds):
            if evSample + sampleRange[0] < 0:
                break
            currEVLFPs[indt,:,:] = data[evSample+sampleRange[0]:evSample+sampleRange[1], :]

        if downFactor==1:
            # eventLockedLFP = np.vstack([eventLockedLFP,currEVLFPs])
            eventLockedLFP[indr,:,:,:] = currEVLFPs

        else:
            # eventLockedLFP = np.vstack([eventLockedLFP,signal.filtfilt(bCoeff, aCoeff, currEVLFPs, axis=0)])
            eventLockedLFP[indr,:,:,:] = signal.filtfilt(bCoeff, aCoeff, currEVLFPs, axis=0)

        if (indr)%10 == 0:
            print(f"{indr}/{nRecordingsThisSite} recordings processed")
    
    # eventLockedLFP = signal.filtfilt(bCoeff, aCoeff, eventLockedLFP, axis=0)
    channelStimEachTrial = np.array(channelStimEachTrial)

    ### reshape data ###
    eventLockedLFP = np.transpose(eventLockedLFP,axes=(0,1,3,2))        # (nBlocks,nTrials,nChannels,nSamples)
    baselineEachBlock = np.transpose(baselineEachBlock,axes=(0,2,1))    # (nBlocks,nChannels,nSamples)

    return channelStimEachTrial,eventLockedLFP,baselineEachBlock

def plot_multiband_power(ax, chanInds, power_dict, time_vector, sigma=5, withLabels=False):

    colors = plt.cm.tab10(np.linspace(0, 1, len(power_dict)))
    # Calculate global min and max across all smoothed bands for uniform scaling
    smoothed_data = {
        band: gaussian_filter1d(data, sigma=sigma, axis=2) 
        for band, data in power_dict.items()
    }
    
    # y_min = min(np.min(data) for data in smoothed_data.values())
    # y_max = max(np.max(data) for data in smoothed_data.values())

    # Extract scalars into lists and cast to native Python floats to prevent unit evaluation errors
    all_mins = [np.min(data) for data in smoothed_data.values()]
    all_maxs = [np.max(data) for data in smoothed_data.values()]
    y_min = float(np.min(all_mins))
    y_max = float(np.max(all_maxs))

    for indp,((band_name, data), color) in enumerate(zip(smoothed_data.items(), colors)):
                
        y_data = data[*chanInds, :]
        
        label = band_name if withLabels else ""
        ax.plot(time_vector, y_data, color=color, lw=1, label=label)
    
        ax.axvline(0, color='red', linestyle='--', lw=0.8) 
        ax.set_ylim(y_min, y_max)
        ax.set_xlim(time_vector[0], time_vector[-1])

def plot_radial_multiband_power(power_dict, time_vector, stimDur=0.65,baselineDict=None,sigma=20, donutChans = studyparams.DONUT_ORDER,scalebar_y=None,scalebar_x=None):
    """
    Plots overlapping, smoothed peristimulus power for multiple LFP bands in a concentric layout.
    
    Parameters:
    power_dict : dict
        Dictionary mapping band names to ndarrays of shape (2, 8, n_samples).
    time_vector : ndarray
        1D array of timepoints.
    sigma : float
        Standard deviation for the Gaussian kernel.
    """
    fig = plt.figure(figsize=(16, 16));
    
    radii = [0.22, 0.42]
    rotFactor = 3
    preRotAngles = np.linspace(-3*np.pi/8, -3*np.pi/8 + 2 * np.pi, 8, endpoint=False)[::-1]
    angles = np.concat([preRotAngles[rotFactor:],preRotAngles[:rotFactor]])
    
    ax_width = 0.15
    ax_height = 0.12


    # baselineEachChan = {band:np.zeros_like(donutChans,dtype=float) for band in power_dict}
    for band, data in power_dict.items():
        for ring_idx,_ in enumerate(radii):
            for angle_idx,_ in enumerate(angles):
                power_dict[band][ring_idx,angle_idx,:] = 10*np.log10(data[ring_idx,angle_idx,:]/np.mean(data[ring_idx,angle_idx,(time_vector < -0.1)]))
                
                # baselineThisChan = np.mean(baselineDict[band][ring_idx,angle_idx,:])
                # power_dict[band][ring_idx,angle_idx,:] = 10*np.log10(data[ring_idx,angle_idx,:]/baselineThisChan)
                # smoothed_data[band][ring_idx,angle_idx,:] -= np.mean(smoothed_data[band][ring_idx,angle_idx,(time_vector < -0.1)])
    
    # Calculate global min and max across all smoothed bands for uniform scaling
    smoothed_data = {
        band: gaussian_filter1d(data, sigma=sigma, axis=2) 
        for band, data in power_dict.items()
    }

    # Extract scalars into lists and cast to native Python floats to prevent unit evaluation errors
    all_mins = [np.min(data) for data in smoothed_data.values()]
    all_maxs = [np.max(data) for data in smoothed_data.values()]
    min_bls = [np.min(data[:,:,((time_vector<0)|(time_vector>stimDur+0.05))]) for data in smoothed_data.values()]
    # y_min = float(np.min(all_mins))
    y_min = float(np.min(min_bls))
    y_max = float(np.max(all_maxs))
    
    colors = plt.cm.tab10(np.linspace(0, 1, len(power_dict)))
    
    for ring_idx, r in enumerate(radii):
        for angle_idx, theta in enumerate(angles):
            x_center = 0.5 + r * np.cos(theta)
            y_center = 0.5 + r * np.sin(theta) - 0.02
            
            left = x_center - ax_width / 2
            bottom = y_center - ax_height / 2
            
            ax = fig.add_axes([left, bottom, ax_width, ax_height]);
            
            for (band_name, data), color in zip(smoothed_data.items(), colors):
                y_data = data[ring_idx, angle_idx, :]
                
                label = band_name if ring_idx == 0 and angle_idx == 0 else ""
                ax.plot(time_vector, y_data, color=color, lw=1.5, label=label, clip_on=False);
            
            ax.axvline(0, color='red', linestyle='--', lw=1);
            ax.set_ylim(y_min, y_max);
            ax.set_xlim(time_vector[0], time_vector[-1]);
            
            ax.axis('off');
            plt.sca(ax);
            plt.title(donutChans[ring_idx][angle_idx],fontsize=18);

        # Scalebar Implementation
        # Scalebar Implementation
        scale_ax = fig.add_axes([0.85, 0.05, ax_width, ax_height])
        scale_ax.set_xlim(time_vector[0], time_vector[-1])
        scale_ax.set_ylim(y_min, y_max)
        scale_ax.axis('off')
        scaleAmount = 0.5
        
        if scalebar_y is None:
            scalebar_y = (y_max - y_min) * scaleAmount

        if scalebar_x is None:
            scalebar_x = (time_vector[-1]-time_vector[0])*scaleAmount
            
        x0 = time_vector[0]
        y0 = y_min
        
        # Draw L-shape
        scale_ax.plot([x0, x0 + scalebar_x], [y0, y0], color=rcParams['axes.edgecolor'], lw=8) 
        scale_ax.plot([x0, x0], [y0, y0 + scalebar_y], color=rcParams['axes.edgecolor'], lw=8)
        
        # Add text labels
        x_range = time_vector[-1] - time_vector[0]
        y_range = y_max - y_min
        scale_ax.text(np.round(x0 + scalebar_x / 2,2), np.round(y0 - y_range * 0.05,2), 
                      f"{scalebar_x:.1f} s", ha='center', va='top', fontsize=18, fontweight='bold')
        scale_ax.text(np.round(x0 - x_range * 0.05,2), np.round(y0 + scalebar_y / 2,2), 
                      f"{scalebar_y:.1f} dB", ha='right', va='center', rotation=90, fontsize=18, fontweight='bold')

            
    leg = fig.legend(loc='lower left', frameon=False, prop={'size':18,'weight':'bold'}, markerscale=4);
    plt.setp(leg.get_lines(),linewidth=4)

    # plt.show()
    return fig
        

def make_donut_axes(figsize = (16,16), donutChans = studyparams.DONUT_ORDER,rotFactor=3):

    fig = plt.figure(figsize=figsize)
    
    radii = [0.25 + 0.16*i for i in range(donutChans.shape[0])]
    preRotAngles = np.linspace(-3*np.pi/8 , -3*np.pi/8  + 2 * np.pi, donutChans.shape[1], endpoint=False)[::-1]


    angles = np.concat([preRotAngles[rotFactor:],preRotAngles[:rotFactor]])

    ax_width = 0.15
    ax_height = 0.12
    axes = np.zeros_like(donutChans,dtype=object)
    
    for ring_idx, r in enumerate(radii):
        for angle_idx, theta in enumerate(angles):
            x_center = (0.52 + r * np.cos(theta))*0.95\
                *(1.035 if ring_idx>0 and theta in np.concat([preRotAngles[1:3],preRotAngles[5:7]]) else 1)\
                     -(0.035 if ring_idx>0 and theta in preRotAngles[1:3] else 0)\
                     -(0.02 if list(preRotAngles).index(theta)//4==1 else 0)
            y_center = 0.5 + r * np.sin(theta)
            
            left = x_center - ax_width / 2
            bottom = y_center - ax_height / 2
            
            ax = fig.add_axes([left, bottom, ax_width, ax_height])
            
            # ax.axis('off')
            ax.set_title(donutChans[ring_idx][angle_idx])
            axes[ring_idx,angle_idx] = ax
            
    return fig,axes


def calc_evoked_lfp_power(data, fs=1000.0, nperseg=None):
    """
    Computes the stimulus-evoked LFP power spectrum.
    
    Parameters:
    data : ndarray
        Electrophysiology data with shape (nTrials, nChannels, nSamples).
    fs : float
        Sampling frequency in Hz.
    nperseg : int, optional
        Length of each segment for Welch's method. Determines frequency resolution.
        
    Returns:
    freqs : ndarray
        Array of frequencies.
    power : ndarray
        Evoked power spectral density, shape (nChannels, nFreqs).
    """
    # 1. Average across trials to isolate the phase-locked evoked response
    evoked_response = np.mean(data, axis=0) 
    
    # 2. Compute the power spectral density of the average using Welch's method
    freqs, power = signal.welch(evoked_response, fs=fs, axis=-1, nperseg=nperseg)
    
    return freqs, power

def calc_evoked_lfp_time_frequency(data, freqs, fs=1000.0, wavelet='cmor0.5-1.0'):
    """
    Computes the stimulus-evoked LFP time-frequency representation using PyWavelets.
    
    Parameters:
    data : ndarray
        Electrophysiology data with shape (nTrials, nChannels, nSamples).
    freqs : ndarray
        Array of specific frequencies to compute (in Hz).
    fs : float, optional
        Sampling frequency in Hz. Default is 1000.0.
    wavelet : str, optional
        Continuous wavelet name. 'cmorB-C' specifies a complex Morlet wavelet 
        where B is the bandwidth and C is the central frequency.
        
    Returns:
    freqs : ndarray
        Array of frequencies.
    power : ndarray
        Evoked time-frequency power, shape (nChannels, nFreqs, nSamples).
    """
    evoked_response = np.mean(data, axis=0) 
    
    # Convert target frequencies to wavelet scales
    scales = pywt.central_frequency(wavelet) * fs / freqs
    
    # Compute the Continuous Wavelet Transform
    coefs, _ = pywt.cwt(evoked_response, scales, wavelet, sampling_period=1/fs, axis=-1)
    
    # Calculate power (squared amplitude)
    power = np.abs(coefs)**2
    
    # pywt.cwt returns shape (nFreqs, nChannels, nSamples). Transpose to output (nChannels, nFreqs, nSamples).
    power = np.mean(np.transpose(power, (1, 0, 2)),axis=2)
        
    return freqs, power

def plot_power_spectra(data, timeVec, stimDur=0.65,freqRange=[0, 200], nperseg=400, fs=1000, shankDepths=studyparams.SHANK_DEPTHS['FD006']['main']):
    """
    Calculates and plots the baseline-normalized, stimulus-evoked LFP power spectra across recording and stimulus channels.

    Parameters
    ----------
    data : ndarray
        Electrophysiology data array of shape (nTrials, nChannels, nSamples).
    timeVec : ndarray
        1D array of time points corresponding to the samples in `data`, in seconds.
    freqRange : list of float, optional
        The lower and upper bounds of the frequencies to plot in Hz. Default is [0, 200].
    nperseg : int, optional
        Length of each segment used in Welch's method for PSD calculation. Default is 500.
    fs : float, optional
        Sampling frequency of the data in Hz. Default is 1000.
    shankDepths : list or ndarray, optional
        Depth labels for the stimulus channels, used for y-axis tick labels. 

    Returns
    -------
    plot_freqs : ndarray
        1D array of frequencies corresponding to the x-axis of the plotted spectra.
    dataToPlot : ndarray
        3D array of relative power spectral density values in dB, shape (nStimChans, nRecChans, nFreqs).
    """
    nTrials, _, nSamples = data.shape
    nStimChans = len(studyparams.SHANK_ORDER)
    stimChanIndOrder = np.stack([np.arange(nStimChans//2), np.arange(nStimChans//2, nStimChans)]).ravel('F')
    recChanOrder = studyparams.DONUT_ORDER.flatten()
    nRecChans = len(recChanOrder)
    
    dummy_freqs = np.fft.rfftfreq(nperseg, 1/fs)
    freq_mask = (dummy_freqs >= freqRange[0]) & (dummy_freqs <= freqRange[1])
    plot_freqs = dummy_freqs[freq_mask]
    nFreqs_plot = len(plot_freqs)
    
    # Define time segment masks
    baseline_mask = (timeVec < 0)
    post_mask = (timeVec > stimDur+0.05)
    
    # Initialize with NaNs to prevent unallocated memory artifacts
    dataToPlot = np.full((nStimChans, nRecChans, nFreqs_plot), np.nan, dtype=float)
    
    for inds, stimChan in enumerate(stimChanIndOrder[::-1]):
        for indr, recChan in enumerate(recChanOrder):
            trial_slice = data[stimChan*5:stimChan*5 + 5, recChan, :]
            
            # Extract baseline and post-stimulus data
            baseline_data = trial_slice[:, baseline_mask]
            post_data = trial_slice[:, post_mask]
            
            # Calculate evoked power for each segment
            freqs, baseline_pwr = calc_evoked_lfp_power(baseline_data, nperseg=nperseg, fs=fs)
            freqs, post_pwr = calc_evoked_lfp_power(post_data, nperseg=nperseg, fs=fs)
            
            safe_baseline = np.maximum(baseline_pwr[freq_mask], 1e-12)
            safe_post = np.maximum(post_pwr[freq_mask], 1e-12)
            
            # Normalize to baseline (dB)
            dataToPlot[inds, indr, :] = 10 * np.log10(safe_post / safe_baseline)

    # Symmetrically center limits around 0
    # abs_max = np.nanmax(np.abs(dataToPlot))
    abs_max = 20
    vmin = -abs_max
    vmax = abs_max
    
    fig, axs = make_donut_axes(figsize=(18,18))
    im = None
    
    # Generate 5 evenly spaced ticks for the x-axis
    tick_indices = np.linspace(0, nFreqs_plot - 1, 5, dtype=int)
    tick_labels = np.round(plot_freqs[tick_indices]).astype(int)
    
    for inda, ax in enumerate(axs.flatten()):
        if inda < nRecChans:
            im = ax.imshow(
                dataToPlot[:, inda, :], 
                aspect=dataToPlot.shape[2]/dataToPlot.shape[0], 
                origin='lower', 
                vmin=vmin, 
                vmax=vmax,
                cmap='RdBu_r'
            )
            
            # if studyparams.DONUT_ORDER.flatten()[inda]==8:
            #     ax.set_yticks(np.arange(0, nStimChans), shankDepths)
            #     ax.set_xticks(tick_indices, tick_labels)
            #     ax.set_xlabel('Frequency (Hz)',fontsize=16)
            #     ax.set_ylabel(f'Stim Depth ({r"$\mu m$"} from pia)',fontsize=16)
            # else:
            #     ax.axis('off')

            ax.set_yticks(np.arange(0, nStimChans,2), shankDepths[::2],fontsize=12)
            ax.set_xticks(tick_indices, tick_labels,fontsize=12)

    fig.supxlabel('Frequency (Hz)',fontsize=24)
    fig.supylabel(f'Stim Depth ({r"$\mu m$"})',fontsize=24)
    fig.subplots_adjust(wspace=0.6)

    if im is not None:
        cb = fig.colorbar(im, ax=axs.ravel().tolist(), fraction=0.02, pad=0.02,location='right')
        cb.ax.tick_params(labelsize=18)
        cb.ax.set_ylabel('Normalized Power (dB)',fontsize=24)
        
    return plot_freqs, dataToPlot, fig, ax

def calc_broadband_power(data,timeVec,stimDur=0.65, freqRange=[4, 100], nperseg=100, fs=1000, wavelet = 'cmor1.5-1.0'):
    """
    Calculates the baseline-normalized, stimulus-evoked LFP broadband power over time.
    """
    nTrials, nRecChans, nSamples = data.shape
    nStimChans = len(studyparams.SHANK_ORDER)
    stimChanIndOrder = np.stack([np.arange(nStimChans//2), np.arange(nStimChans//2, nStimChans)]).ravel('F')
    
    target_freqs = np.linspace(max(1, freqRange[0]), freqRange[1], nperseg)
    scales = pywt.central_frequency(wavelet) * fs / target_freqs
    
    baseline_mask = (timeVec < -0.1)
    evoked_mask = (timeVec > stimDur)
    
    bbpwr = np.full((nTrials, nRecChans, nSamples), np.nan, dtype=float)
    
    for indt in range(nTrials):
        for indr, recChan in enumerate(range(nRecChans)):
            evoked_response = data[indt,recChan,:]
            
            coefs, _ = pywt.cwt(evoked_response, scales, wavelet, sampling_period=1/fs)
            pwr = np.abs(coefs)**2


            
            broadband_pwr = np.mean(pwr, axis=0)
            
            baseline_mean = np.mean(broadband_pwr[baseline_mask])
            if baseline_mean == 0:
                print("baseline_mean is ZERO!!!")
            # safe_baseline = np.maximum(baseline_mean, 1e-12)
            # safe_time_pwr = np.maximum(broadband_pwr, 1e-12)
            safe_baseline = baseline_mean
            safe_time_pwr = broadband_pwr
            
            bbpwr[indt, indr, :] = 10 * np.log10(safe_time_pwr / safe_baseline)

    return bbpwr



def plot_broadband_power(data, timeVec, stimDur=0.65, freqRange=[0, 200], nperseg=100, fs=1000, wavelet = 'cmor1.5-1.0',shankDepths=studyparams.SHANK_DEPTHS['FD006']['main']):
    """
    Calculates and plots the baseline-normalized, stimulus-evoked LFP broadband power over time.
    """
    nTrials, _, nSamples = data.shape
    nStimChans = len(studyparams.SHANK_ORDER)
    stimChanIndOrder = np.stack([np.arange(nStimChans//2), np.arange(nStimChans//2, nStimChans)]).ravel('F')
    recChanOrder = studyparams.DONUT_ORDER.flatten()
    nRecChans = len(recChanOrder)
    
    target_freqs = np.linspace(max(1, freqRange[0]), freqRange[1], nperseg)
    scales = pywt.central_frequency('cmor1.5-1.0') * fs / target_freqs
    
    baseline_mask = (timeVec < 0)
    evoked_mask = (timeVec > stimDur)
    dataToPlot = np.full((nStimChans, nRecChans, nSamples), np.nan, dtype=float)
    
    for inds, stimChan in enumerate(stimChanIndOrder[::-1]):
        for indr, recChan in enumerate(recChanOrder):
            trial_slice = data[stimChan*5:stimChan*5 + 5, recChan, :]

            # pwrs = np.zeros_like(trial_slice)
            # for trial in range(pwrs.shape[0]): 
            #     coefs, _ = pywt.cwt(trial_slice[trial], scales, wavelet, sampling_period=1/fs)
            #     pwrs[trial] = np.mean(np.abs(coefs)**2,axis=0)

            coefs,_ = pywt.cwt(np.mean(trial_slice,axis=0),scales, wavelet, sampling_period=1/fs)
            pwrs = np.abs(coefs**2)
                
            broadband_pwr = np.mean(pwrs,axis=0)
            
            baseline_mean = np.mean(broadband_pwr[baseline_mask])
            safe_baseline = np.maximum(baseline_mean, 1e-12)
            safe_time_pwr = np.maximum(broadband_pwr, 1e-12)
            
            dataToPlot[inds, indr, :] = 10 * np.log10(safe_time_pwr / safe_baseline)

    # abs_max = np.nanmax(np.abs(dataToPlot[:,:,(timeVec>stimDur+0.05)]))
    abs_max = 15
    vmin = -abs_max
    vmax = abs_max
    
    fig, axs = make_donut_axes(figsize=(18,18))
    im = None
    
    # Calculate index for t=0
    zero_idx = np.argmin(np.abs(timeVec - 0.0))
    stimoff_idx = np.argmin(np.abs(timeVec - stimDur))
    
    # Ensure 0.0 is explicitly included in the tick marks
    # target_times = np.unique(np.append(np.linspace(timeVec[0], timeVec[-1], 5), 0.0))
    target_times = np.linspace(timeVec[0], timeVec[-1], 4)
    target_times.sort()
    tick_indices = [np.argmin(np.abs(timeVec - t)) for t in target_times]
    tick_labels = np.round(target_times, 2)
    
    for inda, ax in enumerate(axs.flatten()):
        if inda < nRecChans:
            im = ax.imshow(
                dataToPlot[:, inda, :], 
                aspect=dataToPlot.shape[2]/dataToPlot.shape[0], 
                origin='lower', 
                vmin=vmin, 
                vmax=vmax,
                cmap='RdBu_r'
            )

            # Add dashed red line at stimulus onset
            ax.axvline(x=zero_idx, color='red', linestyle='--', linewidth=2)
            ax.axvline(x=stimoff_idx, color='red', linestyle='--', linewidth=2)
            ax.set_yticks(np.arange(0, nStimChans,2), shankDepths[::2],fontsize=12)
            ax.set_xticks(tick_indices, tick_labels,fontsize=12)

    fig.supxlabel('Time (s)',fontsize=24)
    fig.supylabel(f'Stim Depth ({r"$\mu m$"})',fontsize=24)
    fig.subplots_adjust(wspace=0.6)

    if im is not None:
        cb = fig.colorbar(im, ax=axs.ravel().tolist(), fraction=0.02, pad=0.02, location='right')
        cb.ax.tick_params(labelsize=18)
        cb.ax.set_ylabel('Normalized Power (dB)', fontsize=24)
        
    return timeVec, dataToPlot, fig, axs
    

def extract_lfp_bands(lfp_data, fs, bands=studyparams.LFP_BANDS, filter_order=4):
    """
    Filters LFP data into specified frequency bands.
    
    Parameters:
    lfp_data : ndarray
        Shape (nTrials, nSamples, nChannels).
    fs : float
        Sampling frequency in Hz.
    bands : dict, optional
        Dictionary of band names and (low_hz, high_hz) tuples.
    filter_order : int
        Order of the Butterworth filter.
        
    Returns:
    dict
        Filtered data arrays for each band, preserving original shape.
    """

    filtered_signals = {}
    nyquist = 0.5 * fs

    for band_name, (low_hz, high_hz) in bands.items():
        low = low_hz / nyquist
        high = high_hz / nyquist
        
        if high >= 1.0:
            high = 0.999 
            
        b, a = signal.butter(filter_order, [low, high], btype='band')
        
        # Apply filter along the time/samples axis (axis 1)
        filtered_signals[band_name] = signal.filtfilt(b, a, lfp_data, axis=1)

    return filtered_signals

def plot_radial_peristimulus_power(power_data, time_vector):
    """
    Plots peristimulus power timeseries for 16 channels in a concentric layout.
    
    Parameters:
    power_data : ndarray
        Shape (2, 8, n_samples). Row 0 is inner ring, Row 1 is outer ring.
    time_vector : ndarray
        1D array of timepoints.
    """
    fig = plt.figure(figsize=(10, 10))
    
    # Expanded radii to push plots closer to the figure edges
    radii = [0.22, 0.42]
    rotAngle = -3*np.pi/8
    angles = np.linspace(rotAngle, rotAngle + 2 * np.pi, 8, endpoint=False)[::-1]
    
    # Increased subplot dimensions to reduce dead space
    ax_width = 0.15
    ax_height = 0.12
    
    y_min, y_max = np.min(power_data), np.max(power_data)
    
    for ring_idx, r in enumerate(radii):
        for angle_idx, theta in enumerate(angles):
            x_center = 0.5 + r * np.cos(theta)
            y_center = 0.5 + r * np.sin(theta)
            
            left = x_center - ax_width / 2
            bottom = y_center - ax_height / 2
            
            ax = fig.add_axes([left, bottom, ax_width, ax_height])
            
            y_data = power_data[ring_idx, angle_idx, :]
            ax.plot(time_vector, y_data, color='black', lw=1)
            
            ax.axvline(0, color='red', linestyle='--', lw=0.8) 
            ax.set_ylim(y_min, y_max)
            ax.set_xlim(time_vector[0], time_vector[-1])
            
            if ring_idx == 1 and angle_idx == 0:
                ax.set_xticks([-0.5, 0, 1.5])
                ax.set_yticks([y_min, y_max])
                ax.tick_params(axis='both', which='major', labelsize=8)
            else:
                ax.set_xticks([])
                ax.set_yticks([])
            plt.sca(ax)
            plt.title(donutChans[ring_idx][angle_idx])
                
    # plt.show()


def compute_1d_csd(data, spacing,diam=500):
    '''
    compute 1d csd from spontaneous activity

    Args:
        data (ndarray): lfp data matrix (sorted by channel depth); shape (nChannels, nSamples)
        spacing (int): electrode spacing (um)

    Returns:
        csd (ndarray): current source density; shape (nChannels,)
    '''

    csd = icsd.DeltaiCSD(data*1E-6*pq.V,
                         spacing*np.arange(data.shape[0])*1e-6*pq.m,
                         diam=diam*1e-6*pq.m)

    return csd

def plot_icsd(lfp_data,spacing,diam=500):

    csd_obj = compute_1d_csd(lfp_data,spacing,diam)
    lfp_data = lfp_data*1e-6*pq.V

    fig, axes = plt.subplots(3,1, figsize=(8,8))

    #plot LFP signal
    ax = axes[0]
    cbmax = np.percentile(abs(lfp_data),99)
    im = ax.imshow(np.array(lfp_data), origin='upper', vmin=-cbmax, \
              vmax=cbmax, cmap='RdBu_r', interpolation='nearest')
    ax.axis(ax.axis('tight'))
    cb = plt.colorbar(im, ax=ax)
    cb.set_label('LFP (%s)' % lfp_data.dimensionality.string)
    ax.set_xticklabels([])
    ax.set_title('LFP')
    ax.set_ylabel('ch #')

    #plot raw csd estimate
    csd = csd_obj.get_csd()
    ax = axes[1]
    cbmax = np.percentile(abs(csd),99)
    im = ax.imshow(np.array(csd), origin='upper', vmin=-cbmax, \
          vmax=cbmax, cmap='RdBu_r', interpolation='nearest')
    ax.axis(ax.axis('tight'))
    ax.set_title(csd_obj.name)
    cb = plt.colorbar(im, ax=ax)
    cb.set_label('CSD (%s)' % csd.dimensionality.string)
    ax.set_xticklabels([])
    ax.set_ylabel('ch #')

    #plot spatially filtered csd estimate
    ax = axes[2]
    csd = csd_obj.filter_csd(csd)
    cbmax = np.percentile(abs(csd),99)
    im = ax.imshow(np.array(csd), origin='upper', vmin=-cbmax, \
          vmax=cbmax, cmap='RdBu_r', interpolation='nearest')
    ax.axis(ax.axis('tight'))
    ax.set_title(csd_obj.name + ', filtered')
    cb = plt.colorbar(im, ax=ax)
    cb.set_label('CSD (%s)' % csd.dimensionality.string)
    ax.set_ylabel('ch #')
    ax.set_xlabel('timestep')

    return fig, axes

def estimate_layers(data,spacing=100,diam=40):
    ### get csd ###
    if len(data.shape)==3:
        csd_obj = [compute_1d_csd(data[event],spacing,diam) for event in range(data.shape[0])]
        csd = np.mean(np.array([obj.filter_csd(obj.get_csd()) for obj in csd_obj]),axis=0)
    else:
        csd_obj = compute_1d_csd(data,spacing,diam)
        csd = csd_obj.filter_csd(csd_obj.get_csd())

    csdEachChan = np.mean(csd,axis=1)
    sinkInd = np.argmin(csdEachChan)
    layersEachChan = np.full((data.shape[0]),' '*16,dtype='U16')

    layersEachChan[:sinkInd-1] = 'deep'
    layersEachChan[sinkInd-1:sinkInd+2] = 'granule'
    layersEachChan[sinkInd+2:] = 'superficial'

    return layersEachChan,csd_obj,csdEachChan

def calc_broadband_power_each_layer(data,timeVec,layersEachChan,stimDur=0.65, freqRange=[0, 200], nperseg=100, fs=1000):
    """
    Calculates the baseline-normalized, stimulus-evoked LFP broadband power over time.
    """
    nTrials, nRecChans, nSamples = data.shape
    nStimChans = len(studyparams.SHANK_ORDER)
    stimChanIndOrder = np.stack([np.arange(nStimChans//2), np.arange(nStimChans//2, nStimChans)]).ravel('F')
    
    target_freqs = np.linspace(max(1, freqRange[0]), freqRange[1], nperseg)
    scales = pywt.central_frequency('cmor1.5-1.0') * fs / target_freqs
    
    baseline_mask = (timeVec >= -1.0) & (timeVec < 0.0)
    
    bbpwr = np.full((nTrials, nRecChans, nSamples), np.nan, dtype=float)
    
    for indt in range(nTrials):
        for indr, recChan in enumerate(range(nRecChans)):
            evoked_response = data[indt,recChan,:]
            
            coefs, _ = pywt.cwt(evoked_response, scales, 'cmor1.5-1.0', sampling_period=1/fs)
            pwr = np.abs(coefs)**2
            
            broadband_pwr = np.mean(pwr, axis=0)
            
            baseline_mean = np.mean(broadband_pwr[baseline_mask])
            safe_baseline = np.maximum(baseline_mean, 1e-12)
            safe_time_pwr = np.maximum(broadband_pwr, 1e-12)
            
            bbpwr[indt, indr, :] = 10 * np.log10(safe_time_pwr / safe_baseline)

    return bbpwr


