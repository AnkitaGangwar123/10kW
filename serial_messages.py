import serial
import time

class arduino_comm:
    def __init__(self, com_port, baudrate):
        self.com_port =  com_port
        self.baudrate = baudrate
        self.arduino = None

        self.channel_dict = {"charge": "A",
                             "discharge": "B",
                             "ignition_on": "D",
                             "ignition_off": "C"}
        
        self.start_comm()

    def start_comm(self):
        self.arduino = serial.Serial(self.com_port)
        self.arduino.baudrate = self.baudrate

    def switch(self, command):
        time.sleep(3)
        try:
            self.arduino.write(bytes(self.channel_dict[command], 'ascii'))
        except serial.SerialException as e:
            print("Serial communication error:", e)
        except KeyError:
            print("Invalid command:", command)

# # Direct check
# A = arduino_comm("COM" , 9600)
# A.switch("ignition_on")
# time.sleep(3)
# A.switch("ignition_off")

        


