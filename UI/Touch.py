import smbus
import time
from gpiozero import DigitalOutputDevice

RST_PIN = 13
reset_pin = DigitalOutputDevice(RST_PIN, initial_value=True)

bus = smbus.SMBus(1)
addr = 0x38

def reset_touch_controller(pulse_time=0.05, settle_time=0.15):
    # Most capacitive touch controllers on this board expect an active-low reset.
    reset_pin.on()
    time.sleep(pulse_time)
    reset_pin.off()
    time.sleep(pulse_time)
    reset_pin.on()
    time.sleep(settle_time)

def read_touch(retries=3, delay=0.003):
    last_point = None

    for _ in range(retries):
        try:
            data = bus.read_i2c_block_data(addr, 0x02, 5)
        except OSError:
            time.sleep(delay)
            continue

        touches = data[0] & 0x0F
        if touches == 0:
            time.sleep(delay)
            continue

        x = ((data[1] & 0x0F) << 8) | data[2]
        y = ((data[3] & 0x0F) << 8) | data[4]
        point = (x, y)

        if point == last_point:
            return point

        last_point = point
        time.sleep(delay)

    return last_point
