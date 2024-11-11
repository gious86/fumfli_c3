
import network as net
import time
import ubinascii
import uasyncio as a
from ws import AsyncWebsocketClient
import gc
import machine
import ujson as json
from wiegand import wiegand
import neopixel
from ota import ota_update
import ntptime
import os

print("loading config...")
f = open("/config.json")
text = f.read()
f.close()
config = json.loads(text)
del text
print(config)

aps = config['aps']
server_address = config['server_address']

ota_files=[]
for file in config['ota_filenames']:
    ota_files.append(file['file'])
print(ota_files)


led = neopixel.NeoPixel(machine.Pin(8), 1)
led[0] = (1,1,1)
led.write()

out1 = machine.Pin(7, machine.Pin.OUT)

ws = AsyncWebsocketClient(5)
lock = a.Lock()
data_from_ws = []


card = 0

async def wifi_connect(aps, delay_in_msec: int = 3000) -> network.WLAN:
    
    wifi = net.WLAN(net.STA_IF)
    
    wifi.active(1)
    count = 1
    #await a.sleep_ms(10000)
    while not wifi.isconnected(): 
        for ap in aps:
            for attempt in range(1,3):
                print(f"WiFi connecting to:{ap['ssid']}.Round {count}. Attempt {attempt}.")
                led[0] = (0,0,1)
                led.write()
                await a.sleep_ms(500)
                led[0] = (0,0,0)
                led.write()
                status = wifi.status()
                print(f"status: {status}")
                if wifi.isconnected(): #status == net.STAT_GOT_IP:
                    break
                if status != net.STAT_CONNECTING:
                    wifi.connect(ap['ssid'], ap['password'])
                await a.sleep_ms(delay_in_msec)
            if wifi.isconnected():
                led[0] = (1,0,0)
                led.write()
                break
        count += 1
        if count>5:
            machine.reset()

    if wifi.isconnected():
        print("ifconfig: {}".format(wifi.ifconfig()))
    else:
        print("Wifi not connected.")
    
    return wifi


async def sesam_open(outputs):
    out1.on()
    led[0] = (0,255,0)
    led.write()
    await a.sleep_ms(1000)
    led[0] = (1,0,0)
    led.write()
    out1.off()


async def heart_beat():
    global ws
    
    while True:
        await a.sleep(30)
        if ws is not None:
            if await ws.open(): 
                await ws.send('*')
                print('tick')
                s = os.statvfs('//')
                print('Free Disk:{0} MB'.format((s[0]*s[3])/1048576))
                F = gc.mem_free()
                A = gc.mem_alloc()
                T = F+A
                P = '{0:.2f}%'.format(F/T*100)
                print('RAM Total:{0} Free:{1} ({2})'.format(T,F,P))
                print("Local time：%s" %str(time.localtime()))
            
async def blink_loop():
    global lock
    global data_from_ws
    global ws
    global card
    

    while True:
        await a.sleep_ms(10)
        if ws is not None and card > 0:
            if await ws.open(): 
                await ws.send('{"card":"%s"}' %str(card))
                card = 0
        await lock.acquire() # lock data archive
        if data_from_ws:
            for data in data_from_ws:
                print(f"\nData from ws: {data}")
                js = None
                op = None
                try:
                    js = json.loads(data)
                except:
                    pass    
                if js:
                    if 'open' in js:
                        await sesam_open(js['open'])
                    if 'cmd' in js:
                        if js['cmd'] == 'reset':
                            machine.reset()

            data_from_ws = []                
        lock.release()
        gc.collect()

        

async def read_loop():
    global config
    global lock
    global data_from_ws


    wifi = await wifi_connect(aps)
    mac = ubinascii.hexlify(wifi.config('mac')).decode().upper()
    print(f'mac:{mac}')
    
    print('checking ota update...')
    ota_update(config['ota_server_address'], config['model'], ota_files)
    
    print("Local time before synchronization：%s" %str(time.localtime()))
    ntptime.settime()
    print("Local time after synchronization：%s" %str(time.localtime()))
    
    while True:
        gc.collect()           
        try:
            print (f'{server_address}/{mac}')
            if not await ws.handshake(f'{server_address}/{mac}'):
                print('Handshake error.')
                raise Exception('Handshake error.')
            if ws is not None:
                if await ws.open(): 
                    await ws.send('{"model":"%s"}' %config['model'])
                    print('***')
            while await ws.open():
                print('.')
                data = await ws.recv()
                if data is not None:
                    await lock.acquire()
                    data_from_ws.append(data)
                    lock.release()
                await a.sleep_ms(50)
        except Exception as ex:
            print(f'Exceptionn: {ex}')
            await a.sleep(1)

  
async def main():    

    tasks = [read_loop(), blink_loop(), heart_beat()]
    await a.gather(*tasks)
    
    
def on_card(id):
    #print(f'card:{id}')
    global card
    card = id
    
reader = wiegand(9, 8, on_card)
    
a.run(main())



