import smbus
import time
from gpiozero import DigitalOutputDevice

RST_PIN = 13
reset_pin = DigitalOutputDevice(RST_PIN, initial_value=True)

bus = smbus.SMBus(1)
addr = 0x38

def read_touch():
    data = bus.read_i2c_block_data(addr, 0x02, 5)
    touches = data[0] & 0x0F
    if touches == 0:
        return None
    x = ((data[1] & 0x0F) << 8) | data[2]
    y = ((data[3] & 0x0F) << 8) | data[4]
    return x, y