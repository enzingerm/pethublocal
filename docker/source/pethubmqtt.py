#!/usr/bin/env python3
"""
   Pet Hub MQTT to Parse MQTT messages from the Hub and create Home Assistant discovery topics and push to home assistant mqtt.

   Copyright (c) 2021, Peter Lambrechtsen (peter@crypt.nz)

   This program is free software; you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation; either version 3 of the License, or
   (at your option) any later version.

   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.

   You should have received a copy of the GNU General Public License
   along with this program; if not, write to the Free Software Foundation,
   Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
"""

import sys
sys.path.append('/code/source')

#import logging
import json, ast, os, logging, sys, socket, pathlib
import pethubpacket as phlp
import paho.mqtt.client as mqtt
from pethubconst import *
from box import Box
#from pathlib import Path
from datetime import datetime
from configparser import ConfigParser

#Debugging mesages
PrintDebug = True #Print debugging messages
StateOnStartup = False #Query all known devices state on startup

#Fixed values for MQTT Topic Names
#Topic for all messages generated by the hub, with the devices being a sub topic which is how the hub and devices work so can't be changed.
hub_topic = 'pethublocal/messages'
#Home Assistant MQTT Discovery Sensor topic for pets being added
ha_pet_topic = 'homeassistant/sensor/pethub/pet_'
#Home Assistant MQTT Discovery Sensor topic for devices being added
d_sen_t = 'homeassistant/sensor/pethub/device_'
#Home Assistant MQTT Discovery Switch topic for devices being added with on/off switch
d_swi_t = 'homeassistant/switch/pethub/device_'
#Home Assistant topics to subscribe to as we care about the state and set messages from HA.
hastatetopic="homeassistant/+/pethub/+/state"
hasettopic="homeassistant/+/pethub/+/set"

#Dict to hold all states in memory
states=Box()

#logger = logging.getLogger(__file__)
#logging.basicConfig(level=logging.INFO)

#Setup Logging framework to log to console without timestamps and log to file with timestamps
log = logging.getLogger('')
log.setLevel(logging.DEBUG)
format = logging.Formatter("%(asctime)s - [%(levelname)-5.5s] - %(message)s")
ch = logging.StreamHandler(sys.stdout)
log.addHandler(ch)
pathlib.Path("log").mkdir(exist_ok=True)
fh = logging.FileHandler('log/pethubmqtt-{:%Y-%m-%d}.log'.format(datetime.now()))
fh.setFormatter(format)
log.addHandler(fh)

#MQTT for pethublocal/hub and home assistant where the hub messages go, the broker sends the messages from the docker hub mqtt instance to your home assistant instance in the mosquitto.conf broker setting
if os.environ.get('HAMQTTIP') is not None:
    hamqttip = os.environ.get('HAMQTTIP')
    log.info("HAMQTTIP environment: "+hamqttip)
else:
    parser = ConfigParser()
    if pathlib.Path("../config.ini").exists():
        with open("../config.ini") as stream:
            parser.read_string("[top]\n" + stream.read())
            if 'top' in parser and 'HAMQTTIP' in parser['top']:
                log.info("HAMQTTIP from config.ini")
                hamqttip = parser['top']['HAMQTTIP']
    else:
        try:
            result = socket.gethostbyname_ex('mqtt')
        except:
            log.info("You're trying to run pethubmqtt.py locally but need to set the environment variable HAMQTTIP to point to your home assistant MQTT instance so exiting")
            exit(1)
        else:
            log.info("HAMQTTIP has not been set so connecting to internal mqtt instance")
            mqtthost = 'mqtt' #Connect to internal mqtt instance if the home assistant one wasn't specified in the env
            mqttport = 1883

if ':' in hamqttip:
    hamqttipsplit = hamqttip.split(':')
    mqtthost = hamqttipsplit[0]
    mqttport = int(hamqttipsplit[1])
else:
    mqtthost = hamqttip
    mqttport = 1883
if PrintDebug:
    log.debug("HAMQTT Host: "+mqtthost)
    log.debug("HAMQTT Port: "+str(mqttport))

