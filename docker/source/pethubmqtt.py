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
import json, ast, os, logging, sys, socket
import pethubpacket as phlp
import paho.mqtt.client as mqtt
from pethubconst import *
from box import Box
from pathlib import Path
from datetime import datetime

#Debugging mesages
PrintDebug = True #Print debugging messages

#Fixed values for MQTT Topic Names
#Topic for all messages generated by the hub, with the devices being a sub topic which is how the hub and devices work so can't be changed.
h_t = 'pethublocal/messages'
#Home Assistant MQTT Discovery Sensor topic for pets being added
p_t = 'homeassistant/sensor/pethub/pet_'
#Home Assistant MQTT Discovery Sensor topic for devices being added
d_sen_t = 'homeassistant/sensor/pethub/device_'
#Home Assistant MQTT Discovery Switch topic for devices being added with on/off switch
d_swi_t = 'homeassistant/switch/pethub/device_'
#Home Assistant topics to subscribe to as we care about the state and set messages from HA.
hastatetopic="homeassistant/+/pethub/+/state"
hasettopic="homeassistant/+/pethub/+/set"

#logger = logging.getLogger(__file__)
#logging.basicConfig(level=logging.INFO)

#Setup Logging framework to log to console without timestamps and log to file with timestamps
log = logging.getLogger('')
log.setLevel(logging.DEBUG)
format = logging.Formatter("%(asctime)s - [%(levelname)-5.5s] - %(message)s")
ch = logging.StreamHandler(sys.stdout)
log.addHandler(ch)
Path("log").mkdir(exist_ok=True)
fh = logging.FileHandler('log/pethubmqtt-{:%Y-%m-%d}.log'.format(datetime.now()))
fh.setFormatter(format)
log.addHandler(fh)

#MQTT for pethublocal/hub and home assistant where the hub messages go, the broker sends the messages from the docker hub mqtt instance to your home assistant instance in the mosquitto.conf broker setting
if os.environ.get('HAMQTTIP') is not None:
    hamqttip = os.environ.get('HAMQTTIP')
    log.info("HAMQTTIP connecting to "+hamqttip)
    #If no port was specified connect to 1883
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

# Feeder
def on_hub_message(client, obj, msg):
    log.info("Hub  "+msg.topic+" "+str(msg.qos)+" "+msg.payload.decode("utf-8"))

# Pet Door
def on_petdoor_message(client, obj, msg):
    log.info("Door "+msg.topic+" "+str(msg.qos)+" "+msg.payload.decode("utf-8"))
    pethub = phlp.decodehubmqtt(msg.topic,msg.payload.decode("utf-8"))
    for values in pethub['message'][-1:][0].values():
        if "PetMovement" in values: #Pet Movement 
            mv = next((fm for fm in pethub['message'] if fm['OP'] == "PetMovement"), None)
            ret=mc.publish(p_t + mv['Animal'].lower() + '/state',mv['Direction'])
        if "LockState" in values: #Lock state
            mv = next((fm for fm in pethub['message'] if fm['OP'] == "LockState"), None)
            if mv['Lock'] in ["KeepIn","Locked"]:
                keepin = "ON"
            else:
                keepin = "OFF"
            if mv['Lock'] in ["KeepOut","Locked"]:
                keepout = "ON"
            else:
                keepout = "OFF"
            ret=mc.publish(d_swi_t+devid+"_lock_keepin/state",keepin)
            ret=mc.publish(d_swi_t+devid+"_lock_keepout /state",keepout)
            topicsplit = msg.topic.split("/")
            if PrintDebug:
                log.debug("Device "+str(topicsplit[-1]))
            lockmsg = phlp.updatedb('doors',topicsplit[-1],'lockingmode', mv['Lock'])
            if PrintDebug:
                log.debug("Database updated"+str(lockmsg))

# Pet Door Lock Update State
def on_petdoor_lock_message(client, obj, msg):
    log.info("Door Lock "+msg.topic+" "+str(msg.qos)+" "+msg.payload.decode("utf-8"))
    topicsplit = msg.topic.split("/")
    if PrintDebug:
        log.debug(topicsplit[3])
    devname=topicsplit[3].split("_")
    if PrintDebug:
        log.debug(devname[1])
    lockmsg = phlp.generatemessage(devname[1], devname[3], str(msg.payload,"utf-8"))
    if PrintDebug:
        log.debug(lockmsg)
    ret=mc.publish(lockmsg['topic'],lockmsg['msg'],qos=1)

# Pet Door Curfew
def on_petdoor_curfew_message(client, obj, msg):
    log.info("Door Curfew "+msg.topic+" "+str(msg.qos)+" "+msg.payload.decode("utf-8"))
