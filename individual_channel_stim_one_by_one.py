import socket
import time
import random
import itertools
import sys
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

baselineDuration = 5        # minutes of baseline before stim

shankOrder = [24, 0, 7, 31, 25, 1, 6, 30, 26, 2, 5, 29, 27, 3, 4, 28]
nChan = len(shankOrder)
CHANNELS = [f"a-{site:03d}" for site in shankOrder] 

WAVEFORMS = [
    {
        'name': 'Symmetric Biphasic Cathodic-First',
        'polarity': 'NegativeFirst',
        'pulseWidths': [[200, 40, 200]],             
        'amplitudes': [1, 2, 5, 10, 20, 40, 0],         
        'frequencies': [320],                           
        'pulseDurations': [650]                         
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
            CHANNELS, [wf], wf['pulseWidths'], wf['amplitudes'], wf['frequencies'], wf['pulseDurations']
        ))
        stim_combinations.extend(wf_combos)
    # random.shuffle(stim_combinations)
    return stim_combinations

def main():
    stim_record = []
    nTrialsEachComb = 2

    # Initialize CSV Log File
    start_time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"single_channel_stim_log_{start_time_str}.csv"
    
    with open(log_filename, mode='w', newline='') as log_file:
        csv_writer = csv.writer(log_file)
        # Write CSV Header
        csv_writer.writerow([
             'Channel', 'Timestamp', 'Waveform', 
            'Base_Amp_uA', 'Freq_Hz', 'Train_Dur_ms', 
            'Phase_1_us', 'Interphase_Delay_us', 'Phase_2_us'
        ])


        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((RHX_IP, RHX_PORT))
                print("Connected to Intan RHX.\n")
 
                trialsCtr = 0
                for trial in range(nTrialsEachComb):
                    stim_combinations = get_stim_combs(WAVEFORMS)
                    random.shuffle(stim_combinations)
                    for i, (channel,waveform, pw_set, base_amp, freq, train_dur_ms) in enumerate(stim_combinations, 1):
                        
                        s.sendall(b"set runmode stop;")     # make sure acquisition is off
                        # print(f"[{i}/{len(stim_combinations)}] {channel} | {base_amp}uA, {freq}Hz, {train_dur_ms}ms")

                        ### Set up spike train ###
                        num_pulses = int(freq * (train_dur_ms / 1000.0))
                        period_us = 1000000 / freq if freq > 0 else 0
                        pulse_or_train = "PulseTrain" if num_pulses > 1 else "SinglePulse"
                        p1_dur, ip_delay, p2_dur = pw_set
                        shape = "BiphasicWithInterphaseDelay" if ip_delay > 0 else "Biphasic"



                        ### Build the batch command list ###
                        cmd_batch= [
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
                                f"set {channel}.Source KeypressF1",  
                                f"set {channel}.StimEnabled True",
                                f"execute UploadStimParameters {channel};"]
                            
                        ### Send/upload stim params ###
                        send_intan_batch(s, cmd_batch)                 

                        ### Start recording ### 
                        if DEBUG:
                            s.sendall(b'set runmode run;')

                        else:
                            s.sendall(b'set runmode record;')

                        time.sleep(0.5)                  # record baseline activity
                        
                        
                        trialsCtr += 1
                        current_isi = ISI_BASE + random.uniform(0, ISI_JITTER)
                        s.sendall(b"execute ManualStimTriggerPulse f1;")
                        time.sleep(current_isi + train_dur_ms/1000)       

                        # 4. Log the exact execution time and parameters
                        exec_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                        csv_writer.writerow([
                            channel, exec_time, waveform['name'], 
                            base_amp, freq, train_dur_ms, p1_dur, ip_delay, p2_dur
                        ])
                        
                        print(f"{trialsCtr}\tStimulating {channel}")
                        log_file.flush() 

                        
                        # 5. Disarm Channels
                        send_intan_batch(s,[f"set {channel}.StimEnabled False;"])
                    
                    
                print("\nProtocol complete.")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
