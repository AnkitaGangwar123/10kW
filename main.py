
import sys
from sys import argv
import os
from can import Message
from can.interfaces.ixxat import IXXATBus, exceptions
import time
from datetime import datetime
from os import getcwd
import cantools
import csv
import asyncio

from PySide2 import QtCore, QtGui, QtWidgets
from PySide2.QtCore import Qt, Signal, QThreadPool, QRunnable, Slot, QObject
from PySide2.QtGui import QIcon, QPixmap
from PySide2.QtWidgets import QApplication, QLineEdit, QWidget, QPushButton, QGroupBox, QGridLayout, \
    QVBoxLayout, QFileDialog, \
    QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QSplashScreen, QHeaderView, QAbstractScrollArea, \
    QAbstractItemView, QComboBox, QProgressBar, QLCDNumber
import serial.tools.list_ports as port_list

from read_can import pack_can_data
from serial_messages import arduino_comm

import openpyxl
from openpyxl import Workbook
from pathlib import Path
import pandas as pd

# Initializing the signal
class Signals(QObject):
    can_response = Signal(dict) #can_response is a signal for CAN_msgs
    state_signal = Signal(int) #state_signal is a signal for automatic switching logic
    append_signal = Signal(int) #append_signal is a signal for appending real time data in a file format

# Worker for CAN messages
class can_workers(QRunnable):
    def __init__(self, can_bus):
        super(can_workers, self).__init__()
        self.can_bus = can_bus
        self.signals = Signals()

    @Slot(dict)
    def run(self):
        while True:
            res = self.can_bus.read_can_message()
            self.signals.can_response.emit(res)

# Worker for Serial Communication messages
class message_worker(QRunnable):
    def __init__(self, serial_bus, init_command):
        super(message_worker, self).__init__()
        self.serial_bus = serial_bus
        self.init_command = init_command
    
    @Slot()
    def run(self):
        self.serial_bus.switch(self.init_command)

    def custom_command(self, command):
        self.serial_bus.switch(command)

# Worker for automatic switching logic
class state(QRunnable):
    def __init__(self):
        super(state, self).__init__()
        self.val = 1
        self.signals = Signals()

    @Slot(int)
    def run(self):
        # while True:
        self.signals.state_signal.emit(self.val)

# Worker for appending data
class append_data(QRunnable):
    def __init__(self):
        super(append_data, self).__init__()
        self.val = 1
        self.signals = Signals()
    
    @Slot(int)
    def run(self):
        self.signals.append_signal.emit(self.val)


