from umachine import Pin
import utime as time

class wiegand:
    def __init__(self, w0_pin, w1_pin, on_card):
        self.w0_pin = Pin(w0_pin, Pin.IN, Pin.PULL_UP)
        self.w1_pin = Pin(w1_pin, Pin.IN, Pin.PULL_UP)
        self.on_card = on_card
        self.w0_pin.irq(trigger=Pin.IRQ_FALLING, handler=self.on_w0)
        self.w1_pin.irq(trigger=Pin.IRQ_FALLING, handler=self.on_w1)
        self.bits = 26
        self.card = 0
        self.start = 0
        
    
    def on_w0(self, s):
        self.on_w(0)
    
    
    def on_w1(self, s):
        self.on_w(1)
    
    
    def on_w(self, val):
        now = time.ticks_ms()
        if now - self.start > 500:
            self.bits = 25
            self.start = now
            self.card = 0
        self.card |= val << self.bits
        if self.bits == 0:
            self.start = 0
            self.ready = False
            c = self.card >> 1
            c &= 0xffffff
            self.on_card(c)
        else :
            self.bits -= 1
            
        
    def check_pairty(card):
        pass
    
    

            
        
        
        
    
            