# Feeder
def on_hub_message(client, obj, msg):
    msgsplit = msg.payload.decode("utf-8").split()
    if msgsplit[1] != "1000":
        pethub=phlp.decodehubmqtt(msg.topic,msg.payload.decode("utf-8"))
        log.info("Hub Parsed: "+json.dumps(pethub))
        if PrintDebug:
            log.info("Hub    Raw: "+msg.topic+" "+str(msg.qos)+" "+msg.payload.decode("utf-8"))
        devid="hub"
        for values in pethub['message'][-1:][0].values():
            if "State" in values: #Hub State Change
                mv = next((fm for fm in pethub['message'] if fm['OP'] == "State"), None)
                states.hub.State = mv['State']
                hasepub(devid+'/status',json.dumps(states.hub))
            if "Uptime" in values: #Update Uptime
                mv = next((fm for fm in pethub['message'] if fm['OP'] == "Uptime"), None)
                states.hub.Uptime = mv['Uptime']+" Mins"
                hasepub(devid+'/status',json.dumps(states.hub))

# Pet Door
def on_petdoor_hub_message(client, obj, msg):
    msgsplit = msg.payload.decode("utf-8").split()
    if msgsplit[1] != "1000":
        #We get messages being reflected so ignore the command messages

        pethub=phlp.decodehubmqtt(msg.topic,msg.payload.decode("utf-8"))
        mac_address = msg.topic.split("/")[-1]
        if PrintDebug:
            log.info("Door    Raw: "+msg.topic+" "+str(msg.qos)+" "+msg.payload.decode("utf-8"))
        log.info("Door Parsed: "+json.dumps(pethub))
        for values in pethub['message'][-1:][0].values():
            #Update battery state
            if "Battery" in values: #Update Battery State
                mv = next((fm for fm in pethub['message'] if fm['OP'] == "Battery"), None)
                hasepub(mac_address+"_battery/state",mv['Battery'])
            #Update movements through the pet door
            if "PetMovement" in values: #Pet Movement 
                mv = next((fm for fm in pethub['message'] if fm['OP'] == "PetMovement"), None)
                happub(mv['Animal'].lower()+'/state',mv['Direction'])

            #Update lock state
            if "LockState" in values: #Lock state
                mv = next((fm for fm in pethub['message'] if fm['OP'] == "LockState"), None)
                if mv['LockState'] in ["Curfew"]:
                    keepin = "OFF"
                    keepout = "OFF"
                    curfew = "ON"
                else:
                    curfew = "OFF"
                    if mv['LockState'] in ["KeepIn","Locked"]:
                        keepin = "ON"
                    else:
                        keepin = "OFF"
                    if mv['LockState'] in ["KeepOut","Locked"]:
                        keepout = "ON"
                    else:
                        keepout = "OFF"
                haswpub(mac_address+"_lock_keepin/state",keepin)
                haswpub(mac_address+"_lock_keepout/state",keepout)
                haswpub(mac_address+"_curfew/state",curfew)

                #Update state value with change
                states[mac_address].State=LockState(device.lockingmode).name

                lockmsg = phlp.updatedb('doors',mac_address,'lockingmode', str(mv.LockStateNumber))
                if PrintDebug:
                    log.debug("Database updated "+str(lockmsg))

            #Update Curfew state
            if "Curfew" in values: #Curfew state
                mv = next((fm for fm in pethub['message'] if fm['OP'] == "Curfew"), None)
                states[mac_address].curfew.State=mv.CurfewState
                if PrintDebug:
                    log.debug("Curfew: "+ json.dumps(states[mac_address].curfew))
                #haswpub(mac_address+'_curfew/status',json.dumps(states[mac_address].curfew))

                lockmsg = phlp.updatedb('doors',mac_address,'curfewenabled', str(mv.CurfewStateNumber))
                if PrintDebug:
                    log.debug("Database updated "+str(lockmsg))

            hasepub(mac_address+'/status',json.dumps(states[mac_address]))


