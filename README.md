# Raspberrypi-TPI-programmer
Programmer for AVR ATTiny microcontrollers :ATtiny4/5/9/10/20/40/102/104

This work is inspired from Arduino TPI programmer : https://github.com/james-tate/Arduino-TPI-Programmer

Arduino code is converted to Python 3.

## Prerequisite Libraries
* wiringpi 
* spidev

## Hardware Connection       
![image](https://user-images.githubusercontent.com/10621421/166121026-a541ad24-5d97-4a28-ade3-49bc26ccb682.png)

## Usage

D = dump memory. Displays all current memory on the chip

E = erase chip. Erases all program memory automatically done at time of programming

P = write program. After sending this, paste the program from the hex file into the serial monitor.

S = set fuse. follow the instructions to set one of the three fuses.

C = clear fuse. follow the instructions to clear one of the three fuses.

H = Toggle High Voltage Programming

T = Toggle +12v enabled by High, or Low

R/r = Quick reset

Q/q = Quit Program
