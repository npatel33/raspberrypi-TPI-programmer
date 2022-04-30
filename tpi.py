#! /bin/python3

import wiringpi
import spidev
import time
import sys

# setup GPIO
SS_PIN = 0
LOW = 0
HIGH = 1
wiringpi.wiringPiSetupGpio()
wiringpi.pinMode(SS_PIN, 1);
wiringpi.digitalWrite(SS_PIN, HIGH)

# setup SPI
spi = None

#define the instruction set bytes
SLD = 0x20
SLDp = 0x24
SST = 0x60
SSTp = 0x64
SSTPRH = 0x69
SSTPRL = 0x68

"""
#### see functions below ####
SIN  0b0aa1aaaa replace a with 6 address bits
SOUT 0b1aa1aaaa replace a with 6 address bits
SLDCS  0b1000aaaa replace a with address bits
SSTCS  0b1100aaaa replace a with address bits
"""
SKEY = 0xE0
NVM_PROGRAM_ENABLE = 0x1289AB45CDD888FF

NVMCMD = 0x33
NVMCSR = 0x32
NVM_NOP = 0x00
NVM_CHIP_ERASE = 0x10
NVM_SECTION_ERASE = 0x14
NVM_WORD_WRITE = 0x1D

HVReset = 9

Tiny4_5 = 10
Tiny9 = 1
Tiny10 = 1
Tiny20 = 2
Tiny40 = 4
Tiny102 = 1
Tiny104 = 1

TimeOut = 1
HexError = 2
TooLarge = 3


# represents the current pointer register value
adrs = 0x0000

# used for storing a program file
data = ['' for i in range(16)] # program data
progSize = 0; # program size in bytes

# used for various purposes
startTime = 0
timeout = 0
b = b1 = b2 = b3 = 0
idChecked = False
correct  = False
chipType = 1 #  type of chip connected 1 = Tiny10, 2 = Tiny20
HVP = 0
HVON = 0

counti = 0


def hvserial():
    if HVP:
        print("***High Voltage Programming Enabled***")
    else:
        print("High Voltage Programming Disabled")

    print("Pin 9 ")
    if HVON:
        print("HIGH")
    else:
        print("LOW")
    print(" supplies 12v")


def hvReset(highLow):
    if HVP:
        pass
        #if HVON: 
            # if high enables 12v
            #highLow = 1 - highLow  # invert the typical reset 
        #digitalWrite(HVReset, highLow);
    else:
        wiringpi.digitalWrite(SS_PIN, highLow);

def quickReset():
    wiringpi.digitalWrite(SS_PIN,HIGH);
    time.sleep(0.001)
    wiringpi.digitalWrite(SS_PIN,LOW);
    time.sleep(0.001)
    wiringpi.digitalWrite(SS_PIN,HIGH);

def start_tpi():
    # enter TPI programming mode
    global spi
    spi = spidev.SpiDev()
    spi.open(0, 0)
    spi.max_speed_hz = 122000
    hvReset(LOW)
    time.sleep(0.1)  # t_RST min = 400 ns @ Vcc = 5 V

    spi.xfer([0xff])  # activate TPI by emitting
    spi.xfer([0xff])  # 16 or more pulses on TPICLK
    spi.xfer([0xff]) # while holding TPIDATA to "1"

    writeCSS(0x02, 0x04); # TPIPCR, guard time = 8bits (default=128)
    send_skey(NVM_PROGRAM_ENABLE) # enable NVM interface

    #wait for NVM to be enabled
    while (readCSS(0x00) & 0x02) < 1:
      pass
    print("NVM enabled")

#  writes to CSS
def  writeCSS(address, value):
    tpi_send_byte(0xC0 | address)
    tpi_send_byte(value)

# reads from CSS
def readCSS(address):
  tpi_send_byte(0x80 | address)
  return tpi_receive_byte()

