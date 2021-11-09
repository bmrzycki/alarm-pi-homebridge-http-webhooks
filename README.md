# Home alarm wiring to Pi GPIO bridge to homebridge-http-webhooks
The [homebridge-http-webhooks plugin](https://www.npmjs.com/package/homebridge-http-webhooks "homebridge-http-webhooks plugin")
provides an excellent interface to HomeKit contact sensors via a simple HTTP
API. This server uses the GPIO pins on a
[Raspberry Pi](https://www.raspberrypi.org/ "Raspberry Pi") to read home alarm
zone information directly from passive sensors like
[magnetic switches](https://en.wikipedia.org/wiki/Reed_switch "magnetic switches").
By doing so you can build an inexpensive home monitoring system integrated
into HomeKit.

# Installation
Copy `srv.py` and `default.cfg` anywhere you'd like. It can also be run
directly from the Git repo. By default `srv.py` reads `default.cfg` for its
configuration information but you can use the `-c` parameter to use a custom
configuration file. The program is Python 3 and requires the
[RPi.GPIO](https://pypi.org/project/RPi.GPIO/ "RPi.GPIO") module. If you're
using [Raspbian Linux](https://www.raspbian.org/ "Raspbian Linux") it's
installed by default. The user running `srv.py` needs to also have permissions
to setup and read the Pi GPIO pins. On Raspbian the user needs to be a member
of the `gpio` group (the default user `pi` is already a member).

# Software setup
The `default.cfg` file contains all available parameters and documentation
for each parameter as comments. The server utilizes `syslog` for its messages.

# homebridge-http-webhooks setup
The Homebridge plugin requires a 1:1 mapping from each GPIO pin on the Pi to a
webhooks Contact sensor `AccessoryId`. The configuration also requires `HTTP`
and no login authentication to update or change webhook accessories.

# Hardware setup
Many recently built homes are pre-wired for security systems. This often
includes simple magnetic window and door sensors. These are the kinds of
sensors, which act as simple switches, you want to wire into the GPIO pins.
Devices like motion detectors require more complicated wiring setups and are
not supported.

First, identify the sensor (or sensor groups) known as zones you wish to
monitor with the Pi's GPIO pins. If they are connected to a home security
system it's best if you disconnect them first.

Next, select [Pi GPIO pins](https://pinout.xyz/ "Pi GPIO pins") for each
of your zones. It's best to use GPIO pins that don't have a special use:
5, 6, 16, 17, 22, 23, 24, 25, 26, 27.

Physical wiring is fairly straightforward:
```
Pi +3v3 Power (pin 1 or 17)
  o---------+-----------+
            |           |
            |            \
     +-->|--+             \  Switch
     |  1N4001 diode    o
     |                  |
  o--+------------------+
GPIO N input
```
While not required it's a good idea to add the diode to dissapate inductive
load when the switch changes state as a
[flyback diode](https://en.wikipedia.org/wiki/Flyback_diode "flyback diode").
