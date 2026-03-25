from gpiozero import OutputDevice
import time
import math
import spidev

WIDTH = 480
HEIGHT = 320

DC = 6
RST = 5
BL = 12
SPI_BUS = 0
SPI_DEV = 0
SPI_HZ = int(62.5e6)

class ST7796:
    def __init__(self, spi_bus = SPI_BUS, spi_dev = SPI_DEV, dc = DC, rst = RST, bl = BL):
        self.width = WIDTH
        self.height = HEIGHT

        self.dc = OutputDevice(dc)
        self.rst = OutputDevice(rst)
        self.bl = OutputDevice(bl)

        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_dev)
        self.spi.max_speed_hz = SPI_HZ
        self.spi.mode = 0

        self.reset()
        self.init_display()
        self.bl.on()

    def reset(self):
        self.rst.on()
        time.sleep(0.05)
        self.rst.off()
        time.sleep(0.05)
        self.rst.on()
        time.sleep(0.15)

    def cmd(self, c):
        self.dc.off()
        self.spi.writebytes([c])

    def data(self, d):
        self.dc.on()
        if isinstance(d, int):
            self.spi.writebytes([d])
        else:
            chunk = 4096
            for i in range(0, len(d), chunk):
                self.spi.writebytes(d[i:i + chunk])

    def init_display(self):
        self.cmd(0x01)
        time.sleep(0.15)

        self.cmd(0x11)
        time.sleep(0.12)

        self.cmd(0x36)
        self.data(0xE8)

        self.cmd(0x3A)
        self.data(0x55)

        self.cmd(0xF0)
        self.data(0xC3)
        self.cmd(0xF0)
        self.data(0x96)

        self.cmd(0xB4)
        self.data(0x01)

        self.cmd(0xB7)
        self.data(0xC6)

        self.cmd(0xC0)
        self.data([0x80, 0x45])

        self.cmd(0xC1)
        self.data(0x13)

        self.cmd(0xC2)
        self.data(0xA7)

        self.cmd(0xC5)
        self.data(0x1A)

        self.cmd(0xE8)
        self.data([0x40, 0x8A, 0x00, 0x00, 0x29, 0x19, 0xA5, 0x33])

        self.cmd(0xE0)
        self.data([0xF0, 0x06, 0x0B, 0x08, 0x07, 0x05, 0x2E, 0x33, 0x47, 0x3A, 0x17, 0x16, 0x2E, 0x31])

        self.cmd(0xE1)
        self.data([0xF0, 0x09, 0x0D, 0x09, 0x08, 0x23, 0x2E, 0x33, 0x46, 0x38, 0x13, 0x13, 0x2C, 0x32])

        self.cmd(0xF0)
        self.data(0x3C)
        self.cmd(0xF0)
        self.data(0x69)

        self.cmd(0x21)
        self.cmd(0x29)
        time.sleep(0.05)

    def set_window(self, x0, y0, x1, y1):
        self.cmd(0x2A)
        self.data([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])
        self.cmd(0x2B)
        self.data([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])
        self.cmd(0x2C)

    def show(self, image):
        if image.size != (self.width, self.height):
            image = image.resize((self.width, self.height))
        rgb = image.convert("RGB")
        raw = rgb.load()

        buf = bytearray(self.width * self.height * 2)
        p = 0
        for y in range(self.height):
            for x in range(self.width):
                r, g, b = raw[x, y]
                rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                buf[p] = rgb565 >> 8
                buf[p + 1] = rgb565 & 0xFF
                p += 2

        self.set_window(0, 0, self.width - 1, self.height - 1)
        self.data(buf)