"""
send a byte in one TPI frame (12 bits)
(1 start + 8 data + 1 parity + 2 stop)
using 2 SPI data bytes (2 x 8 = 16 clocks)
(with 4 extra idle bits)
"""
def tpi_send_byte(data):
    global spi
    # compute partiy bit
    par = data
    par ^= (par >> 4)  # b[7:4] (+) b[3:0]
    par ^= (par >> 2)  # b[3:2] (+) b[1:0]
    par ^= (par >> 1)  # b[1] (+) b[0]

    #REMEMBER: this is in LSBfirst mode and idle is high
    #(2 idle) + (1 start bit) + (data[4:0])
    spi.xfer([rev(0x03 | ((data << 3)&255))])
    #(data[7:5]) + (1 parity) + (2 stop bits) + (2 idle)
    spi.xfer([rev(0xf0 | ((par << 3)&255) | ((data >> 5)&255))])

"""
receive TPI 12-bit format byte data
via SPI 2 bytes (16 clocks) or 3 bytes (24 clocks)
"""
def tpi_receive_byte():
    # keep transmitting high(idle) while waiting for a start bit
    b1 = rev(spi.xfer([0xff])[0])
    while 0xff == b1:
        b1 = rev(spi.xfer([0xff])[0])

    # get (partial) data bits
    b2 = rev(spi.xfer([0xff])[0])

    # if the first byte(b1) contains less than 4 data bits
    # we need to get a third byte to get the parity and stop bits
    if 0x0f == (0x0f & b1):
        b3 = rev(spi.xfer([0xff])[0])

    # now shift the bits into the right positions
    # b1 should hold only idle and start bits = 0b01111111
    while 0x7f != b1: # data not aligned
        b2 = (b2 << 1) & 255 # shift left data bits
        if 0x80 & b1: # carry from 1st byte
            b2 |= 1  # set bit
        b1 = (b1 << 1) & 255
        b1 |= 0x01 # fill with idle bit (1)

    # now the data byte is stored in b2
    return b2

# send the 64 bit NVM key
def send_skey(nvm_key):
    tpi_send_byte(SKEY)
    while nvm_key:
        tpi_send_byte(nvm_key & 0xFF)
        nvm_key >>= 8

# reverse byte data for LSBfirst SPI mode
# Rpi doesn't suppor LSBfirst mode
def rev(b):
    b = (b & 0xF0) >> 4 | (b & 0x0F) << 4
    b = (b & 0xCC) >> 2 | (b & 0x33) << 2;
    b = (b & 0xAA) >> 1 | (b & 0x55) << 1;
    return b


def checkID():
    #check the device ID
    id1 = id2 = id3 = 0
    setPointer(0x3FC0)
    tpi_send_byte(SLDp)
    id1 = tpi_receive_byte()
    tpi_send_byte(SLDp)
    id2 = tpi_receive_byte()
    tpi_send_byte(SLDp)
    id3 = tpi_receive_byte()
    if id1==0x1E and id2==0x8F and id3==0x0A:
        print("ATtiny4")
        chipType = Tiny4_5
    elif id1==0x1E and id2==0x8F and id3==0x09:
        print("ATtiny5")
        chipType = Tiny4_5
    elif id1==0x1E and id2==0x90 and id3==0x08:
        print("ATtiny9")
        chipType = Tiny9
    elif id1==0x1E and id2==0x90 and id3==0x03:
        print("ATtiny10")
        chipType = Tiny10
    elif id1==0x1E and id2==0x91 and id3==0x0f:
        print("ATtiny20")
        chipType = Tiny20
    elif id1==0x1E and id2==0x92 and id3==0x0e:
        print("ATtiny40")
        chipType = Tiny40
    elif id1==0x1E and id2==0x90 and id3==0x0c:
        print("ATtiny102")
        chipType = Tiny102
    elif id1==0x1E and id2==0x90 and id3==0x0b:
        print("ATtiny104")
        chipType = Tiny104
    else:
        print("Unknown chip")

    print(" connected")

def finish():
    writeCSS(0x00, 0x00)
    spi.xfer([0xff])
    spi.xfer([0xff])
    hvReset(HIGH)
    time.sleep(0.001)  # t_RST min = 400 ns @ Vcc = 5 V
    spi.close()

