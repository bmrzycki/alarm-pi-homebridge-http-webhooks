#!/usr/bin/env python3

import argparse
import syslog

import RPi.GPIO as gpio

from configparser import ConfigParser
from pathlib import Path
from json import loads
from signal import signal, SIGPIPE, SIG_DFL
from sys import argv
from time import sleep
from urllib.parse import quote
from urllib.request import urlopen

CHANNEL = {  # Key is GPIO number as int
    # id -> str  # Webhooks AccessoryId
}
GLOBAL = {
    'url_timeout' : 5.0,
    'update'      : 180,
}
PI_PIN = {  # GPIO number -> Pi physical pin
    0  : 27,  # EEPROM SDA
    1  : 28,  # EEPROM SCL
    2  : 3,   # I2C1 SDA
    3  : 5,   # I2C1 SCL
    4  : 7,   # GPCLK0
    5  : 29,
    6  : 31,
    7  : 26,  # SPI0 CE1
    8  : 24,  # SPI0 CE0
    9  : 21,  # SPI0 MISO
    10 : 19,  # SPI0 MOSI
    11 : 23,  # SPI0 SCLK
    12 : 32,  # PWM0
    13 : 33,  # PWM1
    14 : 8,   # UART TX
    15 : 10,  # UART RX
    16 : 36,
    17 : 11,
    18 : 12,  # PCM CLK
    19 : 35,  # PCM FS
    20 : 38,  # PCM DIN
    21 : 40,  # PCM DOUT
    22 : 15,
    23 : 16,
    24 : 18,
    25 : 22,
    26 : 37,
    27 : 13,
}
SECURITY = {
    'id' : '',
}
WEBHOOKS = {
    'host'  : '127.0.0.1',
    'port'  : 51828,
    'delay' : 0.2,
}

def error(msg):
    syslog.syslog(syslog.LOG_ERR, msg)


def info(msg):
    syslog.syslog(syslog.LOG_INFO, msg)


def whook(args):
    url, query = f"http://{WEBHOOKS['host']}:{WEBHOOKS['port']}/", []
    for k in args:
        query.append(f"{quote(k)}={quote(args[k])}")
    if query:
        url += '?' + '&'.join(query)
    try:
        rsp = urlopen(url=url, timeout=GLOBAL['url_timeout'])
    except Exception as e:
        error(f"HTTP request exception {e} for url='{url}'")
        return False, {}
    if rsp.status != 200:
        error(f"bad status={rsp.status} for url='{url}'")
        return False, {}
    return True, loads(rsp.read())


def trigger():
    if not SECURITY['id']:
        return
    ok, data = whook({'accessoryId' : SECURITY['id']})
    if not ok:
        return
    try:
        state = int(data['currentState'])
    except Exception as e:
        error(f"currentState {str(e)} from data={data}")
        return
    state = { 0 : 'home',
              1 : 'away',
              2 : 'night',
              3 : 'off',
              4 : 'triggered' }.get(state, 'unknown')
    if state in ('off', 'triggered', 'unknown'):
        if state == 'unknown':
            error(f"invalid security response data={data}")
        return
    ok, data = whook({'accessoryId'  : SECURITY['id'],
                      'currentstate' : 4})
    if ok:
        info(f"triggered by id='{SECURITY['id']}' data={data}")


def callback(channel):
    value, acc = gpio.input(channel), CHANNEL[channel]['id']
    ok, _ = whook({'accessoryId' : acc,
                   'state'       : {1 : 'true', 0 : 'false'}[value]})
    if ok:
        d = {1 : 'closed (contact)', 0 : 'open (no contact)'}
        info(f"{d[value]} accessoryId='{acc}' value='{value}'")
    if value == 0:
        trigger()


def main(args_raw):
    p = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Home alarm monitor using Raspberry Pi GPIO pins and'
        ' Homebridge with the homebridge-http-webhooks plugin')
    p.add_argument(
        '-c', '--config',
        type=argparse.FileType('r', encoding='utf-8'),
        default=str(Path(__file__).parent.resolve().joinpath('default.cfg')),
        help='config file')
    p.add_argument(
        '-v', '--verbose',
        default=0, action='count',
        help='verbosity, repeat to increase')
    args = p.parse_args(args_raw)
    cfg = ConfigParser()
    try:
        cfg.read_file(args.config)
    except Exception as e:
        p.error(str(e))

    GLOBAL['url_timeout'] = cfg.getfloat('global', 'url_timeout',
                                         fallback=GLOBAL['url_timeout'])
    GLOBAL['update'] = cfg.getint('global', 'update',
                                  fallback=GLOBAL['update'])
    WEBHOOKS['host'] = cfg.get('webhooks', 'host',
                               fallback=WEBHOOKS['host'])
    WEBHOOKS['port'] = cfg.getint('webhooks', 'port',
                                  fallback=WEBHOOKS['port'])
    WEBHOOKS['delay'] = cfg.getfloat('webhooks', 'delay',
                                     fallback=WEBHOOKS['delay'])
    SECURITY['id'] = cfg.get('security', 'id',
                             fallback=SECURITY['id'])
    for sect in cfg.sections():
        if sect.startswith('gpio.'):
            g = sect.partition('.')[2]
            try:
                channel = int(g)
            except Exception as e:
                p.error(f"GPIO '{g}' {str(e)} in {sect}")
            if channel not in PI_PIN:
                p.error(f"invalid GPIO {channel} in {sect}")
            acc = cfg.get(sect, 'id', fallback='')
            if not acc:
                p.error(f"missing id in {sect}")
            CHANNEL[channel] = { 'id' : acc }

    if args.verbose:
        for d, n in ((GLOBAL, 'global'), (WEBHOOKS, 'webhooks'),
                     (CHANNEL, 'channel'), (SECURITY, 'security')):
            for k in sorted(d):
                if n == 'channel':
                    print(f"{n}.{k} = {d[k]}  # Pi pin {PI_PIN[k]}")
                else:
                    print(f"{n}.{k} = {d[k]}")

    syslog.openlog('alarmd', logoption=syslog.LOG_PID)
    gpio.setmode(gpio.BCM)
    for channel in CHANNEL:
        gpio.setup(channel, gpio.IN, pull_up_down=gpio.PUD_DOWN)
        gpio.add_event_detect(channel, gpio.BOTH, callback)

    try:
        while True:
            for channel in CHANNEL:
                callback(channel)
                sleep(WEBHOOKS['delay'])
            sleep(GLOBAL['update'])
    except KeyboardInterrupt:
        p.error("aborted with CTRL-C")
    finally:
        gpio.cleanup()


if __name__ == '__main__':
    signal(SIGPIPE, SIG_DFL)  # Avoid exceptions for broken pipes
    main(argv[1:])
