import pifacecad
import sys
import subprocess
import time
import requests
import json
import pprint
import os
import glob
import shutil

pi_home="/home/pi"
setup_home="/setup"

demozone=""

INIT=0
WIFI=1
HUESETUP=2
WSSETUP=3
currentInfoDisplay=0
maxInfoDisplay=3
buttonWaitingForConfirmation=-1

BUTTON1=0
BUTTON2=1
BUTTON3=2
BUTTON4=3
BUTTON5=4
BUTTONMIDDLE=5
BUTTONLEFT=6
BUTTONRIGHT=7

pi_img_version_file=pi_home+setup_home+"/PiImgVersion.dat"
pi_id_file=pi_home+setup_home+"/PiId.dat"
demozone_file=pi_home+setup_home+"/demozone.dat"
redirects_file=pi_home+setup_home+"/redirects"
dbcs_host_file=pi_home+setup_home+"/dbcs.dat"
hue_file=pi_home+setup_home+"/hue.dat"

GET_IP_CMD = "hostname --all-ip-addresses"
GET_WIFI_CMD = "sudo iwconfig wlan0 | grep ESSID | awk -F\":\" '{print $2}' | awk -F'\"' '{print $2}'"
RESET_WIFI_CMD = "sudo ifdown wlan0;sleep 5;sudo ifup wlan0"
CHECK_INTERNET_CMD = "sudo ping -q -w 1 -c 1 8.8.8.8 > /dev/null 2>&1 && echo U || echo D"
REBOOT_CMD = "sudo reboot"
POWEROFF_CMD = "sudo poweroff"
WS_STATUS_CMD = "curl -i -X GET http://localhost:3379/status 2>/dev/null"
HARDRESET_WS_CMD = "forever stop hueeventclient;forever start -a --uid hueeventclient /home/pi/node/hueeventclient/server.js -s `cat /home/pi/setup/eventserver.dat` -d `cat /home/pi/setup/demozone.dat`"
# HUE stuff
HUE_STATUS_CMD = "curl -i -X GET http://localhost:3378/hue/status 2>/dev/null"
HUE_PING_CMD = "curl -i -X GET http://localhost:3378/hue/ping 2>/dev/null"
RESET_HUE_CMD = "curl -i -X POST http://localhost:3378/hue/reset 2>/dev/null | grep HTTP | awk '{print $2}'"
HARDRESET_HUE_CMD = "forever stop hue;forever start --uid hue --append /home/pi/node/huebridge/server.js -h `cat /home/pi/setup/huebridge.dat` -t 1000"
HUE_LOCALON_CMD = "curl -i -X PUT http://localhost:3378/hue/ALL/ON/BLUE >/dev/null 2>&1"
HUE_LOCALOFF_CMD = "curl -i -X PUT http://localhost:3378/hue/ALL/OFF >/dev/null 2>&1"
piusergroup=1000

def getRest(message, url):
  #data_json = json.dumps(message)
  #headers = {'Content-type': 'application/json'}
  #response = requests.get(url, data=data_json, headers=headers)
  try:
    response = requests.get(url, verify=False, timeout=5)
    return response;
  except requests.exceptions.Timeout:
    dummy = requests.Response()
    dummy.status_code=408
    return dummy;

def postRest(message, url):
  #data_json = json.dumps(message)
  #headers = {'Content-type': 'application/json'}
  #response = requests.post(url, data=data_json, headers=headers)
  #print "Posting to "+url
  response = requests.post(url, verify=False, timeout=5)
  return response;

def read_file(filename):
  try:
    with open(filename, 'r') as f:
      first_line = f.readline()
      return(first_line)
  except (IOError):
      print "%s file not found!!!"
      return ""

def get_dbcs():
  global dbcs_host_file
  dbcs = read_file(dbcs_host_file)
  return(dbcs.rstrip())

def displayInfoRotation():
  global currentInfoDisplay
  global cad

  if currentInfoDisplay == INIT:
    initDisplay()
  elif currentInfoDisplay == WIFI:
    wifiDisplay()
  elif currentInfoDisplay == HUESETUP:
    hueSetupDisplay()
  elif currentInfoDisplay == WSSETUP:
    wsStatusDisplay()
  else:
    print "No more pages"

def initDisplay():
    global cad
    cad.lcd.clear()
    cad.lcd.set_cursor(0, 0)
    cad.lcd.write("Pi Version:"+getPiVersion())
    cad.lcd.set_cursor(0, 1)
    cad.lcd.write(getPiName())

def wifiDisplay():
  global cad
  cad.lcd.clear()
  cad.lcd.set_cursor(0, 0)
  cad.lcd.write("Wifi:"+get_my_wifi())
  cad.lcd.set_cursor(0, 1)
  cad.lcd.write(get_my_ip())
  cad.lcd.set_cursor(15, 1)
  cad.lcd.write(check_internet())

