import socket
import time
import random
import itertools
import sys
import os
import csv
from datetime import datetime

DEBUG = False
if len(sys.argv) > 1 and sys.argv[1] == 'debug':
    DEBUG = True

# ==========================================
# 1. Hardware & Trigger Configuration
# ==========================================
RHX_IP = '127.0.0.1'
RHX_PORT = 5000

# ==========================================
# 2. Timing & Parameter Space
# ==========================================
ISI_BASE = 2.0        
ISI_JITTER = 0.5      

baselineDuration = 0.5        # minutes of baseline before stim

shankOrder = [24, 0, 7, 31, 25, 1, 6, 30, 26, 2, 5, 29, 27, 3, 4, 28]
nChan = len(shankOrder)
CHANNELS = [f"a-{site:03d}" for site in shankOrder] 
channelSets = [CHANNELS[::2],CHANNELS[1::2]]

pulseWidthToUse = 200       # us
electrodeDiameter = 40      # um
electrodeArea = (22/7)*((electrodeDiameter/2)**2)
areaToMatch = (22/7)*((75/2)**2)
coulsToMatch = [0,0.5,1,2,3,4,5]
coulsToUse = [couls*(electrodeArea/areaToMatch) for couls in coulsToMatch]       # nC/phase
ampsToUse = [couls/(pulseWidthToUse*(1e-3)) for couls in coulsToUse]

WAVEFORMS = [
    {
        'name': 'Symmetric Biphasic Cathodic-First Pulse Train',
        'polarity': 'NegativeFirst',
        'pulseWidths': [[200, 40, 200]],             
        'amplitudes': ampsToUse,         
        'frequencies': [160,320],                           
        'pulseDurations': [250,650]                         
    },
    {
        'name': 'Symmetric Biphasic Cathodic-First Single Pulse',
        'polarity': 'NegativeFirst',
        'pulseWidths': [[200, 100, 200]],             
        'amplitudes': [0,10,20,40,80,100],
        'frequencies': [1],                           
        'pulseDurations': [1]                                        
    }
]

# ==========================================
# 3. Execution Functions
# ==========================================
def send_intan_batch(sock, cmd_list):
    """Sends commands individually but instantly, bypassing blocking reads."""
    # Set socket to non-blocking so it doesn't wait for silent successful returns
    sock.setblocking(False)
    
    for cmd in cmd_list:
        sock.sendall(f"{cmd};\n".encode('utf-8'))
        time.sleep(0.02) # 2ms delay gives Intan's parser time to process the buffer
        
        try:
            # Catch any immediate error messages
            response = sock.recv(1024).decode('utf-8').strip()
            if DEBUG and response:
                print(f"Server Error: {response}")
        except BlockingIOError:
            # A BlockingIOError here means Intan stayed silent (Command Accepted)
            pass
            
    # Restore normal blocking for the rest of the script
    sock.setblocking(True)

def get_stim_combs(wfs):
    stim_combinations = []
    for wf in wfs:
        wf_combos = list(itertools.product(
            [wf], wf['pulseWidths'], wf['amplitudes'], wf['frequencies'], wf['pulseDurations']
        ))
        stim_combinations.extend(wf_combos)
    # random.shuffle(stim_combinations)
    return stim_combinations