#    log.info(p.generatemessage("hub", "flashleds"))
#    ret=mc.publish('pethublocal/messages',p.generatemessage("hub", "flashleds"),qos=1)
#    log.info(ret)

# Feeder
def on_feeder_message(client, obj, msg):
    log.info("Feeder "+msg.topic+" "+str(msg.qos)+" "+msg.payload.decode("utf-8"))
    pethub = phlp.decodehubmqtt(msg.topic,msg.payload.decode("utf-8"))
    if PrintDebug:
        log.debug(pethub)
    for values in pethub['message'][-1:][0].values():
        if "Feed" in values:
            mv = next((fm for fm in pethub['message'] if fm['OP'] == "Feed"), None)
            if PrintDebug:
                log.debug("Feeder Message"+str(mv))
            if 'Animal_Closed' in mv['FA']:
                #Update feeder current weight
                bowl = {"state":mv['FA'], "left":mv['SLT'],"right":mv['SRT']}
                if PrintDebug:
                    log.debug(bowl)
                ret=mc.publish(d_sen_t+pethub['device'].lower()+'_bowl/state',json.dumps(bowl))

                #Update amount animal ate
                petbowl = {"time":mv['FOS'], "left":str(round(float(mv['SLT'])-float(mv['SLF']),2)),"right":str(round(float(mv['SRT'])-float(mv['SRF']),2))}
                ret=mc.publish(p_t+mv['Animal'].lower()+'_bowl/state',json.dumps(petbowl))
            else:
                if PrintDebug:
                    log.debug("Non animal close")
                bowl = {"state":mv['Animal'] + " " + mv['FA'], "left":mv['SLT'],"right":mv['SRT']}
                ret=mc.publish(d_sen_t+pethub['device'].lower()+'_bowl/state',json.dumps(bowl))

# Cat Door
def on_catflap_message(client, obj, msg):
    log.info("Cat Flap "+msg.topic+" "+str(msg.qos)+" "+msg.payload.decode("utf-8"))
    pethub = phlp.decodehubmqtt(msg.topic,msg.payload.decode("utf-8"))
    for values in pethub['message'][-1:][0].values():
        if "PetMovement" in values: #Pet Movement 
            mv = next((fm for fm in pethub['message'] if fm['OP'] == "PetMovement"), None)
            ret=mc.publish(p_t + mv['Animal'].lower() + '/state',mv['Direction'])
        if "LockState" in values: #Lock state
            mv = next((fm for fm in pethub['message'] if fm['OP'] == "LockState"), None)
            if mv['Lock'] in ["KeepIn","Locked"]:
                keepin = "ON"
            else:
                keepin = "OFF"
            if mv['Lock'] in ["KeepOut","Locked"]:
                keepout = "ON"
            else:
                keepout = "OFF"
            ret=mc.publish(d_swi_t+devid+"_lock_keepin/state",keepin)
            ret=mc.publish(d_swi_t+devid+"_lock_keepout/state",keepout)
            topicsplit = msg.topic.split("/")
            if PrintDebug:
                log.debug(str(topicsplit[-1]))
            lockmsg = phlp.updatedb('doors',topicsplit[-1],'lockingmode', mv['Lock'])
            if PrintDebug:
                log.debug(lockmsg)

# Missed Message.. this shouldn't happen so log it.
def on_message(client, obj, msg):
    log.info("**Non matched message** "  + msg.topic+" "+str(msg.qos)+" "+str(msg.payload))

def on_publish(cl,data,res):
    #log.info("data published ", res)
    pass

log.info("Starting Pet Hub")
mc = mqtt.Client()
mc.on_message = on_message
mc.on_publish = on_publish
if os.environ.get('HAMQTTUSERNAME') is not None and os.environ.get('HAMQTTPASSWORD') is not None:
    if PrintDebug:
        log.debug("HAMQTTUSERNAME and HAMQTTPASSWORD set so setting MQTT broker password")
    mc.username_pw_set(username=os.environ.get('HAMQTTUSERNAME'),password=os.environ.get('HAMQTTPASSWORD'))