class main_window(QWidget):
    
    def __init__(self):
        super().__init__()

        self.logo = "10KWh Diagnostic Tool"
        self.setWindowTitle("10KWh Diagnostic Tool")
        self.grid = QGridLayout()
        self.setStyleSheet('background-color: #FFFFFF')
        self.setFixedWidth(1230)
        self.setFixedHeight(800)
        
        # Drop down menu to select baudrate
        self.baud_rate_selector = QComboBox()
        #self.baud_rate_selector.setFixedWidth(150)
        self.baud_rate_selector.addItems(["Baudrate", "125000", "500000"])

        # Initially, set baudrate as zero, i.e. when nothing is selected
        self.baud_rate = 0

        # Hbox layout for selecting DBC
        self.load_dbc_layout = QHBoxLayout()
        self.load_dbc_box = QGroupBox()

        # push button for loading DBC
        self.loadDBCbtn = QPushButton(self)
        #self.loadDBCbtn.setFixedWidth(150)
        self.loadDBCbtn.setStyleSheet("background-color: #11F0D5")
        self.loadDBCbtn.setText("Load DBC")
        self.loadDBCbtn.clicked.connect(self.loadDBC)

        # main box for parameters, cv and ct
        self.param_cv_ct_layout = QHBoxLayout()
        self.param_cv_ct_box = QGroupBox("Parameters, Cell Voltages and Cell Temperature")
        self.param_cv_ct_box.setFixedWidth(1210)
        self.param_cv_ct_box.setFixedHeight(350)
        # Parameters Messages
        self.parameters = []
        # Cell voltages Messages
        self.cell_voltages = []
        # Cell temperatures Messages
        self.cell_temperatures = []
        # Error Events Messages
        self.errors_events = []

        # set to store parameters
        self.parameters_set = set()

        # hbox for battery parameters
        self.parameters_box_layout = QHBoxLayout()
        self.parameters_box = QGroupBox("Parameters")
        self.parameters_box.setFixedWidth(440)
        self.parameters_box.setFixedHeight(300)

        # table widget for parameters table
        self.parameters_table_widget = QTableWidget()

        # set to store cell voltages
        self.cell_voltages_set = set()

        # hbox for cell voltages
        self.cell_voltages_box_layout = QHBoxLayout()
        self.cell_voltages_box = QGroupBox("Cell Voltages")
        self.cell_voltages_box.setFixedWidth(440)
        self.cell_voltages_box.setFixedHeight(300)

        # table widget for cell voltages
        self.cell_voltages_table_widget = QTableWidget()

        # set to store cell temperature
        self.cell_temperature_set = set()

        # hbox for cell temperature
        self.cell_temperature_box_layout = QHBoxLayout()
        self.cell_temperature_box = QGroupBox("Cell Temperatures")
        self.cell_temperature_box.setFixedWidth(235)
        self.cell_temperature_box.setFixedHeight(300)

        # table widget for cell temperatures
        self.cell_temperature_table_widget = QTableWidget()

        # set to store events and errors name from dbc file
        self.events_errors_set = set()

        # hbox for displaying events and errors
        self.events_errors_box_layout = QHBoxLayout()
        self.events_errors_box = QGroupBox("Events and Errors")
        self.events_errors_box.setFixedWidth(1210)
        self.events_errors_box.setFixedHeight(350)

        #table widget for events and errors
        self.events_errors_table_widget = QTableWidget()

        self.data_dict = {}

        self.can_bus = None
        self.threadpool = QThreadPool()

        # For automatic switching
        self.charging_flag = False
        self.discharging_flag = True
        self.charging_limit_flag = False
        self.discharging_command_flag = False
        self.initial_charging_flag = False

        # Flags for automatic switching worker
        self.state_thread_flag = False
        self.count = 0
        #self.arduino = arduino_comm()

        # Flags for automatic data appending worker
        self.append_thread_flag = False
        self.append_count = 0
        self.daily_logs_path = "day_wise_logs"
        self.last_log_time = None
        self.last_log_date = None

        self.baudrate = 9600 # Arduino comm. baudrate 
        self.portList() # List all the connected ports
        self.start_serial_comm() #Start serial communication with Arduino
        self.gridlayout()

    def portList(self):
            """
            To read all serial ports and append them in port selector list.
            """
            ports = list(port_list.comports())
            portsArray = []
            for p in ports:
                portsArray.append(str(p))

            #print("All connected ports are: " , portsArray)

            self.auto_select_port(portsArray)

    def auto_select_port(self, all_ports):
            """
            Automatically select arduino based on substing in port list.
            """
            arduino_substring = "Arduino Mega 2560"
            #rs485_substring = "Standard Serial over Bluetooth link"

            for j in all_ports:
                
                if arduino_substring in j:
                    self.arduino_port = j
            
                # if rs485_substring in j:
                #     rs485_port = j
                else:
                    #print("No connected arduino port.")
                    pass
                
            # arduino = self.arduino_port.split(" ")
            # print("Arduino port: ", arduino[0])

        # rs485 = rs485_port.split(" ")
        # print("RS485 port: ", rs485[0])


    def gridlayout(self):
        self.grid.addWidget(self.load_dbc_baudrate_box(), 0, 0)
        self.grid.addWidget(self.param_cv_ct_show(), 1, 0)
        self.grid.addWidget(self.events_errors_show(), 2, 0)

        self.setLayout(self.grid)

    def start_serial_comm(self):
        arduino_port = self.arduino_port.split(" ")
        self.serial_bus = arduino_comm(arduino_port[0] , self.baudrate)
        self.start_serial_thread()

    def start_serial_thread(self):
        self.serial = message_worker(self.serial_bus, "ignition_on")
        self.threadpool.start(self.serial)

    def loadDBC(self):
        self.filepath, filter = QFileDialog.getOpenFileName(parent=self, caption='Open File', dir='.', filter='*.dbc')
        self.baud_rate = int(self.baud_rate_selector.currentText())
        self.baud_rate_selector.setEnabled(False) 

        self.can_bus = pack_can_data(int(self.baud_rate))

        self.can_bus.database_file(self.filepath)

        #print("All DBC parameters:", self.can_bus.data_dict)

        # Always keep the parameters sorted. 
        self.parameters = sorted(self.can_bus.parameters)
        #print("Battery parameters list: ", self.can_bus.parameters)

        self.cell_voltages = sorted(self.can_bus.cell_voltages)
        #print("Cell voltages list: ", self.can_bus.cell_voltages)

        self.cell_temperatures = sorted(self.can_bus.cell_temperatures)
        #print("Cell temperatures list: ", self.can_bus.cell_temperatures)

        self.errors_events = sorted(self.can_bus.errors_events)
        #print("Errors events list: ", self.can_bus.errors_events)

        self.parameters_table()
        self.cell_temperature_table()
        self.cell_voltages_table()
        self.events_errors_table()

        # Calling both the worker signals on clicking the Load DBC button in the UI
        self.can_bus_worker()
    
    def can_bus_worker(self):
        self.can_worker = can_workers(self.can_bus)
        self.can_worker.signals.can_response.connect(self.update_data)
        self.threadpool.start(self.can_worker)
        
    def update_data(self, data_dict):
        """
        Updated dictionary it's receiving from the above can-worker signal
        """
        # print("data dict ", data_dict) 

        # Updating the dictionary 
        self.data_dict.update(data_dict)

        # # Sorting the dictionary by via it's keys
        # self.data_dict = dict(sorted(self.data_dict.items()))

        self.update_parameter_data()
        self.update_cell_voltages()
        self.update_cell_temperatures()
        self.update_event_errors()

        if self.state_thread_flag == False:
            self.count = self.count + 1
            if self.count >= 10:
                self.check_state_thread()
                #self.state_thread_flag = True
        
        if self.append_thread_flag == False:
            self.append_count += 1
            if self.append_count >= 10:
                self.append_data_thread()

        # Function to automatically switch the setup
        # self.check_state()
                
    def append_data_thread(self):
        self.append_data_th = append_data()
        self.append_data_th.signals.append_signal.connect(self.append_dict_to_excel)
        self.threadpool.start(self.append_data_th)

    def check_state_thread(self):
        self.check_state_th = state()
        self.check_state_th.signals.state_signal.connect(self.check_state)
        self.threadpool.start(self.check_state_th)

    def check_state(self, val):
        #print(val)
        async def discharging_delay():
            #await asyncio.sleep(900) #15mins. delay
            await asyncio.sleep(900)

        async def charging_delay():
            #await asyncio.sleep(600) #10mins. delay
            await asyncio.sleep(600)

        if ((int(self.data_dict[self.parameters[2]]) >= 10) and (int(self.data_dict[self.parameters[2]]) <= 100) and (self.discharging_flag == True) and (self.charging_limit_flag == False)):
            print("Initial discharging.")
            # self.arduino.switch("discharge")
            self.serial.custom_command("discharge")
            time.sleep(1)
            self.can_bus.discharging_enable_command()
            time.sleep(1)
            self.serial.custom_command("ignition_on")
            time.sleep(1)
            self.charging_flag = True
            self.discharging_flag = False
        
        if (((int(self.data_dict[self.parameters[2]])) == 10) and (self.charging_flag == True) and (self.discharging_flag == False)):
            self.serial.custom_command("ignition_off")
            print("Start discharging delay 1")
            asyncio.run(discharging_delay())
            print("End discharging delay 1")

            #Toggle Ignition
            self.serial.custom_command("ignition_on")
            time.sleep(2)
            self.serial.custom_command("ignition_off")

        if (((int(self.data_dict[self.parameters[2]]) == 0) or (int(self.data_dict[self.parameters[2]]) <= 10)) and (self.charging_flag == True) and (self.discharging_flag == False)):
            print("Switch to charging.")
            self.serial.custom_command("charge")
            time.sleep(1)
            self.can_bus.charging_enable_command()
            time.sleep(1)
            self.serial.custom_command("ignition_off")
            time.sleep(1)
            self.charging_flag = False
            self.discharging_flag = True
            self.charging_limit_flag = True

        if (((int(self.data_dict[self.parameters[2]])) == 100) and (self.charging_flag == False) and (self.discharging_flag == True) and (self.charging_limit_flag == True)):
            # self.serial.custom_command("ignition_off")
            # time.sleep(1)
            # self.can_bus.charging_disable_command()
            # time.sleep(1)
            # print("Start charging delay")
            # asyncio.run(charging_delay())
            # print("End charging delay")

            # #Turn ON Ignition
            # self.serial.custom_command("ignition_on")

            print("Switch to discharging 2.")
            self.can_bus.discharging_enable_command()
            time.sleep(1)
            self.serial.custom_command("ignition_on")
            time.sleep(45)
            #self.charging_limit_flag = False
            self.discharging_command_flag = True
            time.sleep(2)

        # if ((int(self.data_dict[self.parameters[2]]) >= 95) and (self.charging_limit_flag == True)):
        #     print("Switch to discharging 2.")
        #     self.can_bus.discharging_enable_command()
        #     time.sleep(1)
        #     self.serial.custom_command("ignition_on")
        #     time.sleep(45)
        #     self.charging_limit_flag = False
        #     self.discharging_command_flag = True
        #     time.sleep(2)

        if ((int(self.data_dict[self.parameters[2]]) >= 10) and (int(self.data_dict[self.parameters[2]]) <= 100) and (self.discharging_flag == True) and (self.charging_flag == False) and (self.discharging_command_flag == True)):
            print("Switch to discharging 3.")
            time.sleep(1)
            self.serial.custom_command("discharge")
            time.sleep(1)
            self.charging_flag = True
            self.discharging_flag = False


    def load_dbc_baudrate_box(self):
        self.load_dbc_layout.addWidget(self.baud_rate_selector)
        self.load_dbc_layout.addWidget(self.loadDBCbtn)
        self.load_dbc_box.setLayout(self.load_dbc_layout)

        return self.load_dbc_box

    def param_cv_ct_show(self):
        self.param_cv_ct_layout.addWidget(self.parameters_table_box())
        self.param_cv_ct_layout.addWidget(self.cell_voltages_table_box())
        self.param_cv_ct_layout.addWidget(self.cell_temperature_table_box())
        self.param_cv_ct_box.setLayout(self.param_cv_ct_layout)

        return self.param_cv_ct_box

    def parameters_table_box(self):
        self.parameters_box_layout.addWidget(self.parameters_table())
        self.parameters_box.setLayout(self.parameters_box_layout)

        return self.parameters_box

    def parameters_table(self):
        self.parameters_table_widget.setRowCount(8)
        self.parameters_table_widget.setColumnCount(4)
        self.parameters_table_widget.setColumnWidth(0, 120)
        self.parameters_table_widget.setColumnWidth(1, 70)
        self.parameters_table_widget.setColumnWidth(2, 120)
        self.parameters_table_widget.setColumnWidth(3, 70)
        self.parameters_table_widget.verticalHeader().setVisible(False)
        self.parameters_table_widget.horizontalHeader().setVisible(False)

        for i in range(0, len(self.parameters)):
            if i < 8:
                self.parameters_table_widget.setItem(i, 0, QTableWidgetItem(self.parameters[i]))
            else:
               self.parameters_table_widget.setItem(i - 8, 2, QTableWidgetItem(self.parameters[i]))

        return self.parameters_table_widget
    
    def update_parameter_data(self):
        for i in range(0, len(self.parameters)):
            if i < 8:
                try:
                    self.parameters_table_widget.setItem(i, 1, QTableWidgetItem(str(self.data_dict[self.parameters[i]])))
                except:
                    pass
            else:
               try:
                   self.parameters_table_widget.setItem(i-8, 3, QTableWidgetItem(str(self.data_dict[self.parameters[i]])))
               except:
                   pass
    
    def cell_voltages_table_box(self):
        self.cell_voltages_box_layout.addWidget(self.cell_voltages_table())
        self.cell_voltages_box.setLayout(self.cell_voltages_box_layout)

        return self.cell_voltages_box
    
    def cell_voltages_table(self):
        self.cell_voltages_table_widget.setRowCount(8)
        self.cell_voltages_table_widget.setColumnCount(4)
        self.cell_voltages_table_widget.setColumnWidth(0, 120)
        self.cell_voltages_table_widget.setColumnWidth(1, 70)
        self.cell_voltages_table_widget.setColumnWidth(2, 120)
        self.cell_voltages_table_widget.setColumnWidth(3, 70)
        self.cell_voltages_table_widget.verticalHeader().setVisible(False)
        self.cell_voltages_table_widget.horizontalHeader().setVisible(False)

        for i in range(0, len(self.cell_voltages)):
            if i < 8:
                self.cell_voltages_table_widget.setItem(i, 0, QTableWidgetItem(self.cell_voltages[i]))
            else:
               self.cell_voltages_table_widget.setItem(i - 8, 2, QTableWidgetItem(self.cell_voltages[i]))

        return self.cell_voltages_table_widget
    
    def update_cell_voltages(self):
        for i in range(0, len(self.cell_voltages)):
            if i < 8:
                try:
                    self.cell_voltages_table_widget.setItem(i, 1, QTableWidgetItem(str(self.data_dict[str(self.cell_voltages[i])])))
                except:
                    pass
            else:
               try:
                   self.cell_voltages_table_widget.setItem(i - 8, 3, QTableWidgetItem(str(self.data_dict[self.cell_voltages[i]])))
               except:
                   pass
    
    def cell_temperature_table_box(self):
        self.cell_temperature_box_layout.addWidget(self.cell_temperature_table())
        self.cell_temperature_box.setLayout(self.cell_temperature_box_layout)

        return self.cell_temperature_box

    def cell_temperature_table(self):
        self.cell_temperature_table_widget.setRowCount(8)
        self.cell_temperature_table_widget.setColumnCount(2)
        self.cell_temperature_table_widget.setColumnWidth(0, 120)
        self.cell_temperature_table_widget.setColumnWidth(1, 50)
        self.cell_temperature_table_widget.verticalHeader().setVisible(False)
        self.cell_temperature_table_widget.horizontalHeader().setVisible(False)

        for i in range(0, len(self.cell_temperatures)):
            if i < 8:
                self.cell_temperature_table_widget.setItem(i, 0, QTableWidgetItem(self.cell_temperatures[i]))
            else:
               self.cell_temperature_table_widget.setItem(i - 8, 2, QTableWidgetItem(self.cell_temperatures[i]))

        return self.cell_temperature_table_widget
    
    def update_cell_temperatures(self):
        for i in range(0, len(self.cell_temperatures)):
            if i < 8:
                try:
                    self.cell_temperature_table_widget.setItem(i, 1, QTableWidgetItem(str(self.data_dict[self.cell_temperatures[i]])))
                except:
                    pass
            else:
               try:
                   self.cell_temperature_table_widget.setItem(i -8, 3, QTableWidgetItem(str(self.data_dict[self.cell_temperatures[i]])))
               except:
                   pass

        return self.cell_temperature_table_widget
    
    def events_errors_show(self):
        self.events_errors_box_layout.addWidget(self.events_errors_table())
        self.events_errors_box.setLayout(self.events_errors_box_layout)

        return self.events_errors_box
    
    def events_errors_table(self):
        self.events_errors_table_widget.setRowCount(8)
        self.events_errors_table_widget.setColumnCount(8)
        self.events_errors_table_widget.verticalHeader().setVisible(False)
        self.events_errors_table_widget.horizontalHeader().setVisible(False)

        for i in range(0, 8):
            for j in range(0, 8):
                try:
                    self.events_errors_table_widget.setItem(i, j, QTableWidgetItem(self.errors_events[i+8*j]))
                except:
                    pass
     
        return self.events_errors_table_widget
    
    def update_event_errors(self):

        for i in range(0, 8):
            for j in range(0, 8):
                try:
                    err = self.data_dict[self.errors_events[i + 8*j]]
                    if int(err) == 0:
                         self.events_errors_table_widget.item(i, j).setBackgroundColor("Green")
                    elif int(err) == 1:
                        self.events_errors_table_widget.item(i, j).setBackgroundColor("Red")
                except:
                    pass
    
    def append_dict_to_excel(self, val):
        try:
            current_time = time.time()
            current_date = datetime.now().date()
            # Construct filename with current date
            filename = f"{current_date}.csv"
            filepath = os.path.join(self.daily_logs_path, filename)

            # Create the CSV file if it doesn't exist
            if not os.path.exists(filepath):
                with open(filepath, 'w', newline='') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=self.data_dict.keys())
                    writer.writeheader()

            # Convert scalar values to strings
            for key, value in self.data_dict.items():
                if not isinstance(value, list):
                    self.data_dict[key] = str(value)

            # Append the data to the CSV file if one second passed since the last log
            if self.last_log_date != current_date:
                self.last_log_date = current_date

            if self.last_log_time is None or current_time - float(self.last_log_time) >= 1:
                with open(filepath, 'a', newline='') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=self.data_dict.keys())
                    writer.writerow(self.data_dict)
                #print("Data appended successfully to", filepath)
                self.last_log_time = current_time

        except Exception as e:
            #print("An error occurred:", e)
            pass
    

myApp = QApplication(argv)
window = main_window()
window.setWindowFlags(Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint)
window.show()
myApp.exec_()
# os.exit(myApp.exec_())


