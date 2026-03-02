import socket
import time
import random
import itertools

# ==========================================
# 1. Hardware & Trigger Configuration
# ==========================================
RHX_IP = '127.0.0.1'
RHX_PORT = 5000
TRIGGER_METHOD = 'TCP'  # 'TCP' or 'TTL'

shankOrder = [25,1,8,32,26,2,7,31,27,3,6,30,28,4,5,29]
CHANNELS = [f"A-{site-1:03d}" for site in shankOrder]

# Map logical order (1=Tip) to Intan hardware channels
# Adjust this according to your specific probe's wiring diagram
CHANNEL_MAP = {ind+1:chan for ind,chan in enumerate(CHANNELS)}



# ==========================================
# 2. Timing & Parameter Space
# ==========================================
ISI_BASE = 2.0        
ISI_JITTER = 0.5      

# Define groups of logical channels to activate simultaneously
SPATIAL_GROUPS = [
    [1],                # Tip only
    [1, 2],             # Tip + next
    [1, 2, 3, 4],       # Spread from tip
    [16],               # Base only
    [16, 15],           # Base + next
    [16, 15, 14, 13]    # Spread from base
]

WAVEFORMS = [
    {
        'name': 'Symmetric Biphasic Cathodic-First',
        'phases': [
            {'name': 'FirstPhase', 'polarity': 'Negative', 'amp_mult': 1.0},
            {'name': 'SecondPhase', 'polarity': 'Positive', 'amp_mult': 0.0},
            {'name': 'ThirdPhase', 'polarity': 'Positive', 'amp_mult': 1.0},
            {'name': 'FourthPhase', 'polarity': 'Positive', 'amp_mult': 0.0}   
        ],
        'pulseWidths': [[200, 40, 200, 0]],         
        'amplitudes': [0, 1, 5, 10, 20, 40], 
        'frequencies': [320],                       
        'pulseDurations': [650]                     
    }
]

# ==========================================
# 3. Execution Functions
# ==========================================
def send_intan_command(sock, command):
    sock.sendall(f"{command};\n".encode('utf-8'))
    try:
        return sock.recv(1024).decode('utf-8').strip()
    except socket.timeout:
        return "Timeout"

def fire_hardware_ttl():
    # Insert hardware trigger logic here
    print("      [Hardware TTL Fired]")

def main():
    stim_combinations = []
    
    for wf in WAVEFORMS:
        wf_combos = list(itertools.product(
            SPATIAL_GROUPS, 
            [wf], 
            wf['pulseWidths'], 
            wf['amplitudes'], 
            wf['frequencies'], 
            wf['pulseDurations']
        ))
        stim_combinations.extend(wf_combos)
        
    random.shuffle(stim_combinations)
    print(f"Generated {len(stim_combinations)} randomized stimulation trials.")

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect((RHX_IP, RHX_PORT))
            print("Connected to Intan RHX.\n")

            for i, (group, waveform, pw_set, base_amp, freq, train_dur_ms) in enumerate(stim_combinations, 1):
                current_isi = ISI_BASE + random.uniform(0, ISI_JITTER)
                
                print(f"[{i}/{len(stim_combinations)}] Logical Chs: {group} | {waveform['name']} | {base_amp}uA, {freq}Hz, {train_dur_ms}ms")

                # Map logical channels to hardware strings
                hw_channels = [CHANNEL_MAP[ch] for ch in group]

                # 1. Program and arm all channels in the group
                for channel in hw_channels:
                    send_intan_command(s, f"set {channel}.StimStepSize 1.0") 
                    
                    num_pulses = int(freq * (train_dur_ms / 1000.0))
                    period_us = 1000000 / freq if freq > 0 else 0
                    
                    send_intan_command(s, f"set {channel}.NumberOfStimPulses {num_pulses}")
                    send_intan_command(s, f"set {channel}.StimPulsePeriod {period_us}")

                    for phase_idx, phase in enumerate(waveform['phases']):
                        phase_name = phase['name']
                        calc_amp = base_amp * phase['amp_mult']
                        phase_duration = pw_set[phase_idx]
                        
                        send_intan_command(s, f"set {channel}.{phase_name}Polarity {phase['polarity']}")
                        send_intan_command(s, f"set {channel}.{phase_name}Amplitude {calc_amp}")
                        send_intan_command(s, f"set {channel}.{phase_name}Duration {phase_duration}")

                    # Arm channel
                    send_intan_command(s, f"set {channel}.StimEnable true")

                # 2. Trigger all armed channels simultaneously
                if TRIGGER_METHOD == 'TCP':
                    send_intan_command(s, "execute manualstimtrigger") 
                elif TRIGGER_METHOD == 'TTL':
                    fire_hardware_ttl()
                
                # 3. Disarm channels
                for channel in hw_channels:
                    send_intan_command(s, f"set {channel}.StimEnable false")
                
                time.sleep(current_isi)
                
            print("\nProtocol complete.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()