def main():
    stim_record = []
    nTrialsEachComb = 5

    # Initialize CSV Log File
    launch_time_dt = datetime.now()
    launch_time_str = launch_time_dt.strftime("%Y%m%d_%H%M%S.%f")
    if not os.path.exists('stim_logs'):
        os.mkdir('stim_logs')
    log_filename = os.path.join(f"stim_logs",f"single_channel_stim_log_{start_time_str}.csv")
    
    with open(log_filename, mode='w', newline='') as log_file:
        csv_writer = csv.writer(log_file)
        # Write CSV Header
        csv_writer.writerow([
             'Date_Time', 'Channel', 'Timestamp', 'Waveform', 
            'Base_Amp_uA', 'Freq_Hz', 'Train_Dur_ms', 
            'Phase_1_us', 'Interphase_Delay_us', 'Phase_2_us'
        ])


        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((RHX_IP, RHX_PORT))
                print("Connected to Intan RHX.\n")
                stim_combinations = get_stim_combs(WAVEFORMS)

		

                for i, (waveform, pw_set, base_amp, freq, train_dur_ms) in enumerate(stim_combinations, 1):
                    
                    for channelSet in channelSets:
                        s.sendall(b"set runmode stop;")     # make sure acquisition is off
                        print(f"[{i}/{len(stim_combinations)}] {channelSet} | {base_amp}uA, {freq}Hz, {train_dur_ms}ms")

                        ### Set up spike train ###
                        num_pulses = int(freq * (train_dur_ms / 1000.0)) if "train" in waveform['name'].lower() else 1
                        period_us = 1000000 / freq if freq > 0 else 0
                        pulse_or_train = "PulseTrain" if num_pulses > 1 else "SinglePulse"
                        p1_dur, ip_delay, p2_dur = pw_set
                        shape = "BiphasicWithInterphaseDelay" if ip_delay > 0 else "Biphasic"



                        ### Build the batch command list ###
                        cmd_batch=[]
                        for indc,channel in enumerate(channelSet):
                            cmd_batch.extend([
                                f"set {channel}.NumberOfStimPulses {num_pulses}",
                                f"set {channel}.PulseTrainPeriodMicroseconds {period_us}",
                                f"set {channel}.PulseOrTrain {pulse_or_train}",
                                f"set {channel}.Shape {shape}",
                                f"set {channel}.Polarity {waveform['polarity']}",
                                f"set {channel}.FirstPhaseAmplitudeMicroAmps {base_amp}",
                                f"set {channel}.FirstPhaseDurationMicroseconds {p1_dur}",
                                f"set {channel}.InterphaseDelayMicroseconds {ip_delay}",
                                f"set {channel}.SecondPhaseAmplitudeMicroAmps {base_amp}",
                                f"set {channel}.SecondPhaseDurationMicroseconds {p2_dur}",
                                f"set {channel}.Source KeypressF{indc+1}",  
                                f"set {channel}.StimEnabled True"])
                            
                        ### Send/upload stim params ###
                        send_intan_batch(s, cmd_batch)
                        time.sleep(2)
                        s.sendall(b"execute UploadStimParameters;")
                        print(f"Uploading Stimulation Parameters.")
                        time.sleep(5)                        

                        ### Start recording ### 
                        if DEBUG:
                            s.sendall(b'set runmode run;')

                        else:
                            s.sendall(b'set runmode record;')

                        time.sleep(60*baselineDuration)                  # record baseline activity
                        chanInds = [i for i in range(len(channelSet))]

                        trialsCtr = 0
                        for trial in range(nTrialsEachComb):
                            chanOrder = random.sample(chanInds,len(channelSet))
                            for chanInd in chanOrder:
                                trialsCtr += 1
                                current_isi = ISI_BASE + random.uniform(0, ISI_JITTER)
                                s.sendall(f"execute ManualStimTriggerPulse f{chanInd+1};".encode('utf-8'))
                                lastStimTime = 

                                # 4. Log the exact execution time and parameters
                                exec_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                                csv_writer.writerow([
                                    channelSet[chanInd], exec_time, waveform['name'], 
                                    base_amp, freq, train_dur_ms, p1_dur, ip_delay, p2_dur
                                ])
                                
                                print(f"{trialsCtr}\tStimulating {channelSet[chanInd]}\t(f{chanInd+1})")
                                log_file.flush() 

                                time.sleep(current_isi)

                        # 5. Disarm Channels
                        send_intan_batch(s,[f"set {channel}.StimEnabled False;" for channel in channelSet])
                    
                    
                print("\nProtocol complete.")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
