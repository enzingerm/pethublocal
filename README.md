# Pet Hub Local

This is project aims to completely reverse engineer the cloud service for the Sure Petcare "Connect" series of internet enabled pet devices and to provide a local network backend for the Connect Hub to connect to rather than using their cloud service.
It was born out of frustration with the cloud service being unstable over Christmas 2020/January 2021 and from a privacy perspective I prefer to not to have all my animals movements being sent off to their cloud service.
End goal is to connect it to Home Assistant and equally if folks wanted to they could connect it into OpenHAB as I have kept it generic and am just sending MQTT messages to topics with the configuration and status.

All trademarks of are the rights of their respective owners and this is completely unsupported by Sure Petcare and may void agreement you have with them as I am sure what I have built is against their terms of use somewhere in the pages of agreement I was required to tick the box to agree to that no one ever reads.

I have added support for the devices I have in my home which are:

- Connect Internet Hub
- Pet Door Connect
- Feeder Connect

Working on adding support for the following devices if others in the community can assist with traces.
- Cat Flap Connect
- Felaqua Connect

## [Docker](docker) 

This is the main code you are looking for, it is a docker compose stack that should be self contained and able to integrate directly into home assistant.
I have built it on a Debian Buster image and have run it successfully on a x64 and ODroid C2 which is similar to a Raspberry Pi 4.
It is built to be modular so if you want to pick up components such as the MQTT configuration and integrate that into your existing Mosquito MQTT host it should be very straight forward.
Have a read of the readme to see the setup tasks.

### [Docker/source](docker/source)
This is the main python code used for interpreting the Hub messages that are sent from the hub over MQTT as well as supporting decrypting the 802.14.5 / MiWi packets sent over the air from the devices to the hub and converting them into a consistent message that is more useful than a stream of hex bytes. 
This directory is used by the pethub docker image when it starts pethubmqtt.py to talk to the single MQTT broker.

## AWS MTLS Certificate

If you are feeling handy with a soldering iron or have an older Hub (H001-H009) and you have *NEVER* connected it to the internet then you can get extract the AWS MTLS Certificate Password so then you can fully man in the middle the traffic from the Hub to AWS if you are interested to see what the messages that are created (or to contribute to this project).

### Older Hubs

The older hubs have firmware that send out the "long_serial" when they first boot up. If you setup the Docker Stack and redirect the DNS entry hub.api then you should see the hub connect to the web server and send a message like:

```serial_number=H008-0xxxxxxx&mac_address=0000xxxxxxxxxxxx&product_id=1&long_serial=xxxxxxxxxxxxxxxxxxxxx```

So... that last value is what you need, it's the password for the AWS Certificates so write it down, then follow the standard instructions to update the hubs firmware buy pressing and holding the reset button when you plug the power in, then the hub will connect to the cloud, or the docker web instance will also cache the firmware locally as that is useful.

### Newer hubs or hubs already upgraded

If you have a H010 revision hub or have already upgraded the firmware then you need to get a soldering iron out to get the password. First you need a TTL 3.3v Serial Adapter that you solder onto the Hub Mainboard. This will of course void any warranty and don't blame me if you brick your hub, that being said, it isn't that hard. I recommend soldering to the side connector to pins 3, 7 & 8 as per: 

https://github.com/plambrechtsen/pethublocal/tree/main/docs/Hub

Then if you have it working on 576000/8/N/1 you should see the standard boot message when the hub normally. You should save the console log output to a file, as the firmware update generates about 20k lines, so if you are using Windows and Putty change the scroll back to 200000 or some large number.
Then press and hold the reset button underneath, watch the firmware be re-applied and then there is this python script: [fwlogtopw.py](docker/source/fwlogtopw.py)

Which takes the output of the firmware update and prints the serial number.

### [PolarProxy](PolarProxy)

After you have the password you can use [PolarProxy](PolarProxy) and view wireshark PCAPs of all traffic the hub talks to the cloud service.

## [Zigsniff](zigsniff)

Zigsniff is a docker compose that uses a CC2531 to sniff all the 802.14.5 / MiWi / Zigbee traffic and then log it to a wireshark pcap file then translate it using PetHub.
This is really helpful for analysis of network traffic from the hub to the remote devices.
It doesn't need to run as a docker container, and the decryption of the MiWi traffic you check out the xor key to dexor the packets into pethubpacket.

### Python supporting code for zigsniff
The xor key and pethub packet are needed for decrypting the 802.14.5/MiWi traffic:
[pethubpacket.py](docker/source/pethubpacket.py)
[pethubpacket.xorkey](docker/source/pethubpacket.xorkey)

## [Docs](docs)

Various documentation I have found along the way and of the analysis of the Hub, a feeder and pet door and photo of the internal hub including pin outs and how to connect up the serial port.
 
## [WemosMRFShield](WemosMRFShield)

Documentation on how to build a local hub replacement using a Wemos D1 Mini either the ESP32 or ESP8266 version and a custom build hardware shield based off https://doc.riot-os.org/group__boards__esp32__mh-et-live-minikit.html

## [WemosPetHub](WemosPetHub)

The arduino code to run the pet hub connect on a Wemos D1 Mini ESP32 or ESP32 and MRF24J40 using the MRF shield built above. This code is not exactly functional and needs work, but has been abandonded due to getting the hub messages completely with PolarProxy and finding the AWS MTLS Certificate Password for the hub.
