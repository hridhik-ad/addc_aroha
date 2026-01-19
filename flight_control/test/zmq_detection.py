import zmq
import json

def receive_data():
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    
    # Connect to localhost since it's on the same machine
    # If using different machines, replace 'localhost' with the IP of the Hailo Pi
    socket.connect("tcp://localhost:5555")
    
    # Subscribe to all topics (empty string = everything)
    socket.subscribe("")
    
    print("Waiting for data on port 5555...")

    while True:
        try:
            # Receive JSON data directly
            data = socket.recv_json()
            
            # Print formatted JSON
            print(json.dumps(data, indent=2))
            
            # TODO: Add your logic here (e.g., move drone, log data, etc.)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    receive_data()