# Pet Door Lock Update State
def on_petdoor_ha_lock_message(client, obj, msg):
    if PrintDebug:
        log.info("Door Lock    Raw: "+msg.topic+" "+str(msg.qos)+" "+msg.payload.decode("utf-8"))
    devname=msg.topic.split("/")[3].split("_")
    if PrintDebug:
        log.debug('HA Lock MAC: '+devname[1] + ' LockType ' + devname[3] + ' Action ' + str(msg.payload,"utf-8"))
    lockmsg = phlp.generatemessage(devname[1], devname[3], str(msg.payload,"utf-8"))
    if PrintDebug:
        log.debug("HA Lock to Hub Message: " + json.dumps(lockmsg))
    hubpub(lockmsg['topic'],lockmsg['msg'])

# Pet Door Curfew
def on_petdoor_ha_curfew_message(client, obj, msg):
    if PrintDebug:
        log.info("Door Curfew    Raw: "+msg.topic+" "+str(msg.qos)+" "+msg.payload.decode("utf-8"))
    devname=msg.topic.split("/")[3].split("_")
    curfewmsg = phlp.generatemessage(devname[1], "setcurfewstate", str(msg.payload,"utf-8"))
    if PrintDebug:
        log.debug("Curfew Message: " + json.dumps(curfewmsg))
    hubpub(curfewmsg['topic'],curfewmsg['msg'])
    lockmsg = phlp.generatemessage(devname[1], "curfewlock", str(msg.payload,"utf-8"))
    if PrintDebug:
        log.debug("Curfew to Hub Message: " + json.dumps(lockmsg))
    hubpub(lockmsg['topic'],lockmsg['msg'])

# Feeder
def on_feeder_hub_message(client, obj, msg):
    msgsplit = msg.payload.decode("utf-8").split()
    if msgsplit[1] != "1000":
        pethub=phlp.decodehubmqtt(msg.topic,msg.payload.decode("utf-8"))
        mac_address = msg.topic.split("/")[-1]
        log.info("Feeder Parsed: "+json.dumps(pethub))
        if PrintDebug:
            log.info("Feeder    Raw: "+msg.topic+" "+str(msg.qos)+" "+msg.payload.decode("utf-8"))

        #Ack all the messages apart from the acks and the 132's
        for values in pethub['message']:
            #Don't ack an existing ack
            if values['OP'] not in ['Ack','Data132Battery']:
                #Don't ack the last value in array as that is the message info
                if not isinstance(values['OP'], list):
                    #Not an ack so we need to ack back.
                    ackmsg = phlp.generatemessage(mac_address, "ack", values.data.msg)
                    hubpub(ackmsg['topic'],ackmsg['msg'])

        for values in pethub['message'][-1:][0].values():
            if "Battery" in values: #Update Battery State
                mv = next((fm for fm in pethub['message'] if fm['OP'] == "Battery"), None)
                hasepub(mac_address+"_battery/state",mv['Battery'])
            if "Feed" in values:
                mv = next((fm for fm in pethub['message'] if fm['OP'] == "Feed"), None)
                if PrintDebug:
                    log.debug("Feeder Message"+str(mv))

                states[mac_address].State=mv['FA']

                if mv['FA'] in ['Animal_Closed','Manual_Closed']:
                    #Update feeder current weight
                    states[mac_address]['Open Seconds']=mv['FOS']
                    states[mac_address]['Left weight']=mv['SLT']
                    states[mac_address]['Right weight']=mv['SRT']

                    bowl = {"left":mv['SLT'],"right":mv['SRT']}
                    if PrintDebug:
                        log.debug(bowl)

                    #Set Feeder Bowl Status only when the feeder is closing
                    hasepub(mac_address+'_bowl/state',json.dumps(bowl))

                    #Update amount animal ate
                    if mv['Animal'] != "Manual":
                        petbowl = {"time":mv['FOS'], "left":str(round(float(mv['SLF'])-float(mv['SLT']),2)),"right":str(round(float(mv['SRF'])-float(mv['SRT']),2))}
                        happub(mv['Animal'].lower()+'_bowl/state',json.dumps(petbowl))

                else:
                    if PrintDebug:
                        log.debug("Not closed action")
                    bowl = {"state":mv['Animal']+" "+mv['FA'], "left":mv['SLT'],"right":mv['SRT']}

                #Set Feeder Status
                if PrintDebug:
                    log.debug("Feeder State: "+mac_address+" " +json.dumps(states[mac_address]))
                hasepub(mac_address+'/status',json.dumps(states[mac_address]))