def setPointer(address):
    adrs = address
    tpi_send_byte(SSTPRL)
    tpi_send_byte(address & 0xff)
    tpi_send_byte(SSTPRH)
    tpi_send_byte((address>>8) & 0xff)

def quickReset():
    wiringpi.digitalWrite(SS_PIN,HIGH)
    time.sleep(0.001)
    wiringpi.digitalWrite(SS_PIN,LOW)
    time.sleep(0.01);
    wiringpi.digitalWrite(SS_PIN,HIGH)
    print("Reset Done.")

# print the register, SRAM, config and signature memory
def dumpMemory():
    global adrs
    length = 0;
    i = 0

    # initialize memory pointer register
    setPointer(0x0000)

    print("Current memory state:")

    if chipType != Tiny4_5:
        length = 0x400 * chipType # the memory length for a 10/20/40 is 1024/2048/4096
    else:
        length = 0x200 # tiny 4/5 has 512 bytes

    length += 0x4000

    while adrs < length:
        # read the byte at the current pointer address
        # and increment address
        tpi_send_byte(SLDp)
        b = tpi_receive_byte() # get data byte

        # read all the memory, but only print
        # the register, SRAM, config and signature memory
        if ((0x0000 <= adrs and adrs <= 0x005F) # register/SRAM
                |(0x3F00 <= adrs and adrs <= 0x3F01) # NVM lock bits
                |(0x3F40 <= adrs and adrs <= 0x3F41) # config
                |(0x3F80 <= adrs and adrs <= 0x3F81) # calibration
                |(0x3FC0 <= adrs and adrs <= 0x3FC3) # ID
                |(0x4000 <= adrs and adrs <= length-1)): # program
            # print +number along the top
            if ((0x00 == adrs)|(0x3f00 == adrs) # NVM lock bits
                    |(0x3F40 == adrs) # config
                    |(0x3F80 == adrs) # calibration
                    |(0x3FC0 == adrs) # ID
                    |(0x4000 == adrs)):

                print("")
                if adrs == 0x0000: 
                    print("registers, SRAM", end=' ')
                if adrs == 0x3F00:
                    print("NVM lock", end=' ')
                if adrs == 0x3F40:
                    print("configuration", end=' ')
                if adrs == 0x3F80:
                    print("calibration", end=' ')
                if adrs == 0x3FC0:
                    print("device ID", end=' ')
                if adrs == 0x4000:
                    print("program", end=' ')
                print("")

                for i in range(5):
                    print(" ", end=' ')

                for i in range(16):
                    print(" +", end=' ')
                    print(hex(i), end=' ')

            # print number on the left
            if 0 == (0x000f & adrs):
                print("")
                outHex(adrs, 4);
                print(": ", end=' ') # delimiter

            outHex(b, 2);
            print(" ", end=' ')
        adrs+=1 # increment memory address
        if adrs == 0x0060:
            # skip reserved memory
            setPointer(0x3F00);
    print(" ")

def outHex(n, l): # call with the number to be printed, and # of nibbles expected.
    # quick and dirty to add zeros to the hex value
    count = l - 1
    while count > 0:
        if ((n >> (count*4)) & 0x0f) == 0: # if MSB is 0
            print("0", end=' ')  # prepend a 0
        else:
            break  # exit the for loop
        count-=1
    print(hex(n), end=' ')

def eraseChip():
    # initialize memory pointer register
    setPointer(0x4001)  # need the +1 for chip erase

    # erase the chip
    writeIO(NVMCMD, NVM_CHIP_ERASE)
    tpi_send_byte(SSTp)
    tpi_send_byte(0xAA)
    tpi_send_byte(SSTp)
    tpi_send_byte(0xAA)
    tpi_send_byte(SSTp)
    tpi_send_byte(0xAA)
    tpi_send_byte(SSTp)
    tpi_send_byte(0xAA)
    while (readIO(NVMCSR) & (1<<7)) != 0x00:
        pass
    print("chip erased")

