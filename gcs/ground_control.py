#!/usr/bin/env python3
import sys, getopt
import os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import socket
import time
import json
import threading
import iperf3
import requests
import csv
import uuid

BIND_INTERFACE = "eth0"
TELEM_IP = "231.3.3.230"
TELEM_PORT = 55000
GCS_INSTRUCTIONS_PORT = 55002

class GroundControl:
    '''
    Main class for ground control. Recieves telemetry from UAVs and creates flights with USS. 

    param onesky_api: object for pushing to the onesky apie
    param host_ip: ip address to be bound to the outgoing udp socket
    param silvus_ip: ip address written on the back of the silvus radio. only needed if measuring snr
    '''

    def __init__(self, onesky_api, host_ip, silvus_ip, killer):
        self.kill = killer
        
        #client for listening to incoming broadcasts from UAVS
        self.gcs_recv_telem_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            self.gcs_recv_telem_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except AttributeError:
            pass

        self.gcs_recv_telem_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)
        self.gcs_recv_telem_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)


        self.gcs_recv_telem_sock.setsockopt(socket.SOL_SOCKET, 25, str(BIND_INTERFACE + '\0').encode('utf-8'))
        self.gcs_recv_telem_sock.bind((TELEM_IP, TELEM_PORT))

        self.gcs_recv_telem_sock.setsockopt(socket.SOL_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(TELEM_IP) + socket.inet_aton(host_ip))

        #agents dictionary for keeping track of what UAVs are broadcasting
        self.agents = {}

        #onesky api obj
        self.onesky = onesky_api

        #create lock for agents dictionary
        self.agent_lock = threading.Lock()
        #create lock for using sending socket
        self.udp_send_lock = threading.Lock()
        #ip address for sending commands to vehicles
        self.gcs_send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)#, socket.IPPROTO_UDP)
        self.user_input = None
        self.ip = host_ip
        self.network_performance_csv_list = []
        #this is for measuring throughput with iperf3
        self.silvus_ip = silvus_ip
        if silvus_ip:
            self.init_silvus_requests()
        
                
    def run(self):

        threading.Thread(target=self.listen).start()
        threading.Thread(target=self.user_input_loop).start()
        threading.Thread(target=self.user_interface).start()
        threading.Thread(target=self.update_telemetry).start()  

    def listen(self):
        '''method for listening to telemetry broadcasts and updating telemetry to agents dictionary'''
        while not self.kill.kill:
            try:
                _data, addr = self.gcs_recv_telem_sock.recvfrom(1024)
                data = json.loads((_data).decode("utf-8"))
                with self.agent_lock:
                    _temp_agent_dict = self.agents.copy()
                with self.agent_lock:               
                    self.agents[data["name"]] = {"lon": data["lon"], "lat": data["lat"], "alt": data["alt"], "ip": data["ip"]}
            except Exception as e:
                print("Exception while listening: " + e)
                pass



    def update_telemetry(self):
        '''appends telemetry to the /flight/appenedtelemetry extension.'''
        while not self.kill.kill:
            with self.agent_lock:
                _temp_agent_dict = self.agents.copy()
                v = [value for key, value in _temp_agent_dict.items()]  

    def user_input_loop(self):
        '''method for taking in user input. user input is stored in user_input'''
        while not self.kill.kill:
            try:  
                self.user_input = input(">>> ")  
                time.sleep(.01)
            except EOFError:
                pass

    def user_interface(self):
        '''user interface method for interacting with gcs and other vehicles'''
        
        while not self.kill.kill:
            if self.user_input:
                with self.agent_lock:
                    _temp_agent_dict = self.agents.copy()
                try:
                    _user_input = self.user_input.split(" ")
                    if _user_input[0] == 'quit':                    
                        self.kill.kill = True                   
                    elif _user_input[0] == 'agents':
                        for uav in _temp_agent_dict:
                            print(">>> {} : {}".format(uav, _temp_agent_dict[uav]["ip"]))
                    elif _user_input[0] == 'measure':
                        if _user_input[1] in _temp_agent_dict:  
                            #send a udp broadcast to let the uav know we want to measure the throughput
                            self.send_instructions(_user_input[1], "measure_throughput", "null")    
                            time.sleep(.02)
                            #being measuring connection speed
                            threading.Thread(target=self.measure_connection_performance, 
                                args=(_user_input[1],_temp_agent_dict[_user_input[1]]["ip"])).start()
                    elif _user_input[0] in _temp_agent_dict:
                        if _user_input[1] == 'ip':
                            print(">>> " + _temp_agent_dict[_user_input[0]]["ip"])
                        if _user_input[1] == 'type':
                            print(">>> " + _temp_agent_dict[_user_input[0]]["vehicle_type"])
                        if _user_input[1] == 'loc':
                            print(">>> %s:%s" % (_temp_agent_dict[_user_input[0]]["lat"],_temp_agent_dict[_user_input[0]]["lon"]))

                    #for changing parameters on the uav. example: "set my_drone_name rate 1" with change my_drone_name's rate to 1 Hz
                    if _user_input[0] == 'set' and len(_user_input) == 4:
                        print("setting")
                                                # name          #parameter       #newvalue
                        self.send_instructions(_user_input[1], _user_input[2], _user_input[3])      
                except Exception as e:
                    print(e)

                self.user_input = None

    def send_instructions(self, name, parameter, new_value):
        '''
        method for sending instructions to target uav

        param name: name of the target uav
        param parameter: parameter to be changed/toggled
        param new_value: the new desired value for the parameter
        '''
        with self.agent_lock:
            _ip = self.agents[name]["ip"]
        with self.udp_send_lock:
            self.gcs_send_sock.sendto(json.dumps({"change": [parameter, new_value]}).encode("utf-8"),(_ip, GCS_INSTRUCTIONS_PORT))  
    


    def init_silvus_requests(self):
        '''method used if intending to measure snr from silvus radios'''
        
        self.silvus_session = requests.Session()
        self.streamscape_uri = "http://"+self.silvus_ip+"/streamscape_api"
        self.silvus_snr_measurment_msg = '''{"jsonrpc":"2.0", "method" : "network_status","id":"0"}'''


    def init_iperf3_client(self, ip):
        '''creates a client to measure throughput with iperf3. must be recreated for every new measurement (I think)'''

        iperf_client = iperf3.Client()
        iperf_client.duration = 2
        iperf_client.server_hostname = ip
        iperf_client.port = 6969
        iperf_client.protocol = 'udp'

        return iperf_client


    def measure_connection_performance(self, name, ip):
        '''method for grabbing snr and throughput to a uav and logging it into a .csv file'''

        #TODO: need to include the silvus id# in this later to target specific radios, since there's only one radio its not a problem
        print("Recording throughput and SNR from {} at {} \n>>> ".format(name,ip), end = '')    
        snr = 0
        throughput = 0
        fieldnames = ["lat","lon","alt","snr","Mbps"]
        if name not in self.network_performance_csv_list:
            self.network_performance_csv_list.append(name)
            with open('network_logs_{}.csv'.format(name), mode='w') as csv_file:
                 csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames, delimiter = ',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
                 csv_writer.writeheader()

        client = self.init_iperf3_client(ip)
        try:
            response = self.silvus_session.post(self.streamscape_uri, data=self.silvus_snr_measurment_msg, stream=True)
            data = json.loads(response.content.decode("utf-8"))
            snr = int(data["result"][2])
        except:
            pass
        try:                
            result = client.run()
            throughput = result.Mbps
        except Exception as e:
            print(e)
            pass

        with self.agent_lock:
            _temp_agent_dict = self.agents.copy()

        with open('network_logs_{}.csv'.format(name), mode='a') as csv_file:
            csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames, delimiter = ',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            csv_writer.writerow({'lat': _temp_agent_dict[name]["lat"], 'lon': _temp_agent_dict[name]["lon"], 'alt': _temp_agent_dict[name]["alt"], 'snr': snr, 'Mbps': throughput})

        print("Logged network performance from {} \n>>> ".format(name), end = '')