# Cat Door
def on_catflap_hub_message(client, obj, msg):
    msgsplit = msg.payload.decode("utf-8").split()
    if msgsplit[1] != "1000":
        pethub=phlp.decodehubmqtt(msg.topic,msg.payload.decode("utf-8"))
        mac_address = msg.topic.split("/")[-1]
        log.info("Cat Flap    Raw: "+msg.topic+" "+str(msg.qos)+" "+msg.payload.decode("utf-8"))
        log.info("Cat Flap Parsed: "+json.dumps(pethub))

        #I have added this in as the feeder seems to need every message acked back to it with a 127, the counter sent to it and the message type.

        #Ack all the messages apart from the acks and the 132's
        for values in pethub['message']:
            #Don't ack an existing ack
            if values['OP'] not in ['Ack','Data132Battery']:
                #Don't ack the last value in array as that is the message info
                if not isinstance(values['OP'], list):
                    #Not an ack so we need to ack back.
                    ackmsg = phlp.generatemessage(mac_address, "sendack", values.data)
                    hubpub(ackmsg['topic'],ackmsg['msg'])


        if pethub['operation'] == 'Status':
            for values in pethub['message'][-1:][0].values():
                if "Battery" in values: #Update Battery State
                    mv = next((fm for fm in pethub['message'] if fm['OP'] == "Battery"), None)
                    hasepub(devid+"_battery/state",mv['Battery'])
                if "PetMovement" in values: #Pet Movement 
                    mv = next((fm for fm in pethub['message'] if fm['OP'] == "PetMovement"), None)
                    happub(mv['Animal'].lower()+'/state',mv['Direction'])
                if "LockState" in values: #Lock state
                    mv = next((fm for fm in pethub['message'] if fm['OP'] == "LockState"), None)
                    if mv['LockState'] in ["KeepIn","Locked"]:
                        keepin = "ON"
                    else:
                        keepin = "OFF"
                    if mv['LockState'] in ["KeepOut","Locked"]:
                        keepout = "ON"
                    else:
                        keepout = "OFF"
                    haswpub(devid+"_lock_keepin/state",keepin)
                    haswpub(devid+"_lock_keepout/state",keepout)
                    topicsplit = msg.topic.split("/")
                    if PrintDebug:
                        log.debug(str(topicsplit[-1]))
                    lockmsg = phlp.updatedb('doors',topicsplit[-1],'lockingmode', mv['Lock'])
                    if PrintDebug:
                        log.debug(lockmsg)

def on_catflap_lock_message(client, obj, msg):
    log.info("Cat Flap Lock: "+msg.topic+" "+msg.payload.decode("utf-8"))
    topicsplit = msg.topic.split("/")
    if PrintDebug:
        log.debug(topicsplit[3])
    devname=topicsplit[3].split("_")
    if PrintDebug:
        log.debug(devname[1])
    lockmsg = phlp.generatemessage(topicsplit[-1], devname[3], str(msg.payload,"utf-8"))
    if PrintDebug:
        log.debug(lockmsg)
    hubpub(lockmsg['topic'],lockmsg['msg'])

def on_catflap_curfew_message(client, obj, msg):
    log.info("Cat Flap Curfew "+msg.topic+" "+msg.payload.decode("utf-8")+" "+json.dumps(pethub))
    log.info("** not implemented")

# Umatched Message
def on_message(client, obj, msg):
    if "pethublocal/messages" in msg.topic:
        pethub = phlp.decodehubmqtt(msg.topic,msg.payload.decode("utf-8"))
        log.info("Hub Message T=" +msg.topic+" QoS="+str(msg.qos)+" Msg="+str(msg.payload)+" Parsed="+json.dumps(pethub))
    else:
        log.info("HA message T=" +msg.topic+" QoS="+str(msg.qos)+" Msg="+str(msg.payload))
    