# writes using SOUT
def writeIO(address, value):
    # SOUT 0b1aa1aaaa replace a with 6 address bits
    tpi_send_byte(0x90 | (address & 0x0F) | ((address & 0x30) << 1))
    tpi_send_byte(value)

# reads using SIN
def readIO(address):
    # SIN 0b0aa1aaaa replace a with 6 address bits
    tpi_send_byte(0x10 | (address & 0x0F) | ((address & 0x30) << 1))
    return tpi_receive_byte()

# receive and translate the contents of a hex file, Program and verify on the fly
def  writeProgram():
    datlength  = ['0','0']
    addr = ['0','0','0','0']
    something = ['0','0']
    chksm = ['0', '0']
    currentByte = 0
    progSize = 0
    linelength = 0
    fileEnd = False
    tadrs = adrs = 0x4000
    correct = True
    pgmStartTime = millis()
    eraseChip()  # erase chip
    if chipType != Tiny4_5:
        words = chipType
    else:
        words = 1

    #read in the data and
    while not fileEnd:

        if Sread() != ':': # maybe it was a newline??
            if Sread() != ':':
                ERROR_data(HexError)
                return False

        # read data length
        datlength[0] = Sread()
        datlength[1] = Sread()

        # convert character to one byte
        linelength = int(''.join(datlength), 16)

        # read address. if "0000" currentByte = 0
        addr[0] = Sread()
        addr[1] = Sread()
        addr[2] = Sread()
        addr[3] = Sread()

        if linelength != 0x00 and addr[0]=='0' and addr[1]=='0' and addr[2]=='0' and addr[3]=='0':
            currentByte = 0

        # read type thingy. "01" means end of file
        something[0] = Sread()
        something[1] = Sread()
        if something[1] == '1':
            fileEnd = True

        if something[1] == '2':
            for i in range(linelength+1):
                Sread()
                Sread()
        else:
            # read in the data
            for i in range(linelength):
                b1=Sread()
                b2=Sread()
                data[currentByte] = int(b1+b2, 16)
                currentByte+=1
                progSize+=1

                if chipType != Tiny4_5:
                    tmp = chipType * 1024
                else:
                    tmp = 512
                if progSize > tmp:
                    ERROR_data(TooLarge)
                    return False

                if fileEnd: # has the end of the file been reached?
                    while currentByte < (2 * words): # append zeros to align the word count to program
                        data[currentByte] = 0
                        currentByte+=1

                if currentByte == (2 * words): # is the word/Dword/Qword here?
                    currentByte = 0 #yes, reset counter
                    setPointer(tadrs) #point to the address to program
                    writeIO(NVMCMD, NVM_WORD_WRITE)

                    i = 0
                    while i<(2 * words): # loop for each word size depending on micro
                        # now write a word to program memory
                        tpi_send_byte(SSTp)
                        tpi_send_byte(data[i]) #LSB first
                        tpi_send_byte(SSTp)
                        tpi_send_byte(data[i+1]) #then MSB
                        spi.xfer([0xff]) #send idle between words
                        spi.xfer([0xff]) #send idle between words
                        i+=2

                    #wait for write to finish
                    while (readIO(NVMCSR) & (1<<7)) != 0x00:
                        pass 

                    writeIO(NVMCMD, NVM_NOP);
                    spi.xfer([0xff])
                    spi.xfer([0xff])


                    # verify written words
                    setPointer(tadrs)
                    c = 0
                    while c < (2 * words):
                        tpi_send_byte(SLDp)
                        b = tpi_receive_byte() # get data byte

                        if b != data[c]:
                            correct = False
                            print("program error:")
                            print("byte ", end=' ')
                            outHex(adrs, 4)
                            print(" expected ", end=' ')
                            outHex(data[c],2)
                            print(" read ", end=' ')
                            outHex(b,2);
                            print("")

                            if not correct:
                                return False
                        c+=1

                    tadrs += 2 * words

            chksm[0] = Sread();
            chksm[1] = Sread();

    # the program was successfully written
    print("Successfully wrote program: ", end=' ')
    print(progSize, end=' ')
    print(" of ", end=' ')
    if chipType != Tiny4_5:
        print(1024 * chipType, end=' ')
    else:
        print(512, end=' ')
    print(" bytes\n in ", end=' ')
    print((millis()-pgmStartTime)/1000.0, end=' ')
    print(" Seconds", end=' ')

    return True

