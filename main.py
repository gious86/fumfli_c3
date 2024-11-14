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

wdt = machine.WDT(timeout=25000)
wdt.feed()

led = neopixel.NeoPixel(machine.Pin(8), 1)
led[0] = (20,20,0)
led.write()
    
out1 = machine.Pin(7, machine.Pin.OUT)
    
def tim0_callback(t):
    print("*")
    
def tim1_callback(t):
    out1.off()
    led[0] = (20,20,0)
    led.write()
    
tim0 = machine.Timer(0)
#tim0.init(period=5000, mode=machine.Timer.PERIODIC, callback=tim0_callback)

tim1 = machine.Timer(1)

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
if reset_cause==machine.PWRON_RESET:
    print('PWRON_RESET')
elif reset_cause==machine.HARD_RESET:
    print('HARD_RESET')
elif reset_cause==machine.WDT_RESET:
    print('WDT_RESET')
elif reset_cause==machine.DEEPSLEEP_RESET:
    print('DEEPSLEEP_RESET')
elif reset_cause==machine.SOFT_RESET:
    print('SOFT_RESET')



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


ws = AsyncWebsocketClient(5)

card = 0

async def wifi_connect(aps, delay_in_msec: int = 3000) -> network.WLAN:
    
    wifi = net.WLAN(net.STA_IF)
    
    wifi.active(1)
    count = 1
    
    while not wifi.isconnected(): 
        for ap in aps:
            for attempt in range(1,3):
                print(f"WiFi connecting to:{ap['ssid']}.Round {count}. Attempt {attempt}.")
                #led[0] = (0,0,1)
                #led.write()
                await a.sleep_ms(500)
                #led[0] = (0,0,0)
                #led.write()
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
                #led[0] = (1,0,0)
                #led.write()
                break
        count += 1
        if count>5:
            machine.reset()

    if wifi.isconnected():
        print("ifconfig: {}".format(wifi.ifconfig()))
    else:
        print("Wifi not connected.")
    
    return wifi

unlock_time = config['unlock_time']
async def sesam_open(outputs):
    out1.on()
    led[0] = (0,255,0)
    led.write()
    tim1.init(period=unlock_time, mode=machine.Timer.ONE_SHOT, callback=tim1_callback)
  
connected = False
server_last_seen = time.ticks_ms()
async def heart_beat():
    global ws
    global connected
    global server_last_seen
    
    c = 0
    while True:
        wdt.feed()
        gc.collect()
        if connected:
            if time.ticks_diff(time.ticks_ms(), server_last_seen) > 10000:
                await ws.close()
                server_last_seen = time.ticks_ms()
                print('timeout')
        await a.sleep(1)
        c = c+1
        if c>20 :
            c=0
            if ws is not None:
                #if await ws.open(): 
                await ws.send('*')
                print(f'tick')
                s = os.statvfs('//')
                print('Free Disk:{0} MB'.format((s[0]*s[3])/1048576))
                F = gc.mem_free()
                A = gc.mem_alloc()
                T = F+A
                P = '{0:.2f}%'.format(F/T*100)
                print('RAM Total:{0} Free:{1} ({2})'.format(T,F,P))
                print("Local time：%s" %str(time.localtime()))
                ws.close()
       
uart = machine.UART(1, 9600, tx=5, rx=4)                         
uart.init(9600, bits=8, parity=None, stop=1)
            
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
                    tim1 = machine.Timer(1)
                    led[0] = (255,0,0)
                    led.write()
                    tim1.init(period=1000, mode=machine.Timer.ONE_SHOT, callback=tim1_callback)
                    print('card not found')
                    
async def main_loop():
    global config
    global ws
    global server_last_seen
    global connected
    
    wifi = await wifi_connect(aps)
    mac = ubinascii.hexlify(wifi.config('mac')).decode().upper()
    print(f'mac:{mac}')
    
    print('checking ota update...')
    ota_update(config['ota_server_address'], config['model'], ota_files)
    
    wdt.feed()
    print("Local time before synchronization：%s" %str(time.localtime()))
    try:    
        ntptime.settime()
    except Exception as e:
        print(f'ntp error: {e}')
    print("Local time after synchronization：%s" %str(time.localtime()))
    
    ec = 0
    while True:           
        try:
            connected = False
            print (f'connecting to {server_address}/{mac}')
            if not await ws.handshake(f'{server_address}/{mac}'):
                print('Handshake error.')
                raise Exception('Handshake error.')
            if ws is not None:
                #if await ws.open(): 
                await ws.send('{"model":"%s"}' %config['model'])
                ec = 0
            #while await ws.open():
            server_last_seen = time.ticks_ms()
            connected = True
            while True:
                data = await ws.recv()
                if data is not None:
                    server_last_seen = time.ticks_ms()
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
                else:
                    break
                await a.sleep_ms(50)        
        except Exception as ex:
            print(f'Exceptionn: {ex}')
            #ec = ec+1
            #if ec > 5:
            #    machine.reset()
            await a.sleep(60)

  
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