log.info("Connecting to Home Assistant MQTT endpoint at " + mqtthost + " port " + str(mqttport))
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
    devid=device.name.replace(' ', '_').lower()
    batt=device.battery
    mac=device.mac_address
    pid=device.product_id

    #Set Battery as long as it isn't a hub as hubs don't have a battery
    if pid != 1:
        configmessage={"name": dev+" Battery", "icon": "mdi:battery", "unique_id": "device_"+devid+"_battery", "state_topic": d_sen_t+devid+"_battery/state"}
        ret=mc.publish(d_sen_t+devid+'_battery/config',json.dumps(configmessage))
        ret=mc.publish(d_sen_t+devid+'_battery/state',batt)

    if pid == 1: #Hub
        log.info("Loading Hub:"+device.name)
        if PrintDebug:
            log.debug("Hub Payload:"+str(device))
        mc.message_callback_add(h_t, on_hub_message)

    if pid == 3 or pid == 6: #Pet Door (3) or Cat Flap (6)
        #Set Time
        log.info("Setting device time for "+device.name)
        petdoortime = phlp.generatemessage(dev, "settime", "")
        ret=mc.publish(petdoortime.topic,petdoortime.msg,qos=1)

        #Dump current state 
        log.info("Dump current state for "+device.name)
        petdoortime = phlp.generatemessage(dev, "dumpstate", "")
        ret=mc.publish(petdoortime.topic,petdoortime.msg,qos=1)
    
        if pid == 3: #Pet Door (3)
            log.info("Loading Pet Door: "+device.name)
            if PrintDebug:
                log.debug("Pet Door Payload: "+str(device))
            #Adding callbacks to MQTT to call separate functions when messages arrive for pet dor
            mc.message_callback_add(h_t + '/' + mac, on_petdoor_message)
            mc.message_callback_add(d_swi_t+devid+"_lock_keepin/set", on_petdoor_lock_message)
            mc.message_callback_add(d_swi_t+devid+"_lock_keepout/set", on_petdoor_lock_message)
            mc.message_callback_add(d_swi_t+devid+"_curfew/set", on_petdoor_curfew_message)

        if pid == 6: #Cat Flap (6)
            log.info("Loading Cat Flap: "+device.name)
            if PrintDebug:
                log.debug("Cat Flap Payload: "+str(device))
            #Adding callbacks to MQTT to call separate functions when messages arrive for cat flap
            mc.message_callback_add(h_t + '/' + mac, on_catflap_message)
            mc.message_callback_add(d_swi_t+devid+"_lock_keepin/set", on_catflap_lock_message)
            mc.message_callback_add(d_swi_t+devid+"_lock_keepout/set", on_catflap_lock_message)
            mc.message_callback_add(d_swi_t+devid+"_curfew/set", on_catflap_curfew_message)

        #Curfew
        if device.curfewenabled != "None" and device.lock_time != "None" and device.unlock_time != "None":
            #Curfew State Switch
            #configmessage={"name": dev+" Curfew", "icon": "mdi:door", "unique_id": "device_"+devid+"_curfew", "command_topic": d_swi_t+devid+"_curfew/set", "state_topic": d_swi_t+devid+"_curfew/state" }
            #ret=mc.publish(d_swi_t+devid+"_"+key+'/config',json.dumps(configmessage))
            #ret=mc.publish(d_swi_t+devid+'_curfew/state',json.dumps(CurfewState(device.curfewenabled).name))

            #Curfew State Times
            curfewstate = {"lock_time":str(device.lock_time),"unlock_time":str(device.unlock_time)}
            if PrintDebug:
                log.debug("CurfewState: "+str(curfewstate))
            for key in curfewstate:
                configmessage={"name": dev+" "+key.replace('_', ' '), "icon": "mdi:door", "unique_id": "device_"+devid+"_"+key, "state_topic": d_sen_t+devid+"_curfew/state", "value_template": "{{value_json."+key+"}}"}
                ret=mc.publish(d_sen_t+devid+'_'+key+'/config',json.dumps(configmessage))

        #Lock state as a switch
        if device.lockingmode != "None":
            lockstate = ["lock_keepin","lock_keepout"]
            for key in lockstate:
                #log.info(key)
                configmessage={"name": dev+" "+key.replace('_', ' '), "icon": "mdi:door", "unique_id": "device_"+devid+"_"+key, "command_topic": d_swi_t+devid+"_"+key+"/set", "state_topic": d_swi_t+devid+"_"+key+"/state" }
                ret=mc.publish(d_swi_t+devid+"_"+key+'/config',json.dumps(configmessage))
            if device.lockingmode in [1,3]:
                keepin = "ON"
            else:
                keepin = "OFF"
            if device.lockingmode in [2,3]:
                keepout = "ON"
            else:
                keepout = "OFF"
            ret=mc.publish(d_swi_t+devid+"_lock_keepin/state",keepin)
            ret=mc.publish(d_swi_t+devid+"_lock_keepout/state",keepout)

    if pid == 4: #Feeder
        log.info("Loading Feeder: "+device.name)
        if PrintDebug:
            log.info("Feeder Payload: "+str(device))
        #Add callback for feeder from hub
        mc.message_callback_add(h_t + '/' + mac, on_feeder_message)

        if device.bowltype == 2: #Two bowls
            #Build config for HA MQTT discovery
            bowltarget = {"left_target":"Target Left Weight","right_target":"Target Right Weight"}
            #Set Target State
            bowltargetstate = {"left_target": str(device.bowltarget1),"right_target":str(device.bowltarget2)}
            #Build config for HA MQTT discovery
            bowl = {"state":["state",""], "left":["Current Left Weight","g"],"right":["Current Right Weight","g"]}
            #Set State
            bowlstate = {"state":"Closed", "left":"0","right":"0"}

        elif device.bowltype == 1: #One bowl
            #Build config for HA MQTT discovery
            bowltarget = {"target":"Target Weight"}
            #Set Target State
            bowltargetstate = {"target": str(device.bowltarget1)}
            #Build config for HA MQTT discovery
            bowl = {"state":["state",""], "weight":["Current Weight","g"]}
            #Set State
            bowlstate = {"state":"Closed", "weight":"0"}

        else:
            log.info("Unknown Bowl Configuration")
            
        if device.bowltype in [1,2]:
            #Create Bowl Target sensors
            for key,value in bowltarget.items():
                configmessage={"name": dev+" "+value, "icon": "mdi:bowl", "unique_id": "device_"+devid+"_"+key, "state_topic": d_sen_t+devid+"_bowl_target/state", "unit_of_measurement": "g", "value_template": "{{value_json."+key+"}}"}
                if PrintDebug:
                    log.debug(d_sen_t+devid+'_'+key+'/config' + " " +json.dumps(configmessage))
                ret=mc.publish(d_sen_t+devid+'_'+key+'/config',json.dumps(configmessage))

            #Set Bowl Target sensor state
            if PrintDebug:
                    log.debug(d_sen_t+devid+'_bowl_target/state' + " " +json.dumps(bowltargetstate))
            ret=mc.publish(d_sen_t+devid+'_bowl_target/state',json.dumps(bowltargetstate))

            #Create Bowl sensors
            for key,value in bowl.items():
                configmessage={"name": dev+" "+value[0], "icon": "mdi:bowl", "unique_id": "device_"+devid+"_"+key, "state_topic": d_sen_t+devid+"_bowl/state", "unit_of_measurement": value[1], "value_template": "{{value_json."+key+"}}"}
                ret=mc.publish(d_sen_t+devid+'_'+key+'/config',json.dumps(configmessage))

            #Set Bowl Sensor State
            ret=mc.publish(d_sen_t+devid+'_bowl/state',json.dumps(bowlstate))

