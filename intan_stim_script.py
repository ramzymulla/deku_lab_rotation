import socket
import time
import random
import itertools
import sys

DEBUG = False
if len(sys.argv) > 1:
    if sys.argv[1] == 'debug':
        DEBUG = True

# ==========================================
# 1. Hardware & Trigger Configuration
# ==========================================
RHX_IP = '127.0.0.1'
RHX_PORT = 5000

TRIGGER_METHOD = 'TCP'  

# ==========================================
# 2. Timing & Parameter Space
# ==========================================
ISI_BASE = 2.0        
ISI_JITTER = 0.5      

shankOrder = [25,1,8,32,26,2,7,31,27,3,6,30,28,4,5,29]
CHANNELS = [f"a-{site:03d}" for site in shankOrder] # TCP server requires lowercase prefix

CHANNEL_MAP = {ind+1:chan for ind,chan in enumerate(CHANNELS)}

WAVEFORMS = [
    {
        'name': 'Symmetric Biphasic Cathodic-First',
        'polarity': 'NegativeFirst',
        # [FirstPhaseDuration, InterphaseDelay, SecondPhaseDuration] in microseconds
        'pulseWidths': [[200, 33.3, 200]],             
        'amplitudes': [0, 1, 2, 5, 10, 20, 40],         
        'frequencies': [320],                           
        'pulseDurations': [650]                         
    }
]

# ==========================================
# 3. Execution Functions
# ==========================================
def send_intan_command(sock, command):
    sock.sendall(f"{command}\n".encode('utf-8'))

    try:
        response = sock.recv(1024).decode('utf-8').strip()
        if DEBUG:
            print(f"Sent: {command} | Received: {response}")
        return response
    except socket.timeout:
        return "Timeout"

def fire_hardware_ttl():
    # Insert hardware trigger logic here
    print("      [Hardware TTL Fired]")

def get_stim_combs(chs, wfs):
    stim_combinations = []
    for wf in wfs:
        wf_combos = list(itertools.product(
            chs, 
            [wf], 
            wf['pulseWidths'], 
            wf['amplitudes'], 
            wf['frequencies'], 
            wf['pulseDurations']
        ))
        stim_combinations.extend(wf_combos)
    random.shuffle(stim_combinations)
    return stim_combinations

def main():
    stim_record = []
    nTrialsEachComb = 20

    for trial in range(nTrialsEachComb):
        stim_combinations = get_stim_combs(CHANNELS, WAVEFORMS)
        stim_record.extend(stim_combinations)

        print(f"\n--- Starting Trial Loop {trial + 1} ---")
        print(f"Generated {len(stim_combinations)} randomized stimulation combinations.")

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((RHX_IP, RHX_PORT))
                print("Connected to Intan RHX.\n")

                for i, (channel, waveform, pw_set, base_amp, freq, train_dur_ms) in enumerate(stim_combinations, 1):
                    current_isi = ISI_BASE + random.uniform(0, ISI_JITTER)
                    
                    print(f"[{i}/{len(stim_combinations)}] {channel} | {waveform['name']} | {base_amp}uA, {freq}Hz, {train_dur_ms}ms")

                    # 1. Train Parameters
                    num_pulses = int(freq * (train_dur_ms / 1000.0))
                    period_us = 1000000 / freq if freq > 0 else 0
                    pulse_or_train = "PulseTrain" if num_pulses > 1 else "SinglePulse"
                    
                    send_intan_command(s, f"set {channel}.NumberOfStimPulses {num_pulses}")
                    send_intan_command(s, f"set {channel}.PulseTrainPeriodMicroseconds {period_us}")
                    send_intan_command(s, f"set {channel}.PulseOrTrain {pulse_or_train}")

                    # 2. Phase Parameters
                    p1_dur, ip_delay, p2_dur = pw_set
                    shape = "BiphasicWithInterphaseDelay" if ip_delay > 0 else "Biphasic"

                    send_intan_command(s, f"set {channel}.Shape {shape}")
                    send_intan_command(s, f"set {channel}.Polarity {waveform['polarity']}")
                    
                    send_intan_command(s, f"set {channel}.FirstPhaseAmplitudeMicroAmps {base_amp}")
                    send_intan_command(s, f"set {channel}.FirstPhaseDurationMicroseconds {p1_dur}")
                    
                    send_intan_command(s, f"set {channel}.InterphaseDelayMicroseconds {ip_delay}")
                    
                    send_intan_command(s, f"set {channel}.SecondPhaseAmplitudeMicroAmps {base_amp}")
                    send_intan_command(s, f"set {channel}.SecondPhaseDurationMicroseconds {p2_dur}")

                    # 3. Trigger Sequence
                    send_intan_command(s, f"set {channel}.StimEnabled True")

                    if TRIGGER_METHOD == 'TCP':
                        # RHX may not support direct software triggering via execute
                        send_intan_command(s, "execute manualstimtrigger") 
                    elif TRIGGER_METHOD == 'TTL':
                        fire_hardware_ttl()
                    
                    send_intan_command(s, f"set {channel}.StimEnabled False")
                    time.sleep(current_isi)
                    
                print("\nProtocol complete.")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()