#def on_publish(client,data,res):
#    log.info("data published msg ", res)
#   pass

#Publish sensor topic
def hasepub(topic,message):
    ret=mc.publish(d_sen_t+topic,message,qos=0, retain=True)

#Publish switch topic
def haswpub(topic,message):
    ret=mc.publish(d_swi_t+topic,message,qos=0, retain=True)

#Publish pet topic
def happub(topic,message):
    ret=mc.publish(ha_pet_topic+topic,message,qos=0, retain=True)

#Publish pet topic
def hubpub(topic,message):
    ret=mc.publish(topic,message,qos=1, retain=False)


#Start Pet Hub Local Process
log.info("Starting Pet Hub")
mc = mqtt.Client()
mc.on_message = on_message
#mc.on_publish = on_publish
if os.environ.get('HAMQTTUSERNAME') is not None and os.environ.get('HAMQTTPASSWORD') is not None:
    if PrintDebug:
        log.debug("HAMQTTUSERNAME and HAMQTTPASSWORD set so setting MQTT broker password")
    mc.username_pw_set(username=os.environ.get('HAMQTTUSERNAME'),password=os.environ.get('HAMQTTPASSWORD'))
log.info("Connecting to Home Assistant MQTT endpoint at "+mqtthost+" port "+str(mqttport))
mc.connect(mqtthost, mqttport, 30)

#Gather init data from pethublocal.db
pethubinit = phlp.inithubmqtt()
if PrintDebug:
    log.debug("SQLite init database response: "+str(pethubinit))
