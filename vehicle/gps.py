import serial

port = "/dev/ttyACM0"
def parseGPS(data):
# print "raw" , data # prints raw data
    if data[0:6] == "$GNGLL":
        sdata = data.split(",")
        #if sdata[2] == 'V':
            #print("no GPSD data available")
            #return
        print("--Parsing GNGLL--,")
        time = sdata[5][0:2] + ":" + sdata[5][2:4] + ":" + sdata[5][4:6]
        lat = decode(sdata[1],sdata[2])
        lon = decode(sdata[3],sdata[4])
        
        
        
        #speed = sdata[7]
        #trCourse = sdate[8]
        #date = sdate[9][0:2] + "/" + sdata[9][2:4] + "/" + sdata[9][4:6]
        
        print("time : %s, lat : %s, lon : %s, " % (time, lat, lon))
        
def decode(coord, direction):
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

print("Receiving GPS data")
ser = serial.Serial(port,baudrate = 9600, timeout = 0.5)
while True:
    data = ser.readline()
    parseGPS(data)
        