def hueSetupDisplay():
  global cad
  cad.lcd.clear()
  cad.lcd.set_cursor(0, 0)
  cad.lcd.write("GETTING HUE DATA")
  cad.lcd.set_cursor(0, 1)
  cad.lcd.write("PLEASE WAIT...")
  response = get_hue_status()
  responselines = response.splitlines()
  status = int(responselines[0].split(" ")[1])
  body = responselines[-1]
  on=0
  off=0
  reachable=0
  try:
      jsonBody = json.loads(body)
      for i, l in enumerate(jsonBody["lights"]):
          if jsonBody["lights"][l]["state"]["on"]:
              on = on + 1
          else:
              off = off + 1
          if jsonBody["lights"][l]["state"]["reachable"]:
              reachable = reachable + 1
  except:
      print "Not a valid JSON: %s" % body
  if status == 200:
      st = "ON"
  else:
      st = "OFF"
  line1 = "HUE:%s" % st
  line2 = "ON:%d OFF:%d RCH:%d" % (on,off,reachable)
  cad.lcd.clear()
  cad.lcd.set_cursor(0, 0)
  cad.lcd.write(line1)
  cad.lcd.set_cursor(0, 1)
  cad.lcd.write(line2)

def wsStatusDisplay():
  global cad
  cad.lcd.clear()
  cad.lcd.set_cursor(0, 0)
  cad.lcd.write("WS CONNECTION:")
  cad.lcd.set_cursor(0, 1)
  response = get_ws_status()
  cad.lcd.write(response.split()[-1])

def handleButton(button, screen):
  global buttonWaitingForConfirmation
  global dbcs
  global demozone
  global proxyport
#  print "Button %s at screen %s" % (button,screen)
  if screen == INIT:
    # 1: REBOOT
    # 2: POWEROFF
    # 5: CONFIRM
    if buttonWaitingForConfirmation != -1 and button == BUTTON5:
	  # Confirmation to previous command
	  if buttonWaitingForConfirmation == BUTTON1:
	    # REBOOT
	    CMD = REBOOT_CMD
	    msg = "REBOOTING"
	  else:
	    # POWEROFF
	    CMD = POWEROFF_CMD
	    msg = "HALTING SYSTEM"
	  cad.lcd.clear()
	  cad.lcd.set_cursor(0, 0)
	  cad.lcd.write(msg)
	  run_cmd(CMD)
    if button == BUTTON1 or button == BUTTON2:
	  buttonWaitingForConfirmation = button
	  if button == BUTTON1:
	     msg = "REBOOT REQUEST"
	  else:
	     msg = "POWEROFF REQUEST"
	  cad.lcd.clear()
	  cad.lcd.set_cursor(0, 0)
	  cad.lcd.write(msg)
	  cad.lcd.set_cursor(0, 1)
	  cad.lcd.write("CONFIRM RIGHTBTN")
    else:
	  if buttonWaitingForConfirmation != -1:
	    displayInfoRotation()
	    buttonWaitingForConfirmation = -1
  elif screen == WIFI:
    # 1: RESET WIFI
    # 5: CONFIRM
    if buttonWaitingForConfirmation != -1 and button == BUTTON5:
	  # Confirmation to previous command
	  buttonWaitingForConfirmation = -1
	  msg = "RESETING WIFI"
	  cad.lcd.clear()
	  cad.lcd.set_cursor(0, 0)
	  cad.lcd.write(msg)
	  run_cmd(RESET_WIFI_CMD)
	  displayInfoRotation()
    if button == BUTTON1:
	  buttonWaitingForConfirmation = button
	  msg = "WIFI RST REQUEST"
	  cad.lcd.clear()
	  cad.lcd.set_cursor(0, 0)
	  cad.lcd.write(msg)
	  cad.lcd.set_cursor(0, 1)
	  cad.lcd.write("CONFIRM RIGHTBTN")
    else:
	  if buttonWaitingForConfirmation != -1:
	    displayInfoRotation()
	    buttonWaitingForConfirmation = -1
  elif screen == HUESETUP:
    # 1: RESTART HUE
    # 2: TEST LIGHTS (ON and then OFF)
    # 5: CONFIRM for #1 and #2
    if buttonWaitingForConfirmation != -1 and button == BUTTON5:
	  # Confirmation to previous command
	  cad.lcd.clear()
	  cad.lcd.set_cursor(0, 0)
	  if buttonWaitingForConfirmation == BUTTON1:
	    # RESTART HUE
	    cad.lcd.write("RESETING HUE\nCONNECTION")
	    run_cmd(RESET_HUE_CMD)
	  else:
	    # TEST LIGHTS
	    cad.lcd.write("TESTING LIGHTS\nON & OFF")
	    run_cmd(HUE_LOCALON_CMD)
	    time.sleep(1)
	    run_cmd(HUE_LOCALOFF_CMD)
	  buttonWaitingForConfirmation = -1
	  displayInfoRotation()
    if button == BUTTON1:
	  buttonWaitingForConfirmation = button
	  msg = "HUE RESET REQ"
	  cad.lcd.clear()
	  cad.lcd.set_cursor(0, 0)
	  cad.lcd.write(msg)
	  cad.lcd.set_cursor(0, 1)
	  cad.lcd.write("CONFIRM RIGHTBTN")
    elif button == BUTTON2:
	  buttonWaitingForConfirmation = button
	  msg = "HUE LIGHTS TEST"
	  cad.lcd.clear()
	  cad.lcd.set_cursor(0, 0)
	  cad.lcd.write(msg)
	  cad.lcd.set_cursor(0, 1)
	  cad.lcd.write("CONFIRM RIGHTBTN")
  elif screen == WSSETUP:
    # 1: RESTART WS process
    # 5: CONFIRM for #1
    if buttonWaitingForConfirmation != -1 and button == BUTTON5:
	  # Confirmation to previous command
	  cad.lcd.clear()
	  cad.lcd.set_cursor(0, 0)
	  if buttonWaitingForConfirmation == BUTTON1:
	    # RESTART HUE
	    cad.lcd.write("RESETING WS\nCLIENT")
	    run_cmd(HARDRESET_WS_CMD)
	  buttonWaitingForConfirmation = -1
	  displayInfoRotation()
    if button == BUTTON1:
	  buttonWaitingForConfirmation = button
	  msg = "WS RESET REQ"
	  cad.lcd.clear()
	  cad.lcd.set_cursor(0, 0)
	  cad.lcd.write(msg)
	  cad.lcd.set_cursor(0, 1)
	  cad.lcd.write("CONFIRM RIGHTBTN")
    else:
	  if buttonWaitingForConfirmation != -1:
	    displayInfoRotation()
	    buttonWaitingForConfirmation = -1
  else:
    print "UNKNOWN SCREEN: %s" % screen

