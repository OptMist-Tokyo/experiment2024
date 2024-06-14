from machine import enable_irq, disable_irq, idle
from machine import Pin, Timer
import network
import socket
import time
import uasyncio as asyncio
import math
import re

class HX711:
    def __init__(self, pSCK, pOUT):
        self.pSCK = pSCK
        self.pOUT = pOUT
        self.pSCK.value(False)

        self.GAIN = 1

    def read(self):
        for _ in range(500):
            if self.pOUT() == 0:
                break
            time.sleep_ms(1)
        else:
            raise OSError("Sensor does not respond.")

        result = 0
        for j in range(24 + self.GAIN):
            state = disable_irq()
            self.pSCK(True)
            self.pSCK(False)
            enable_irq(state)
            result = (result << 1) | self.pOUT()

        result >>= self.GAIN
        if result > 0x7fffff:
            result -= 0x1000000
        return result

OFFSET = - 690
DIV = 412.5
STABLE_VAR = 1.0
LIST_SIZE = 10
CHANGED_THRE = 5
ZERO_THRE = 10
body_weight = 60
refresh_interval = 10000
consumed_per_min = 1.25 * body_weight / 60
MINUTE = 60
HOUR = 60 * MINUTE
DAY = 24 * HOUR

pin_OUT = Pin(11, Pin.IN, pull=Pin.PULL_DOWN)
pin_SCK = Pin(10, Pin.OUT)
hx711 = HX711(pin_SCK, pin_OUT)
led = Pin(0, Pin.OUT)

prv_mean = None
val_list = []
intake_list = []
tbw = 0

from secrets import secrets
ssid = secrets['ssid']
password = secrets['password']
IP_ADDRESS = '192.168.86.41'
LISTEN_PORT = 80
from index import html

def measure():
    global prv_mean, tbw
    val = hx711.read() / DIV - OFFSET
    val_list.append(val)
    if len(val_list) > LIST_SIZE:
        val_list.pop(0)
    mean = sum(val_list) / len(val_list)
    var = sum((val - mean) ** 2 for val in val_list) / len(val_list)
    now = time.mktime(time.gmtime())
    # print(val, mean, var)
    print(val)
    if prv_mean is None:
        prv_mean = mean
    else:
        intake = prv_mean - mean
        if abs(intake) >= CHANGED_THRE and mean >= ZERO_THRE and var <= STABLE_VAR:
            # if mean - prv_mean >= CHANGED_BOTTLE_THRE:
            #     print("botttle is empty!")
            # else:
            if intake > 0:
                # print(f"intake of water: {intake}, time: {now}")
                tbw += intake
                intake_list.append((intake, now))
            prv_mean = mean
    if len(intake_list) > 0 and now - intake_list[0][0] > DAY:
        intake_list.pop(0)

def connect_wlan():

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    for _ in range(10):
        print('Connecting to Wi-Fi router')
        if wlan.status() < 0 or wlan.status() >= 3:
            break
        time.sleep(1)
    if wlan.status() == 3:
        wlan_status = wlan.ifconfig()
        wlan.ifconfig((IP_ADDRESS, wlan_status[1], wlan_status[2], wlan_status[3]))
        print("Connected!")
    else:
        pass
        # raise RuntimeError('Connection failed: '+str(wlan.status()))

async def http_server(reader, writer):
    global body_weight, refresh_interval
    peer_ip = reader.get_extra_info('peername')[0]
    # print(f"Client connected from {peer_ip}")
    request_line = await reader.readline()
    # print("Request:")
    # print(request_line)
    while await reader.readline() != b'\r\n':
        pass
    request = str(request_line)
    if 'weight' in request:
        body_weight = int(re.search(r'weight=(\d+)', request).group(1))
        refresh_interval = int(re.search(r'interval=(\d+)', request).group(1)) * 1000
        # print(body_weight)
    consumed_per_min = 1.25 * body_weight / 60
    
    if 'human.svg' in request:
        with open('human.svg','rb') as f:
            data = f.read()
        response = data.decode()
        writer.write('HTTP/1.0 200 OK\r\nContent-type: image/svg+xml\r\n\r\n')
        writer.write(response)
    elif 'human_back.svg' in request:
        with open('human_back.svg','rb') as f:
            data = f.read()
        response = data.decode()
        writer.write('HTTP/1.0 200 OK\r\nContent-type: image/svg+xml\r\n\r\n')
        writer.write(response)
    else:
        now = time.mktime(time.gmtime())
        hist = [0] * 24
        for (intake, t) in intake_list:
            i = min(23, int((now - t) / 24))
            hist[i] += intake
        hist_acc = hist.copy()
        for i in range(1, 24):
            hist_acc[i] += hist_acc[i - 1]
        sum_intake = hist_acc[-1]

        hydrate_time = max(0, math.ceil(tbw / consumed_per_min))
        ratio_intake = sum_intake / (body_weight * 20) * 100
        response = html % {'ref_url': IP_ADDRESS,
                           'sum_intake': sum_intake, 'hydrate_time': hydrate_time,
                           'hist': str(hist), 'hist_acc': str(hist_acc),
                           'refresh_interval': refresh_interval}
        writer.write('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
        writer.write(response)
    
    await writer.drain()
    await writer.wait_closed()
    # print(f"Connection from {peer_ip} closed")

def run():
    global tbw
    sum_intake = 0
    tbw = consumed_per_min * 60
    prv = time.mktime(time.gmtime())
    while True:
        measure()
        crt = time.mktime(time.gmtime())
        if crt >= prv + MINUTE:
            tbw -= consumed_per_min
            prv = crt
            
        print(crt, tbw)
        if tbw <= 0:
            # print(f"hydrate yourself! TBW={tbw}")
            for _ in range(2):
                led.value(0)
                await asyncio.sleep(0.02)
                led.value(1)
                await asyncio.sleep(0.03)
        else:
            led.value(0)
            await asyncio.sleep(0.1)


async def main():
    connect_wlan()

    asyncio.create_task(asyncio.start_server(http_server, IP_ADDRESS, LISTEN_PORT))
    await run()

if __name__ == '__main__':
    led.value(1)
    time.sleep(0.1)
    led.value(0)
    try:
        asyncio.run(main())

    except OSError as e:
        print(f"ERROR: {e}")

    finally:
        asyncio.new_event_loop()

