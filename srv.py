#!/usr/bin/env python3
"Home alarm using Pi GPIO to webhooks HomeKit bridge."

import syslog

from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, FileType
from configparser import ConfigParser
from pathlib import Path
from json import loads
from signal import signal, SIGPIPE, SIG_DFL
from sys import argv
from time import time, sleep
from urllib.parse import quote
from urllib.request import urlopen

from gpiozero import Button

VERBOSE = 0
WEBHOOK = None
ZONES = []


def error(msg):
    """
    Send error-level msg to syslog.
    """
    syslog.syslog(syslog.LOG_ERR, msg)
    if VERBOSE:
        print(f"error: {msg}")


def info(msg):
    """
    Send info-level msg to syslog.
    """
    syslog.syslog(syslog.LOG_INFO, msg)
    if VERBOSE:
        print(f"info: {msg}")


class Zone:
    """
    Zone class to track the GPIO and Button info.
    """

    def __init__(self, gpio, name, security_name=""):
        self.gpio = gpio
        self.name = name
        self.security_name = security_name
        self.button = Button(pin=gpio, pull_up=False)
        self.button.when_pressed = self.update
        self.button.when_released = self.update

    def __str__(self):
        return f"zone '{self.name}' (GPIO {self.gpio})"

    def update(self):
        """
        Update the webhook bridge with current state.
        """
        is_active, state = self.button.is_active, "false"
        if is_active:
            state = "true"
        good, _ = WEBHOOK.send({"accessoryId": self.name, "state": state})
        if not good:
            error(f"failed to update {self}")
            return
        if self.security_name and not is_active:
            self.trigger()

    def trigger(self):
        """
        Triggers an alarm event.
        """
        good, data = WEBHOOK.send({"accessoryId": self.security_name})
        if not good:
            error(f"bad check of security name '{self.security_name}'")
            return
        try:
            state_num = int(data.get("currentState", ""))
        except ValueError:
            error(f"bad currentState in data={data}")
            return
        state = {0: "home", 1: "away", 2: "night", 3: "off", 4: "triggered"}.get(
            state_num, "unknown"
        )
        # Trigger events for all states except off and already-triggered.
        if state in ("off", "triggered", "unknown"):
            if state == "unknown":
                error(f"invalid security response data={data}")
            return
        # Send currentstate == 4 -> Triggered. Note the name case changed!
        good, data = WEBHOOK.send(
            {"accessoryId": self.security_name, "currentstate": 4}
        )
        if good:
            info(f"alarm triggered by {self}")


class WebHook:
    """
    Setup the WebHook URL caller and supported data.
    """

    def __init__(self, host="127.0.0.1", port=51828, delay=0.4, timeout=5.0):
        self.host = host
        self.port = port
        self.delay = delay
        self.timeout = timeout
        self._last = time()

    def __str__(self):
        return f"http://{self.host}:{self.port}/"

    def send(self, data):
        """
        Send the webhook with the dictionary data.
        Returns a tuple of success_bool, returned_dict.
        """
        # Prevent slamming the webhooks server
        now = time()
        delta = now - self._last
        self._last = now
        if delta < self.delay:
            sleep(self.delay - delta)

        # Send the query
        url, query = str(self), []
        for key, value in data.items():
            query.append(
                "=".join([quote(str(key), safe=""), quote(str(value), safe="")])
            )
        if query:
            url += "?" + "&".join(query)
        info(f"webhook send url={url}")
        # pylint: disable=broad-exception-caught, consider-using-with
        try:
            rsp = urlopen(url=url, timeout=self.timeout)
        except Exception as err:
            error(f"HTTP request exception {err} for url='{url}'")
            return False, {}
        if rsp.status != 200:
            error(f"bad status={rsp.status} for url='{url}'")
            return False, {}
        return True, loads(rsp.read())


def main(args_raw):
    """
    Main routine.
    """
    parser = ArgumentParser(
        formatter_class=ArgumentDefaultsHelpFormatter,
        description=(
            "Home alarm monitor using Raspberry Pi GPIO pins and Homebridge with the"
            " homebridge-http-webhooks plugin"
        ),
    )
    parser.add_argument(
        "-c",
        "--config",
        type=FileType("r", encoding="utf-8"),
        default=str(Path(__file__).parent.resolve().joinpath("default.cfg")),
        help="config file",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        default=0,
        action="count",
        help="verbosity",
    )

    args = parser.parse_args(args_raw)
    # pylint: disable=global-statement
    global VERBOSE
    VERBOSE = args.verbose
    cfg = ConfigParser()
    cfg.read_file(args.config)

    # Setup a single WebHook object instance. We don't need to worry about locking
    # because writes to the REST API are serialized on the server side.
    global WEBHOOK
    WEBHOOK = WebHook(
        host=cfg.get("webhooks", "host", fallback="127.0.0.1"),
        port=cfg.getint("webhooks", "port", fallback=51828),
        timeout=cfg.getfloat("global", "url_timeout", fallback=5.0),
        delay=cfg.getfloat("webhooks", "delay", fallback=0.4),
    )

    # Setup all our Zone objects.
    security_name = cfg.get("security", "id", fallback="")
    for sect in cfg.sections():
        if sect.startswith("gpio."):
            gpio = int(sect.partition(".")[2])
            name = cfg.get(sect, "id", fallback="")
            if not name:
                parser.error(f"missing id in {sect}")
            ZONES.append(Zone(gpio=gpio, name=name, security_name=security_name))

    # Start the endless loop.
    update_interval = cfg.getint("global", "update", fallback=180)
    syslog.openlog("webhooks-alarmd", logoption=syslog.LOG_PID)
    try:
        while True:
            for zone in ZONES:
                zone.update()
            sleep(update_interval)
    except KeyboardInterrupt:
        parser.error("aborted with CTRL-C")


if __name__ == "__main__":
    signal(SIGPIPE, SIG_DFL)  # Avoid exceptions for broken pipes
    main(argv[1:])
