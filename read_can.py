import cantools
from can import Message
from can.interfaces.ixxat import IXXATBus, exceptions

import time

class pack_can_data:
    def __init__(self, baudrate):
        self.baudrate = baudrate
        self.bus = None
        self.can_command = Message(is_extended_id=False,
                                   arbitration_id=0x77F,
                                   dlc=0x08,
                                   data=[0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        
        self.cycle_time = time.time() + 5
        self.message = []
        self.data_dict = {}             #instance to store can data
        self.parameters = []            #List for appending battery parameters
        self.cell_voltages = []         #List for appending cell voltages
        self.cell_temperatures = []     #List for appending cell temperatures
        self.errors_events = []         #List for appending errors and events
        self.can_bus()

        self.decoded_data = {}
        # self.database_file()
    
    def can_bus(self):
        # try:
        #     self.bus = IXXATBus(channel=0,
        #                             can_filters=[{"can_id": 0x00, "can_mask": 0x00}],
        #                             bitrate=self.baudrate)
        # # self.bus = IXXATBus(channel=0, bitrate=500000)
    
        # # except exceptions.VCIError as e:
        # #     print("Error warning limit exceeded:", e)
        # #     # Handle the error appropriately, such as logging, retrying, or exiting the program 
        # except:
        #     pass


        # try:
        #     self.bus = IXXATBus(channel=0,
        #                         can_filters = [{"can_id": 0x00, "can_mask": 0x00}],
        #                         bitrate = self.baudrate)
        #     # Assuming IXXATBus raises VCIError if an error occurs
        # except exceptions.VCIError as e:
        #     print("Error occurred during CAN bus initialization:", e)
        #     # Handle the error appropriately, such as logging, retrying, or exiting the program
        #     # For example, you might raise the exception again to propagate it up the call stack
        #     raise

        # except Exception as e:
        #     print("Unexpected error: ", e)

        # else:
        #     pass

        # finally:
        #     pass

        self.bus = IXXATBus(channel=0,
                            can_filters=[{"can_id": 0x00, "can_mask": 0x00}],
                            bitrate = self.baudrate)

    def read_can_message(self):
        while True:
            try:
                self.message = self.bus.recv(timeout=2)
                self.decode_message()
                return self.decoded_data
            except exceptions.VCIError as e:
                print("Error:", e)
                time.sleep(1) # Wait for a short delay before retrying
            except TimeoutError:
                break # Exit the loop if the timeout is exceeded
    
    def database_file(self, filepath):
        self.database = cantools.database.load_file(filepath)
        self.iterate_messages()

    def iterate_messages(self):
        for message in self.database.messages:
            # Battery parameters
            if message.name in ["BMS_MSG_11_SID", "BMS_MSG_10_SID", "BMS_MSG_03_SID", "BMS_MSG_02_EID"]:
                for signal in message.signals:
                    self.parameters.append(signal.name)
            # Cell voltages 
            if message.name in ["BMS_MSG_CV0104_EID", "BMS_MSG_CV0508_EID", "BMS_MSG_CV0912_EID","BMS_MSG_CV1316_EID"]:
                for signal in message.signals:
                    self.cell_voltages.append(signal.name)
            # Cell temperatures 
            if message.name in ["BMS_MSG_CT0003_SID", "BMS_MSG_CT0407_SID"]:
                for signal in message.signals:
                    self.cell_temperatures.append(signal.name)
            # Errors and Warnings
            if message.name in ["BMS_MSG_13_SID"]:
                for signal in message.signals:
                    self.errors_events.append(signal.name)

            # Keeping all the parameters in the dictionary      
            for signal in message.signals:
                self.data_dict[signal.name] = ''

    def decode_message(self):
        try:
            self.decoded_data = self.database.decode_message(self.message.arbitration_id, self.message.data)
        except:
            pass
    
    def send_cyclic_message(self, message):
        while True:
            try:
                self.cycle_time = time.time() + 1
                #self.bus.send(message)
                self.bus.send(message, timeout = 2)
                break
            except exceptions.VCIError as e:
                print(f"Error: {e}")
                time.sleep(1) # Wait for a short delay before retrying
            except TimeoutError:
                break # Exit the loop if the timeout is exceeded

    def charging_enable_command(self):
        command = Message(is_extended_id=False,
                          arbitration_id=0x77F,
                          dlc=0x08,
                          data=[0x84,
                                0x08,
                                0x01,
                                0x00,
                                0x00,
                                0x00,
                                0x00,
                                0x00])
        
        self.send_cyclic_message(command)

    def discharging_enable_command(self):
        command = Message(is_extended_id=False,
                          arbitration_id=0x77F,
                          dlc=0x08,
                          data=[0x84,
                                0x08,
                                0x00,
                                0x00,
                                0x00,
                                0x00,
                                0x00,
                                0x00])
        
        self.send_cyclic_message(command)

    def charging_disable_command(self):
        command = Message(is_extended_id=False,
                          arbitration_id=0x77F,
                          dlc=0x08,
                          data=[0x84,
                                0x08,
                                0x00,
                                0x00,
                                0x00,
                                0x00,
                                0x00,
                                0x00])
        
        self.send_cyclic_message(command)

