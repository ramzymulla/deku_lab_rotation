import socket

def get_intan_parameters():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect(('127.0.0.1', 5000))
            
            s.sendall(b"get A-000\n")
            
            # 8192 bytes should be enough to capture the full parameter list
            response = s.recv(8192).decode('utf-8') 
            
            print("--- Valid Parameters for A-000 ---")
            print(response)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_intan_parameters()