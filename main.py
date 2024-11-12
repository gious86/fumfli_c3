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
import array
from random import randint
import urequests


#*****************************
'''
cards = array.array("I")
for _ in range(5000):
    cards.append(randint(111111,222222))
cards.append(2590189)
for _ in range(5000):
    cards.append(randint(111111,222222))
cards.append(2434289)
for _ in range(5000):
    cards.append(randint(111111,222222))
    '''
#*****************************

cards = array.array("I")
def get_cards(host, mac, auth = None, timeout=5):
    print(f'getting cards from {host}/get_cards/{mac}')
    try:
        if auth:
            response = urequests.get(f'{host}/get_cards/{mac}', headers={'Authorization': f'Basic {auth}'}, timeout=timeout)
        else:
            response = urequests.get(f'{host}/get_cards/{mac}', timeout=timeout)
        response_status_code = response.status_code
        response_content = response.content
        response.close()
        if response_status_code != 200:
            print(f'error, can not get cards')
            return False
        with open('cards', 'wb') as f:
            f.write(response_content)
            print('done')
    except Exception as e:
        print(f'error: {e}')
        
def get_config(host, mac, auth = None, timeout=5):
    print(f'getting config from {host}/get_config/{mac}')
    try:
        if auth:
            response = urequests.get(f'{host}/get_config/{mac}', headers={'Authorization': f'Basic {auth}'}, timeout=timeout)
        else:
            response = urequests.get(f'{host}/get_config/{mac}', timeout=timeout)
        response_status_code = response.status_code
        response_content = response.content
        response.close()
        if response_status_code != 200:
            print(f'error, can not get config')
            return False
        with open('temp_config.json', 'wb') as f:
            f.write(response_content)
            print('done')
    except Exception as e:
        print(f'error: {e}')

def load_cards():
    #"I"
    global cards
    cards = array.array("I")
    print("loading cards..")
    try:
        with open('cards', 'rb') as f:
            while True:
                b = f.read(4)
                if not b:
                    break
                card = int.from_bytes(b)
                cards.append(card)
    except Exception as e:
        print(f'error: {e}')
    print(len(cards))
    
def check_card(card):
    global cards
    for i in range(len(cards)):
        if cards[i]==card:
            return True
    return False
    
    

reset_cause = machine.reset_cause()
print(f'reset cause: {reset_cause}')

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
                    try:
                        wifi.connect(ap['ssid'], ap['password'])
                    except Exception as e:
                        print(f'exception:{e}')
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
        gc.collect()
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
       
uart = machine.UART(1, 9600, tx=5, rx=4)                         
uart.init(9600, bits=8, parity=None, stop=1)
#uart.write('abc')
            
async def read_loop():
    global ws
    global card
    
    while True:
        await a.sleep_ms(10)
        if ws is not None and card > 0:
            if await ws.open(): 
                await ws.send('{"card":"%s"}' %str(card))
                card = 0
        if uart.any():
            await a.sleep_ms(20)
            b = uart.read()
            l = len(b)
            
            if (l < 9) or (b[0] != 2) or (b[1] != l) or (b[l-1] != 3):
                print('uart: wrong format')
            else:
                c = int.from_bytes(b[l-6:l-2])
                print(f'uart: card {c}')
                if check_card(c):
                    await sesam_open([1])
                    print('welcome')
                else:
                    print('card not found')
                    
async def main_loop():
    global config
    global ws  
    
    wifi = await wifi_connect(aps)
    mac = ubinascii.hexlify(wifi.config('mac')).decode().upper()
    print(f'mac:{mac}')
    
    print('checking ota update...')
    ota_update(config['ota_server_address'], config['model'], ota_files)
    
    print("Local time before synchronization：%s" %str(time.localtime()))
    ntptime.settime()
    print("Local time after synchronization：%s" %str(time.localtime()))
    
    ec = 0
    while True:           
        try:
            print (f'connecting to {server_address}/{mac}')
            if not await ws.handshake(f'{server_address}/{mac}'):
                print('Handshake error.')
                raise Exception('Handshake error.')
            if ws is not None:
                if await ws.open(): 
                    await ws.send('{"model":"%s"}' %config['model'])
                    ec = 0
                    print('***')
            while await ws.open():
                print('.')
                data = await ws.recv()
                if data is not None:
                    print(f"\nData from ws: {data}")
                    js = None
                    try:
                        js = json.loads(data)
                    except:
                        pass    
                    if js:
                        if 'open' in js:
                            await sesam_open(js['open'])
                        if 'cmd' in js:
                            cmd = js['cmd']
                            if cmd == 'reset':
                                machine.reset()
                            elif cmd == 'sync':
                                print('sync')
                                get_cards(host = config['config_host'], mac = mac)
                                load_cards()
                                get_config(host = config['config_host'], mac = mac)
                await a.sleep_ms(50)
        except Exception as ex:
            print(f'Exceptionn: {ex}')
            ec = ec+1
            if ec > 5:
                machine.reset()
            await a.sleep(1)

  
async def main():    
    tasks = [main_loop(), heart_beat(), read_loop()]
    await a.gather(*tasks)
    
    
def on_card(id):
    #print(f'card:{id}')
    global card
    card = id
 
load_cards()
for i in range(len(cards)):
    print(f'{i}:{cards[i]}')
        
reader = wiegand(9, 8, on_card)
 

a.run(main())