log.info("Load Devices from pethublocal.db and create Home Assistant MQTT discovery config topics")
for device in pethubinit.devices:
    if PrintDebug:
        log.debug(device)
    #Shorter variable to save time and allow replacement if needed
    dev=device.name

    #Naming the Unique IDs and thus the topics and thus the entity id should make everything easier for both ends.
    #devid=device.name.replace(' ', '_').lower()
    devid=device.mac_address

    mac=device.mac_address
    pid=device.product_id

    #Create Battery sensor as long as it isn't a hub as hubs don't have a battery
    if pid != 1:
        #Battery State Config
        configmessage={"name": dev+" Battery", "icon": "mdi:battery", "unique_id": "device_"+devid+"_battery", "state_topic": d_sen_t+devid+"_battery/state"}
        hasepub(devid+'_battery/config',json.dumps(configmessage))
        #Set Battery Sensor state
        if PrintDebug:
            log.debug(d_sen_t+devid+'_battery/state'+" " +device.battery)
        hasepub(devid+'_battery/state',device.battery)

    if pid == 1: #Hub
        log.info("Loading Hub: "+dev)
        if PrintDebug:
            log.debug("Hub DB record: "+str(device))
        devid="hub"
        #Hub Uptime
        configmessage={"name": dev, "icon": "mdi:radio-tower", "unique_id": "device_"+devid, "stat_t": d_sen_t+devid+"/status", "json_attr_t": d_sen_t+devid+"/status", "val_tpl": "{{value_json['State']}}" }
        hasepub(devid+'/config',json.dumps(configmessage))

        #Hub status message
        states.hub=Box({"State":Online(device.state).name, "Uptime":"0 Mins", "Name": dev, "Serial": device.serial_number,"MAC Address": mac, "LED Mode":HubLeds(device.led_mode).name, "Pairing Mode":HubAdoption(device.pairing_mode).name })

        #Loop version json blob
        version = Box.from_json(device.version)
        for devs in version.device:
            states.hub[devs.title()] = version.device[devs]

        #Publish staus message
        hasepub(devid+'/status',json.dumps(states.hub))

        #Add callback
        mc.message_callback_add(hub_topic, on_hub_message)

    if pid == 3 or pid == 6: #Pet Door (3) or Cat Flap (6)
        #Set Time
        #log.info("Setting device time for "+device.name)
        
        states.update({mac:{'State':LockState(device.lockingmode).name}})

        #Set time on device
        genmsg = phlp.generatemessage(mac, "settime", "") # Message 0c for Battery
        if PrintDebug:
            log.debug("Gen settime Message: " + json.dumps(genmsg))
        hubpub(genmsg.topic,genmsg.msg)

        if pid == 3: #Pet Door (3)
            log.info("Loading Pet Door: "+device.name)
            #Dump current state 
            if StateOnStartup:
                log.info("Dump current state for "+device.name)
                genmsg = phlp.generatemessage(mac, "dumpstate", "")
                hubpub(genmsg.topic,genmsg.msg)

            if PrintDebug:
                log.debug("Pet Door Payload: "+str(device))
            #Adding callbacks to MQTT to call separate functions when messages arrive for pet dor
            mc.message_callback_add(hub_topic+'/'+mac, on_petdoor_hub_message)
            mc.message_callback_add(d_swi_t+devid+"_lock_keepin/set", on_petdoor_ha_lock_message)
            mc.message_callback_add(d_swi_t+devid+"_lock_keepout/set", on_petdoor_ha_lock_message)
            mc.message_callback_add(d_swi_t+devid+"_curfew/set", on_petdoor_ha_curfew_message)

        if pid == 6: #Cat Flap (6)
            log.info("Loading Cat Flap: "+device.name)
            if PrintDebug:
                log.debug("Cat Flap Payload: "+str(device))
            #Adding callbacks to MQTT to call separate functions when messages arrive for cat flap
            mc.message_callback_add(hub_topic+'/'+mac, on_catflap_hub_message)
            mc.message_callback_add(d_swi_t+devid+"_lock_keepin/set", on_catflap_lock_message)
            mc.message_callback_add(d_swi_t+devid+"_lock_keepout/set", on_catflap_lock_message)
            mc.message_callback_add(d_swi_t+devid+"_curfew/set", on_catflap_curfew_message)

            #Get Battery state
            genmsg = phlp.generatemessage(mac, "get", "battery") # Message 0c for Battery
            if PrintDebug:
                log.debug("Gen Cat Flap Message: " + json.dumps(genmsg))
            hubpub(genmsg.topic,genmsg.msg)

        #Curfew
        if device.curfewenabled != "None" and device.lock_time != "None" and device.unlock_time != "None":
            curfewstate = {'State':CurfewOnOff(device.curfewenabled).name, 'Lock time':str(device.lock_time),'Unlock time':str(device.unlock_time)}
            states[mac].curfew=curfewstate

            ##Curfew State Switch
            #configmessage={"name": dev+" Curfew", "icon": "mdi:door", "unique_id": "device_"+devid+"_curfew", "command_topic": d_swi_t+devid+"_curfew/set", "state_topic": d_swi_t+devid+"_curfew/status", "json_attributes_topic": d_swi_t+devid+"_curfew/status", "val_tpl": "{{value_json['State']}}" }
            #if PrintDebug:
            #    log.debug("Curfew Config: " + json.dumps(configmessage))
            #haswpub(devid+'_curfew/config',json.dumps(configmessage))

            #Curfew State Times
            #curfewstate = {'State':CurfewOnOff(device.curfewenabled).name, 'Lock time':str(device.lock_time),'Unlock time':str(device.unlock_time)}
            #states[mac].curfew=curfewstate
            ##if PrintDebug:
            #    log.debug("Curfew State: " + json.dumps(states[mac].curfew))
            #haswpub(devid+'_curfew/status',json.dumps(states[mac].curfew))

        #Lock state as a switch
        if device.lockingmode != "None":
            lockstate = ["lock_keepin","lock_keepout","curfew"]
            for key in lockstate:
                #log.info(key)
                configmessage={"name": dev+" "+key.replace('_', ' '), "icon": "mdi:door", "unique_id": "device_"+devid+"_"+key, "command_topic": d_swi_t+devid+"_"+key+"/set", "state_topic": d_swi_t+devid+"_"+key+"/state" }
                haswpub(devid+"_"+key+'/config',json.dumps(configmessage))
                if PrintDebug:
                    log.info("Add Lock switch: "+ devid+"_"+key+'/config' + " " +json.dumps(configmessage))
            if device.lockingmode in [1,3]:
                keepin = "ON"
            else:
                keepin = "OFF"
            if device.lockingmode in [2,3]:
                keepout = "ON"
            else:
                keepout = "OFF"
            if device.lockingmode in [4]:
                curfew = "ON"
            else:
                curfew = "OFF"
            haswpub(devid+"_lock_keepin/state",keepin)
            haswpub(devid+"_lock_keepout/state",keepout)
            haswpub(devid+"_curfew/state",curfew)

        #State Config
        configmessage={"name": dev, "icon": "mdi:door", "unique_id": "device_"+devid, "stat_t": d_sen_t+devid+"/status", "json_attr_t": d_sen_t+devid+"/status", "val_tpl": "{{value_json['State']}}" }
        hasepub(devid+'/config',json.dumps(configmessage))

        #Set Sensor Status
        if PrintDebug:
            log.debug(d_sen_t+devid+'/status'+" " +json.dumps(states[mac]))
        hasepub(devid+'/status',json.dumps(states[mac]))

    if pid == 4: #Feeder
        log.info("Loading Feeder: "+device.name)
        if PrintDebug:
            log.info("Feeder Payload: "+str(device))
        #Add callback for feeder from hub
        mc.message_callback_add(hub_topic+'/'+mac, on_feeder_hub_message)

        #Init feeder
        #Get Battery state
        genmsg = phlp.generatemessage(mac, "get", "battery") # Message 0c for Battery
        if PrintDebug:
            log.debug("Gen Battery Message: " + json.dumps(genmsg))
        hubpub(genmsg.topic,genmsg.msg)

        #Set the time
        genmsg = phlp.generatemessage(mac, "settime", "")
        if PrintDebug:
            log.debug("Gen settime Message: " + json.dumps(genmsg))
        hubpub(genmsg.topic,genmsg.msg)

        #Configured bowls
        states.update({mac:{'State':'Closed','Open Seconds':0, 'Left weight':device.bowl1,'Right weight':device.bowl2, 'Bowl Count':device.bowltype}})
        if device.bowltype == 2: #Two bowls
            #Build config for HA MQTT discovery
            states[mac].update({"Left target": str(device.bowltarget1),"Right target":str(device.bowltarget2)})
            #Build config for HA MQTT discovery
            bowl = {"left":["Current Left Weight","g"],"right":["Current Right Weight","g"]}
            #Set State
            bowlstate = {"left":str(device.bowl1),"right":str(device.bowl2)}
        elif device.bowltype == 1: #One bowl
            #Build config for HA MQTT discovery
            states[mac].update({"Target": str(device.bowltarget1)})
            #Build config for HA MQTT discovery
            bowl = {"weight":["Current Weight","g"]}
            #Set State
            bowlstate = {"weight":str(device.bowl1)}
        else:
            log.info("Unknown Bowl Configuration")

        #Feeder State Config
        configmessage={"name": dev, "icon": "mdi:bowl", "unique_id": "device_"+devid, "stat_t": d_sen_t+devid+"/status", "json_attr_t": d_sen_t+devid+"/status", "val_tpl": "{{value_json['State']}}" }
        hasepub(devid+'/config',json.dumps(configmessage))

        #Set Feeder Sensor Status
        if PrintDebug:
            log.debug(d_sen_t+devid+'/status'+" " +json.dumps(states[mac]))
        hasepub(devid+'/status',json.dumps(states[mac]))

        if device.bowltype in [1,2]:
            #Create Bowl sensors
            for key,value in bowl.items():
                configmessage={"name": dev+" "+value[0], "icon": "mdi:bowl", "unique_id": "device_"+devid+"_"+key, "state_topic": d_sen_t+devid+"_bowl/state", "unit_of_measurement": value[1], "value_template": "{{value_json."+key+"}}"}
                hasepub(devid+'_'+key+'/config',json.dumps(configmessage))

            #Set Bowl Sensor State
            if PrintDebug:
                log.debug(d_sen_t+devid+'_bowl/state'+" " +json.dumps(bowlstate))
            hasepub(devid+'_bowl/state',json.dumps(bowlstate))

    if pid == 8: #Felaqua
        log.info("Loading Felaqua: "+device.name)
        if PrintDebug:
            log.info("Felaqua Payload: "+str(device))
        #Add callback for felaqua from hub
        mc.message_callback_add(hub_topic+'/'+mac, on_feeder_hub_message)

        #Get Battery state
        genmsg = phlp.generatemessage(mac, "get", "battery") # Message 0c for Battery
        if PrintDebug:
            log.debug("Gen Battery Message: " + json.dumps(genmsg))
        hubpub(genmsg.topic,genmsg.msg)

        #Set the time
        genmsg = phlp.generatemessage(mac, "settime", "") # Message 0c for Battery
        if PrintDebug:
            log.debug("Gen settime Message: " + json.dumps(genmsg))
        hubpub(genmsg.topic,genmsg.msg)

        #Configured water bowl
        states.update({mac:{'Weight':device.bowl1,'Tare':device.bowltarget1}})

        #Feeder State Config
        configmessage={"name": dev, "icon": "mdi:bowl", "unique_id": "device_"+devid, "stat_t": d_sen_t+devid+"/status", "json_attr_t": d_sen_t+devid+"/status", "val_tpl": "{{value_json['Weight']}}" }
        hasepub(devid+'/config',json.dumps(configmessage))

        #Set Feeder Sensor Status
        if PrintDebug:
            log.debug(d_sen_t+devid+'/status'+" " +json.dumps(states[mac]))
        hasepub(devid+'/status',json.dumps(states[mac]))

