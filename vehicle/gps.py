#!/usr/bin/env python3

import serial

class GPS:
    def __init__(self):
        self.port = "/dev/ttyACM0"
        self.latitude = ""
        self.longitude = ""
        self.altitude = ""
        self.debug=1

    def startRead(self, debug):
        self.debug = debug
        if self.debug == 1: print("Reading GPS")
        ser = serial.Serial(self.port,baudrate = 9600, timeout = 0.5)
        while True:
            data = str(ser.readline(), 'utf-8')
            self.parseGPS(data)
        
    def parseGPS(self,data):
    # print "raw" , data # prints raw data
        if data[0:6] == "$GNGGA":
            ## SAMPLE: $GNGGA,122553.00,4310.34095,N,07504.99230,W,2,12,0.92,340.9, M,-34.1,M ,  ,0000*76
            ## FIELDS:    0      1           2     3      4      5 6  7   8    9   10  11   12 13   14
            sdata = data.split(",")

            if self.debug == 1: print("--Parsing GNGGA--,")
            
            time = sdata[1][0:2] + ":" + sdata[1][2:4] + ":" + sdata[1][4:6]
            
            self.latitude = self.decode(sdata[2],sdata[3])
            self.longitude = self.decode(sdata[4],sdata[5])
            self.altitude = sdata[9]
            
            if self.debug == 1: print("time : %s, lat : %s, lon : %s, alt: %s" % (time, self.latitude, self.longitude, self.altitude))
            
    def decode(self,coord, direction):
        x = coord.split(".")
        head = x[0]
        tail = x[1]
        deg = head[0:-2]
        min = head[-2:]
        secs = str(float("." + tail) * 60)
        
        dirlbl = ""
        if direction == "W" or direction == "S":
            dirlbl = "-"
        
        return dirlbl + deg + ":" + min + ":" + secs
    
    def getTelemetry(self):
        return (self.longitude, self.latitude, self.altitude)
        