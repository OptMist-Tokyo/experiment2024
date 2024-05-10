# MIT License

# Copyright (c) 2019 

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from machine import enable_irq, disable_irq, idle
import time

class HX711:
    def __init__(self, pd_sck, dout, gain=128):
        self.pSCK = pd_sck
        self.pOUT = dout
        self.pSCK.value(False)

        self.GAIN = 0
        self.OFFSET = 0
        self.SCALE = 1

        self.time_constant = 0.25
        self.filtered = 0

        self.set_gain(gain);

    def set_gain(self, gain):
        if gain is 128:
            self.GAIN = 1
        elif gain is 64:
            self.GAIN = 3
        elif gain is 32:
            self.GAIN = 2

        self.read()
        self.filtered = self.read()

    def is_ready(self):
        return self.pOUT() == 0

    def read(self):
        # wait for the device being ready
        for _ in range(500):
            if self.pOUT() == 0:
                break
            time.sleep_ms(1)
        else:
            raise OSError("Sensor does not respond")

        # shift in data, and gain & channel info
        result = 0
        for j in range(24 + self.GAIN):
            state = disable_irq()
            self.pSCK(True)
            self.pSCK(False)
            enable_irq(state)
            result = (result << 1) | self.pOUT()

        # shift back the extra bits
        result >>= self.GAIN

        # check sign
        if result > 0x7fffff:
            result -= 0x1000000

        return result

    def power_down(self):
        self.pSCK.value(False)
        self.pSCK.value(True)

    def power_up(self):
        self.pSCK.value(False)


# Example for micropython.org device, gpio mode
# Connections:
# Pin # | HX711
# ------|-----------
# 12    | data_pin
# 13    | clock_pin
#

# from hx711 import HX711
from machine import Pin, Timer


pin_OUT = Pin(11, Pin.IN, pull=Pin.PULL_DOWN)
pin_SCK = Pin(10, Pin.OUT)

hx711 = HX711(pin_SCK, pin_OUT)

OFFSET = - 700
DIV = 412.5
STABLE_VAR = 0.1
LIST_SIZE = 10
CHANGED_THRE = 5
ZERO_THRE = 10
# CHANGED_BOTTLE_THRE = 20

prv_mean = None
val_list = []
intake_list = []

def measure(timer):
    global prv_mean
    val = hx711.read() / DIV - OFFSET
    val_list.append(val)
    if len(val_list) > LIST_SIZE:
        val_list.pop(0)
    mean = sum(val_list) / len(val_list)
    var = sum((val - mean) ** 2 for val in val_list) / len(val_list)
    # print(val, mean, var)
    if prv_mean is None:
        prv_mean = mean
    else:
        intake = prv_mean - mean
        if abs(intake) >= CHANGED_THRE and mean >= ZERO_THRE and var <= STABLE_VAR:
            # if mean - prv_mean >= CHANGED_BOTTLE_THRE:
            #     print("botttle is empty!")
            # else:
            if intake > 0:
                now = time.localtime()
                print("intake water!", intake, now)
                intake_list.append((intake, now))
            prv_mean = mean


timer = Timer()
timer.init(freq=10, mode=Timer.PERIODIC, callback=measure)

while True:
    time.sleep(1)