log.info("Load Pets from pethublocal.db and create Home Assistant MQTT discovery config topics")
for pet in pethubinit.pets:
    pn = pet.name
    pnid = pn.replace(' ', '_').lower()
    if pet.product_id == 3: #Pet Door
        log.info("Loading Pet: "+pn+" for door "+pet.device)
        configmessage={"name": pn, "icon": "mdi:"+Animal(pet.species).name, "unique_id": "pet_"+pnid, "state_topic": p_t+pnid+"/state"}
        ret=mc.publish(p_t+pnid+'/config',json.dumps(configmessage))
        ret=mc.publish(p_t+pnid+'/state',str(AnimalState(pet.state).name))

    if pet.product_id == 4: #Feeder
        log.info("Loading Pet: "+pn+" for feeder "+pet.device)
        feederarray = ast.literal_eval(pet.state)
        if len(feederarray)==2:
            #Build config for HA MQTT discovery
            bowl = {"time":[" last feed time","s"], "left":[" left weight","g"],"right":[" right weight","g"]}
            for key,value in bowl.items():
                configmessage={"name": pn+value[0], "icon": "mdi:"+Animal(pet.species).name, "unique_id": "pet_"+pnid+"_"+key, "state_topic": p_t+pnid+"_bowl/state", "unit_of_measurement": value[1], "value_template": "{{value_json."+key+"}}"}
                ret=mc.publish(p_t+pnid+'_'+key+'/config',json.dumps(configmessage))
            #Get current bowl state
            bowlstate = {"time":"0", "left":str(feederarray[0]),"right":str(feederarray[1])}
            if PrintDebug:
                log.debug(bowlstate)
            ret=mc.publish(p_t+pnid+'_bowl/state',json.dumps(bowlstate))

#Everything done so ready to subscribe to the topics we care about.
log.info("Subscribe to pethublocal and home assistant topics")
mc.subscribe([("pethublocal/#",1), (hastatetopic, 0), (hasettopic, 0)])
mc.loop_forever()