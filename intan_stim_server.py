import socket
import time
import random
import itertools

# ==========================================
# 1. Hardware & Trigger Configuration
# ==========================================
RHX_IP = '127.0.0.1'
RHX_PORT = 5000

# Set to 'TCP' for software triggering, or 'TTL' for hardware synchronization
TRIGGER_METHOD = 'TCP'  

# ==========================================
# 2. Timing & Parameter Space
# ==========================================
ISI_BASE = 2.0        # Seconds between stimuli
ISI_JITTER = 0.5      # Max random time added to ISI

CHANNELS = ['A-000', 'A-001']
BASE_AMPLITUDES_UA = [10, 50]         
BASE_PULSE_WIDTHS_US = [100, 200]  

# Define your custom waveform shapes here. 
# Multipliers allow you to easily scale asymmetric phases based on the BASE values above.
WAVEFORMS = [
    {
        'name': 'Symmetric Biphasic Cathodic-First',
        'phases': [
            {'name': 'FirstPhase', 'polarity': 'Negative', 'amp_mult': 1.0, 'width_mult': 1.0},
            {'name': 'SecondPhase', 'polarity': 'Positive', 'amp_mult': 1.0, 'width_mult': 1.0},
            {'name': 'ThirdPhase', 'polarity': 'Positive', 'amp_mult': 0.0, 'width_mult': 0.0} # 0 duration turns phase off
        ]
    },
    {
        'name': 'Asymmetric Monophasic Anodic',
        'phases': [
            {'name': 'FirstPhase', 'polarity': 'Positive', 'amp_mult': 1.0, 'width_mult': 1.0},
            {'name': 'SecondPhase', 'polarity': 'Positive', 'amp_mult': 0.0, 'width_mult': 0.0},
            {'name': 'ThirdPhase', 'polarity': 'Positive', 'amp_mult': 0.0, 'width_mult': 0.0}
        ]
    }
]

# ==========================================
# 3. Execution Functions
# ==========================================
def send_intan_command(sock, command):
    """Sends a command string to the Intan TCP server."""
    sock.sendall(f"{command};\n".encode('utf-8'))
    try:
        return sock.recv(1024).decode('utf-8').strip()
    except socket.timeout:
        return "Timeout"

def fire_hardware_ttl():
    """
    Placeholder for your hardware TTL logic. 
    e.g., nidaqmx task, or serial write to an Arduino.
    """
    # import nidaqmx
    # with nidaqmx.Task() as task:
    #     task.do_channels.add_do_chan("Dev1/port0/line0")
    #     task.write(True)
    #     task.write(False)
    print("      [Hardware TTL Fired]")

def main():
    # Generate all possible combinations
    stim_combinations = list(itertools.product(CHANNELS, WAVEFORMS, BASE_PULSE_WIDTHS_US, BASE_AMPLITUDES_UA))
    random.shuffle(stim_combinations)
    
    print(f"Generated {len(stim_combinations)} randomized stimulation trials.")

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect((RHX_IP, RHX_PORT))
            print("Connected to Intan RHX.\n")

            for i, (channel, waveform, base_pw, base_amp) in enumerate(stim_combinations, 1):
                current_isi = ISI_BASE + random.uniform(0, ISI_JITTER)
                
                print(f"[{i}/{len(stim_combinations)}] {channel} | {waveform['name']} | Base: {base_amp}uA, {base_pw}us")

                # 1. Enable channel to accept parameters
                send_intan_command(s, f"set {channel}.StimStepSize 1.0") 

                # 2. Iterate through the phases in the selected waveform dictionary
                for phase in waveform['phases']:
                    phase_name = phase['name']
                    calc_amp = base_amp * phase['amp_mult']
                    calc_pw = base_pw * phase['width_mult']
                    
                    send_intan_command(s, f"set {channel}.{phase_name}Polarity {phase['polarity']}")
                    send_intan_command(s, f"set {channel}.{phase_name}Amplitude {calc_amp}")
                    send_intan_command(s, f"set {channel}.{phase_name}Duration {calc_pw}")

                # 3. Arm the channel
                send_intan_command(s, f"set {channel}.StimEnable true")

                # 4. Trigger the Stimulation
                if TRIGGER_METHOD == 'TCP':
                    send_intan_command(s, "execute manualstimtrigger") 
                elif TRIGGER_METHOD == 'TTL':
                    fire_hardware_ttl()
                
                # 5. Disarm channel & Wait for ISI
                send_intan_command(s, f"set {channel}.StimEnable false")
                time.sleep(current_isi)
                
            print("\nProtocol complete.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
