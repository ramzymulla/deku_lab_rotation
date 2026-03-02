import socket
import time

def fuzz_intan_parameters():
    # Common variations for Intan TCP syntax
    test_parameters = [
        "get a-000.StimStepSize",
        "get A-000.StimStepSize",
        "get a-000.FirstPhaseAmplitude",
        "get a-000.StimPhase1Amplitude",
        "get a-000.Phase1Amplitude",
        "get a-000.FirstPhaseDuration",
        "get a-000.NumberOfStimPulses",
        "get a-000.NumPulses",
        "get a-000.StimEnable",
        "get a-000.StimEnabled"
    ]

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect(('127.0.0.1', 5000))
            
            print("--- Testing Parameter Syntax ---")
            for cmd in test_parameters:
                s.sendall(f"{cmd}\n".encode('utf-8'))
                response = s.recv(1024).decode('utf-8').strip()
                
                if "Unrecognized Parameter" not in response:
                    print(f"SUCCESS: '{cmd}' -> {response}")
                else:
                    print(f"FAILED:  '{cmd}'")
                time.sleep(0.05)

            print("\n--- Testing Execute Commands ---")
            test_commands = [
                "execute manualstimtrigger",
                "execute manualstim",
                "execute triggerstim",
                "execute trigger",
                "set manualstimtrigger true",
                "set manualstimtrigger 1"
            ]
            
            for cmd in test_commands:
                s.sendall(f"{cmd}\n".encode('utf-8'))
                response = s.recv(1024).decode('utf-8').strip()
                if "Unrecognized Command" not in response and "Unrecognized Parameter" not in response:
                    print(f"SUCCESS: '{cmd}' -> {response}")
                else:
                    print(f"FAILED:  '{cmd}'")
                time.sleep(0.05)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fuzz_intan_parameters()