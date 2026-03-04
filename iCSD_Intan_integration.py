import socket
import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import quantities as pq

homeDir = os.path.expanduser("~")
sys.path.insert(0,os.path.join(homeDir,'src','elephant','elephant','current_source_density_src'))
import icsd


# ==========================================
# 1. Configuration
# ==========================================
RHX_IP = '127.0.0.1'
DATA_PORT = 5001  # Only the Data Output server is needed

# Hardware Setup
NUM_CHANNELS = 32
SPACING_M = 0.0001
SAMPLE_RATE = 30000
CHANNELS_TO_USE = [24, 0, 7, 31, 25, 1, 6, 30, 26, 2, 5, 29, 27, 3, 4, 28]
NUM_CHANNELS_TO_USE = len(CHANNELS_TO_USE)

# Streaming & Visualization Parameters
DOWNSAMPLE_FACTOR = 30               # 30kHz -> 1kHz LFP rate
LFP_RATE = SAMPLE_RATE // DOWNSAMPLE_FACTOR
WINDOW_SEC = 1.0                     # How much time to show on screen
CHUNK_SEC = 0.1                      # How frequently the screen updates (100ms)

WINDOW_SAMPLES = int(LFP_RATE * WINDOW_SEC)
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_SEC)
LFP_CHUNK_SAMPLES = CHUNK_SAMPLES // DOWNSAMPLE_FACTOR
BYTES_PER_CHUNK = CHUNK_SAMPLES * NUM_CHANNELS * 2

# ==========================================
# 2. Mathematical Functions
# ==========================================
def compute_1d_csd(lfp_matrix, spacing):
    """Computes standard 1D CSD using the second spatial derivative."""
    # v_z_plus_1 = lfp_matrix[2:, :]
    # v_z = lfp_matrix[1:-1, :]
    # v_z_minus_1 = lfp_matrix[:-2, :]
    
    # csd = -1 * (v_z_plus_1 - 2 * v_z + v_z_minus_1) / (spacing ** 2)
    # return csd

    csd = icsd.DeltaiCSD(lfp_matrix*1E-6*pq.V,spacing*np.arange(NUM_CHANNELS_TO_USE)*pq.m)

    return csd.get_csd()

def process_intan_chunk(raw_bytes):
    """Converts raw TCP bytes to microvolts and downsamples to LFP rate."""
    data = np.frombuffer(raw_bytes, dtype=np.uint16)
    
    expected_length = NUM_CHANNELS * CHUNK_SAMPLES
    if len(data) > expected_length:
        data = data[:expected_length]
    elif len(data) < expected_length:
        data = np.pad(data, (0, expected_length - len(data)))
        
    # Reshape data (shape nChan x nTimeBin)
    data = data.reshape((CHUNK_SAMPLES, NUM_CHANNELS)).T

    # Convert to voltage
    voltage = (data.astype(np.float32) - 32768) * 0.195
    
    # Fast decimation for real-time visualization, LFP shape (nChanToUse x nDownsampledTimeBin)
    lfp = voltage[CHANNELS_TO_USE, ::DOWNSAMPLE_FACTOR]
    return lfp

# ==========================================
# 3. Execution & Visualization
# ==========================================
def main():
    plt.ion()
    fig, ax = plt.subplots(figsize=(10, 6))
    
    cax = ax.imshow(np.zeros((NUM_CHANNELS_TO_USE - 2, WINDOW_SAMPLES)), 
                    aspect='auto', cmap='jet', vmin=-1000, vmax=1000,
                    extent=(-WINDOW_SEC, 0, NUM_CHANNELS_TO_USE-1, 2))
    
    ax.set_title("Continuous Real-Time CSD")
    ax.set_xlabel("Time (seconds)")
    ax.set_ylabel("Channel (Depth)")
    fig.colorbar(cax, label="CSD Amplitude")
    
    # Initialize rolling LFP buffer (shape nChan x nTimeBin)
    lfp_buffer = np.zeros((NUM_CHANNELS_TO_USE, WINDOW_SAMPLES))

    print(f"Connecting to Intan RHX Data Server at {RHX_IP}:{DATA_PORT}...")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as data_sock:
            data_sock.connect((RHX_IP, DATA_PORT))
            print("Connected. Streaming CSD...")
            
            while True:
                # 1. Ingest exact byte chunk
                raw_data = bytearray()
                while len(raw_data) < BYTES_PER_CHUNK:
                    chunk = data_sock.recv(BYTES_PER_CHUNK - len(raw_data))
                    if not chunk:
                        raise ConnectionError("Intan Data Stream closed.")
                    raw_data.extend(chunk)

                # 2. Convert and downsample
                new_lfp = process_intan_chunk(raw_data)
                
                # 3. Roll buffer and insert new data
                lfp_buffer = np.roll(lfp_buffer, -LFP_CHUNK_SAMPLES, axis=1)
                lfp_buffer[:, -LFP_CHUNK_SAMPLES:] = new_lfp
                
                # 4. Compute CSD on the whole window
                csd_matrix = compute_1d_csd(lfp_buffer, SPACING_M)
                
                # 5. Update display
                cax.set_data(csd_matrix)
                
                # Auto-scale colorbar slightly to track spontaneous burst amplitudes
                current_max = np.max(np.abs(csd_matrix))
                if current_max > 0:
                    cax.set_clim(vmin=-current_max*0.8, vmax=current_max*0.8)
                
                fig.canvas.flush_events()

    except KeyboardInterrupt:
        print("\nStream stopped.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()