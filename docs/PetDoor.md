# Pet Door

The Pet Door sends a number of messages, the main ones we are interested in are the 132 and the 8.
Like the feeder the Mac address of the door in reverse order is the topic the messages are put on.

## Message type 8
The 8 messages are generate by the Feeder and the Hub. 

|MSG|00|01|02|03|04|05|06|07|08|09|10|11|12|
|--|--|--|--|--|--|--|--|--|--|--|--|--|--|
8|02|05|11|61|00|02|bc|44|02|b2|bc|03|2c
8|02|05|11|61|00|05|bd|44|03|b3|bd|02|2d
8|02|05|11|81|00|03|be|44|04|b4|be|01|2d
8|02|05|11|81|00|03|bf|44|05|b5|bf|01|2d
132|211|531|3|05|11|81

Standard message header offsets that don't change per message type:
| Offset | Message |
|-|-|
|8| Message Type 8 
|00| 00 - 05 and 20, ??? Perhaps seconds it took
|01| Hex counter that seems to go up every hour. Also 1-3 matches the 3 bytes from the packet 132 at offset 3-5
|02| ??
|03| Pet direction and I think speed. x0 looked in, x1 = Came in, x2 went out. the 6x seems to be sub-second, 8x or higher indicates how long they took.
|04| Always 00 except when 621 animal goes out
|05| ??  
|06| Hex counter that seems to go up with each 8 event, but not when offset 00 = 20
|07| Mostly 44, except when 621 animal goes out.
|08| Counter that goes 00-07 except when 621 animal goes out.
|09| Another hex counter
|10| Same value as offset 06
|11| Message count for timestamp, normally 01, but if multiple messages the 02/03 as shown above.
|12| ?? Perhaps CRC?

## Message type 132
The 132 messages are generate by the Feeder and the Hub. 

Refer to the hub documentation for tag id 33 for the hub messages.

|MSG|00|01|02|03|04|05|06|07|08|09|10|11|12|
|--|--|--|--|--|--|--|--|--|--|--|--|--|--|
132|254|33|3|9c|02|b2
8|00|00|32|62|00|11|36|44|04|2c|36|01|18
132|240|525|3|00|32|62
8|00|01|35|61|00|3f|37|44|05|2d|37|01|3d
132|248|525|3|01|35|61
8|20|0f|2f|d2|49|40|2d|9c|38|01|30|01|d6
132|173|621|9|0f|2f|d2|49|40|2d|9c|38|01

The above message shows first the hub message 33, then pet tag 1 aka 525 coming in, then going out. Lastly a 621 animal going out tag unknown.

Standard message header offsets that don't change per message type:
| Offset | Message |
|-|-|
|132| Message type
|C| Decimal message counter which is generated by the door and has a limit of 255
|01| Decimal Tag or hub device identifer. 33 message about the hub, 621 is a animal leaving that the tag wasn't scanned, 525 with an offset of 3 for each pet ie tag1=525, tag2=528 tag added to the door.
|02| Message length, always 3 including hub messages except 621 it is 9.
|03| Same as packet 8 offset 1-3 - ??
|04| ??
|05| Pet direction and I think speed. x0 looked in, x1 = Came in, x2 went out. the 6x seems to be sub-second, 8x or higher indicates how long they took.
|06-11| Only happens on 621 unknown animal left.