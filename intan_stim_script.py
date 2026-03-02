import socket
import time
import random
import itertools
import sys
import pyautogui # Required for software triggering
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

shankOrder = [25,1,8,32,26,2,7,31,27,3,6,30,28,4,5,29]
CHANNELS = [f"a-{site-1:03d}" for site in shankOrder] 

WAVEFORMS = [
    {
        'name': 'Symmetric Biphasic Cathodic-First',
        'polarity': 'NegativeFirst',
        'pulseWidths': [[200, 40, 200]],             
        'amplitudes': [0, 1, 2, 5, 10, 20, 40],         
        'frequencies': [320],                           
        'pulseDurations': [650]                         
    }
]

# ==========================================
# 3. Execution Functions
# ==========================================
# ==========================================
# 3. Execution Functions
# ==========================================
def send_intan_batch(sock, cmd_list):
    """Sends commands individually but instantly, bypassing blocking reads."""
    # Set socket to non-blocking so it doesn't wait for silent successful returns
    sock.setblocking(False)
    
    for cmd in cmd_list:
        sock.sendall(f"{cmd}\n".encode('utf-8'))
        time.sleep(0.002) # 2ms delay gives Intan's parser time to process the buffer
        
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

def get_stim_combs(chs, wfs):
    stim_combinations = []
    for wf in wfs:
        wf_combos = list(itertools.product(
            chs, [wf], wf['pulseWidths'], wf['amplitudes'], wf['frequencies'], wf['pulseDurations']
        ))
        stim_combinations.extend(wf_combos)
    random.shuffle(stim_combinations)
    return stim_combinations

def main():
    stim_record = []
    nTrialsEachComb = 20

    # Initialize CSV Log File
    start_time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"single_channel_stim_log_{start_time_str}.csv"
    
    with open(log_filename, mode='w', newline='') as log_file:
        csv_writer = csv.writer(log_file)
        # Write CSV Header
        csv_writer.writerow([
            'Trial_Loop', 'Timestamp', 'Channel', 'Waveform', 
            'Base_Amp_uA', 'Freq_Hz', 'Train_Dur_ms', 
            'Phase_1_us', 'Interphase_Delay_us', 'Phase_2_us'
        ])

        for trial in range(nTrialsEachComb):
            stim_combinations = get_stim_combs(CHANNELS, WAVEFORMS)
            stim_record.extend(stim_combinations)

            print(f"\n--- Starting Trial Loop {trial + 1} ---")
            print(f"Generated {len(stim_combinations)} randomized stimulation trials.")

            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(2.0)
                    s.connect((RHX_IP, RHX_PORT))
                    print("Connected to Intan RHX.\n")

                    for i, (channel, waveform, pw_set, base_amp, freq, train_dur_ms) in enumerate(stim_combinations, 1):
                        current_isi = ISI_BASE + random.uniform(0, ISI_JITTER)
                        print(f"[{i}/{len(stim_combinations)}] {channel} | {base_amp}uA, {freq}Hz, {train_dur_ms}ms")

                        num_pulses = int(freq * (train_dur_ms / 1000.0))
                        period_us = 1000000 / freq if freq > 0 else 0
                        pulse_or_train = "PulseTrain" if num_pulses > 1 else "SinglePulse"
                        p1_dur, ip_delay, p2_dur = pw_set
                        shape = "BiphasicWithInterphaseDelay" if ip_delay > 0 else "Biphasic"

                        s.sendall(b"set runmode stop")

                        # 1. Build the batch command list
                        cmd_batch = [
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
                            f"set {channel}.Source KeypressF1",  # Change trigger source to F1
                            f"set {channel}.StimEnabled True"    # Arm the channel
                        ]

                        # 2. Send all parameters at once
                        send_intan_batch(s, cmd_batch)
                        send_intan_batch(s, f"execute UploadStimParameters {channel}")

                        s.sendall(b'set runmode run')
                        time.sleep(0.5)
                        # 3. Software Trigger via Keyboard Emulation
                        s.sendall(b'execute ManualTriggerPulse f1')

                        # 4. Log the exact execution time and parameters
                        exec_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                        csv_writer.writerow([
                            trial + 1, exec_time, channel, waveform['name'], 
                            base_amp, freq, train_dur_ms, p1_dur, ip_delay, p2_dur
                        ])
                        log_file.flush() 
                        
                        time.sleep(2)

                        # 5. Disarm Channel
                        s.sendall(b"set runmode stop")
                        send_intan_batch(s, f"execute ClearAllStimParameters")
                        
                        
                        
                        
                    print("\nProtocol complete.")

            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    main()