def buttonPressed(buttonId):
#  print "Event: "+str(event.pin_num)
  global currentInfoDisplay

  if buttonId == BUTTONLEFT:
    if currentInfoDisplay > 0:
      currentInfoDisplay=currentInfoDisplay-1
    else:
      currentInfoDisplay=maxInfoDisplay
    displayInfoRotation()
    buttonWaitingForConfirmation = -1
  elif buttonId == BUTTONRIGHT:
    if currentInfoDisplay < maxInfoDisplay:
      currentInfoDisplay=currentInfoDisplay+1
    else:
      currentInfoDisplay=0
    displayInfoRotation()
    buttonWaitingForConfirmation = -1
  elif buttonId == BUTTONMIDDLE:
    displayInfoRotation()
    buttonWaitingForConfirmation = -1
  elif buttonId >= BUTTON1 and buttonId <= BUTTON5:
    handleButton(buttonId,currentInfoDisplay)
  else:
    cad.lcd.set_cursor(0, 14)
#    cad.lcd.write(str(event.pin_num))

def run_cmd(cmd):
  msg = subprocess.check_output(cmd, shell=True).decode('utf-8')
  return msg

def get_my_wifi():
  ssid = run_cmd(GET_WIFI_CMD)[:-1]
  l = len(ssid)
  if l > 11:
      wifi = ssid[:4] + ".." + ssid[len(ssid)-5:]
  else:
      wifi = ssid
  return wifi

def get_my_ip():
  return run_cmd(GET_IP_CMD).split(" ")[0]

def get_hue_status():
  return run_cmd(HUE_PING_CMD)

def get_ws_status():
  try:
      return run_cmd(WS_STATUS_CMD)
  except:
      return "ERROR"

def check_internet():
  return run_cmd(CHECK_INTERNET_CMD)

def getPiName():
  with open(demozone_file, 'r') as f:
    return(f.readline())

def getPiVersion():
  with open(pi_img_version_file, 'r') as f:
    first_line = f.readline()
    return(first_line)

def getserial():
  # Extract serial from cpuinfo file
  cpuserial = "0000000000000000"
  try:
    f = open('/proc/cpuinfo','r')
    for line in f:
      if line[0:6]=='Serial':
        cpuserial = line[10:26]
    f.close()
  except:
    cpuserial = "ERROR000000000"
  return cpuserial

def getPiId():
  try:
    with open(pi_id_file, 'r') as f:
      first_line = f.readline().rstrip()
      return(first_line)
  except (IOError):
      print "%s file not found. Creating..." % pi_id_file
      serial = getserial()
      with open(pi_id_file,"w+") as f:
        f.write(serial)
      return(serial)

cad = pifacecad.PiFaceCAD()
cad.lcd.backlight_on()
cad.lcd.blink_off()
cad.lcd.cursor_off()

initDisplay()

FLAGS     = [0,0,0,0,0,0,0,0]
PREVFLAGS = [0,0,0,0,0,0,0,0]

while True:
    time.sleep(0.1)
    for i,e in enumerate(FLAGS):
        FLAGS[i] = cad.switches[i].value
    #print FLAGS
    for i,e in enumerate(FLAGS):
        if PREVFLAGS[i] == 1 and FLAGS[i] == 0:
            PREVFLAGS[i] = 0
            #print "PRESSED & UNPRESSED BUTTON #" + str(i)
            buttonPressed(i)
        else:
            PREVFLAGS[i] = FLAGS[i]

#listener = pifacecad.SwitchEventListener(chip=cad)
#for i in range(8):
#  listener.register(i, pifacecad.IODIR_FALLING_EDGE, buttonPressed)
#listener.activate()