log.info("Load Pets from pethublocal.db and create Home Assistant MQTT discovery config topics")
for pet in pethubinit.pets:
    pn = pet.name
    pnid = pn.replace(' ', '_').lower()
    if pet.product_id == 3 or pet.product_id == 6: #Pet Door or Cat Flap
        log.info("Loading Pet: "+pn+" for door "+pet.device)
        configmessage={"name": pn, "icon": "mdi:"+Animal(pet.species).name, "unique_id": "pet_"+pnid, "state_topic": ha_pet_topic+pnid+"/state"}
        happub(pnid+'/config',json.dumps(configmessage))
        happub(pnid+'/state',str(AnimalState(pet.state).name))

    if pet.product_id == 4: #Feeder
        log.info("Loading Pet: "+pn+" for feeder "+pet.device)
        feederarray = ast.literal_eval(pet.state)
        if len(feederarray)==2:
            #Build config for HA MQTT discovery
            bowl = {"time":[" last feed time","s"], "left":[" left weight","g"],"right":[" right weight","g"]}
            #Get current bowl state
            bowlstate = {"time":"0", "left":str(feederarray[0]),"right":str(feederarray[1])}
        elif len(feederarray)==1:
            #Build config for HA MQTT discovery
            bowl = {"time":[" last feed time","s"], "bowl":[" weight","g"]}
            #Get current bowl state
            bowlstate = {"time":"0", "bowl":str(feederarray[0])}
        else:
            log.info("Unknown Bowl Configuration")

        for key,value in bowl.items():
            configmessage={"name": pn+value[0], "icon": "mdi:"+Animal(pet.species).name, "unique_id": "pet_"+pnid+"_"+key, "state_topic": ha_pet_topic+pnid+"_bowl/state", "unit_of_measurement": value[1], "value_template": "{{value_json."+key+"}}"}
            happub(pnid+'_'+key+'/config',json.dumps(configmessage))

        if PrintDebug:
            log.debug(bowlstate)
        happub(pnid+'_bowl/state',json.dumps(bowlstate))

#Everything done so ready to subscribe to the topics we care about.
log.info("Subscribe to pethublocal and home assistant topics")
mc.subscribe([("pethublocal/#",1), (hastatetopic, 0), (hasettopic, 0)])
mc.loop_forever()