def ERROR_data(i):
    print("couldn't receive data:")
    if i ==  TimeOut:
        print("timed out")
    elif i == HexError:
        print("hex file format error")
    elif i == TooLarge:
        print("program is too large")

def Sread():
    return sys.stdin.read(1)

def setConfig(val):
    # get current config byte
    setPointer(0x3F40);
    tpi_send_byte(SLD);
    b = tpi_receive_byte();

    print("input one of these letters")
    print("c = system clock output")
    print("w = watchdog timer on")
    print("r = disable reset")
    print("x = cancel. don't change anything")

    comnd = input()
    setPointer(0x3F40)

    if val:
        tmp = NVM_WORD_WRITE
    else:
        tmp = NVM_SECTION_ERASE

    writeIO(NVMCMD,tmp)

    if comnd == 'c':
        tpi_send_byte(SSTp)
        if val:
            tpi_send_byte(b & 0b11111011)
        else:
            tpi_send_byte(b | 0x04)
        tpi_send_byte(SSTp)
        tpi_send_byte(0xFF)
    elif comnd == 'w':
        tpi_send_byte(SSTp)
        if val:
            tpi_send_byte(b & 0b11111101)
        else:
            tpi_send_byte(b | 0x02)
        tpi_send_byte(SSTp)
        tpi_send_byte(0xFF)
    elif comnd == 'r':
        tpi_send_byte(SSTp);
        if val:
            tpi_send_byte(b & 0b11111110)
        else:
            tpi_send_byte(b | 0x01)
        tpi_send_byte(SSTp)
        tpi_send_byte(0xFF)
    elif comnd == 'x':
        pass
    else:
        print("received unknown command. Cancelling")
    
    while (readIO(NVMCSR) & (1<<7)) != 0x00:
        pass
    writeIO(NVMCMD, NVM_NOP)
    spi.xfer([0xff])
    spi.xfer([0xff])
    
    if comnd != 'x':
    
        print("\n\nSuccessfully ", end=' ')
        if val:
            print("Set ", end=' ')
        else:
            print("Cleared ", end=' ')
      
        print("\"", end=' ')
        if comnd == 'w':
            print("Watchdog", end=' ')
        elif comnd == 'c':
            print("Clock Output")
        elif comnd == 'r':
            print("Reset")
      
        print("\" Flag\n")

if __name__ == '__main__':
    start_tpi()
    while True:
        if not idChecked:
            print("checking ID")
            checkID()
            idChecked = True
            finish()

        # when ready, send ready signal '.' and wait
        print("\n>")
        start_tpi()

        # the first byte is a command
        #** 'P' = program the ATtiny using the read program
        #** 'D' = dump memory to serial monitor
        #** 'E' = erase chip. erases current program memory.(done automatically by 'P')
        #** 'S' = set fuse
        #** 'C' = clear fuse

        cmd = input("Enter:")
        if cmd == 'r' or cmd == 'R':
            quickReset()

        elif cmd == 'D':
            dumpMemory()

        elif cmd == 'H':
            HVP = 1 - HVP
            hvserial()

        elif cmd == 'T':
            HVON = 1 - HVON
            hvserial()

        elif cmd ==  'P':
            if not writeProgram():
                print("Writing program faile!")

        elif cmd == 'E':
            eraseChip()

        elif cmd == 'S':
            setConfig(True)

        elif cmd == 'C':
            setConfig(False)

        elif cmd == 'Q' or cmd == 'q':
            print("Quitting..")
            finish()
            break

        else:
            print("Received unknown command")

        finish()
