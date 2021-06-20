from array import array
from machine import Pin, PWM
from queue import Queue
import uasyncio as asyncio
import math
from time import sleep


async def schedule(callback, time, *args, **kwargs):
    await asyncio.sleep_ms(time)
    callback(*args, **kwargs)
    
class Kinematics:
    def __init__(self, a1, a2, a3, a4):
        self.lenghts = (a1, a2, a3, a4)
        self.motors = []
        self.storedPoints = []
        self.storedSpeeds = []
        self.programRunning = False
        self.currentAngles = [0, math.pi/2, 0, math.pi/2] 
        self.currentPos = self.forward(*self.currentAngles)
        self.speed = 50
        self.speedLimits = (1, 100)
        self.q23limits = (math.pi*(0.5 - 35/180), math.pi*(0.5 + 55/180))
        self.create_motor(1200, 8500, -math.pi*0.25, math.pi*0.25, 6, 0)
        self.create_motor(6500, 2800, math.pi*(35/180), math.pi*(145/180), 7, math.pi/2)
        self.create_motor(5900, 8400, -math.pi*(65/180), math.pi*(10/180), 8, 0)
        self.create_motor(1200, 5500, 0., math.pi, 9, math.pi/2)
        print('forward0', self.forward(*self.currentAngles))
        self.to_point(*self.currentPos)
        
    def validate_angles(self, q1, q2, q3, q4):
        if not (self.motors[0]['minAngle'] <= q1 <= self.motors[0]['maxAngle']):
            return False
        if not (self.motors[1]['minAngle'] <= q2 <= self.motors[1]['maxAngle']):
            return False
        if not (self.motors[2]['minAngle'] <= q3 <= self.motors[2]['maxAngle']):
            return False
        if not (self.motors[3]['minAngle'] <= q4 <= self.motors[3]['maxAngle']):
            return False
        if not(self.q23limits[0] <= q2+q3 <= self.q23limits[1]):
            return False
        return True
    
    def forward(self, q1, q2, q3, q4):
        sinq1 = math.sin(q1)
        cosq1 = math.cos(q1)
        d1 = self.lenghts[1]*math.cos(q2)
        d2 = self.lenghts[1]*math.sin(q2)
        d3 = d1+self.lenghts[2]*math.cos(q3)
        d4 = d2-self.lenghts[2]*math.sin(q3)
        d5 = d3+self.lenghts[3]
        
        return [d5*cosq1, d5*sinq1, self.lenghts[0]+d4, 100*q4/math.pi]
    
    def inverse(self, x, y, z, g):
        q1 = math.atan2(y, x)
        x -= self.lenghts[3]*math.cos(q1)
        y -= self.lenghts[3]*math.sin(q1)
        r1 = math.sqrt(x**2 + y**2)
        r2 = z - self.lenghts[0]
        fi2 = math.atan2(r2, r1)
        r3 = math.sqrt(r1**2 + r2**2)
        fi1 = math.acos((self.lenghts[2]**2 - self.lenghts[1]**2 - r3**2)/(-2*self.lenghts[1]*r3))
        q2 = fi2 + fi1
        fi3 = math.acos((r3**2 - self.lenghts[1]**2 - self.lenghts[2]**2)/(-2*self.lenghts[1]*self.lenghts[2]))
        q3 = fi3 + q2 - math.pi
        
        return [q1, q2, q3, g*math.pi/100]
    
    async def store_point(self):
        if self.programRunning:
            return 'RUNNING\n'
        self.storedPoints.append(self.currentPos)
        self.storedSpeeds.append(self.speed)
        await asyncio.sleep(0)
        return 'ACK\n'
    
    async def run_program(self):
        self.programRunning = True
        progLen = len(self.storedPoints)
        index = 0
        while True:
            if self.programRunning:
                await self.set_speed(self.storedSpeeds[index], auto=True)
                await self.to_point(*self.storedPoints[index], auto=True)
                index += 1
                if index == progLen:
                    index = 0
            else:
                break
    
    async def store_program(self):
        if self.programRunning:
            return 'RUNNING\n'
        open('points', 'w').write(str(self.storedPoints))
        open('pspeeds', 'w').write(str(self.storedSpeeds))
        return 'ACK\n'
    
    async def read_program(self):
        if self.programRunning:
            return 'RUNNING\n'
        self.storedPoints = eval(open('points').read())
        self.storedSpeeds = eval(open('pspeeds').read())
        return 'ACK\n'
    
    async def clean_program(self):
        if self.programRunning:
            return 'RUNNING\n'
        self.storedPoints = []
        self.storedSpeeds = []
        return 'ACK\n'
    
    async def stop_program(self):
        self.programRunning = False
        return 'ACK\n'
        
    async def command(self, msg):
        pos = [self.currentPos[0], self.currentPos[1], self.currentPos[2], self.currentPos[3]]
        if msg[0] == 'P':
            return await self.to_point(msg[1], msg[2], msg[3], msg[4])
        elif msg[0] == 'X':
            pos[0] += msg[1]
            return await self.to_point(*pos)
        elif msg[0] == 'Y':
            pos[1] += msg[1]
            return await self.to_point(*pos)
        elif msg[0] == 'Z':
            pos[2] += msg[1]
            return await self.to_point(*pos)
        elif msg[0] == 'G':
            pos[3] += msg[1]
            return await self.to_point(*pos)
        elif msg[0] == 'F':
            return await self.set_speed(msg[1])
        elif msg[0] == 'C':
            if msg[1] == 'P':
                return await self.store_point()
            elif msg[1] == 'R':
                asyncio.create_task(self.run_program())
                return 'ACK\n'
            elif msg[1] == 'W':
                return await self.store_program()
            elif msg[1] == 'G':
                return await self.read_program()
            elif msg[1] == 'S':
                return await self.stop_program()
            elif msg[1] == 'C':
                return await self.clean_program()
            
    async def set_speed(self, speed, auto=False):
        if self.programRunning and not auto:
            return 'RUNNING\n'
        if self.speedLimits[0] <= speed <= self.speedLimits[1]:
            self.speed = speed
            return 'ACK\n'
        else:
            return 'LS\n'
            
    async def to_point(self, x, y, z, g, auto=False):
        if self.programRunning and not auto:
            return 'RUNNING\n'
        pos = [x, y, z, g]
        cx, cy, cz, cg = self.currentPos
        cpos = [cx, cy, cz, cg]
        way = []
        diff = (x - cx, y - cy, z - cz)
        longest = max(abs(diff[0]), abs(diff[1]), abs(diff[2]))
        steps = int(100*longest/self.speed)
        gsteps = int(300*abs(g - cg)/self.speed)
        if gsteps > steps:
            steps = gsteps
        if steps == 0:
            steps = 1
        diff = (diff[0]/steps, diff[1]/steps, diff[2]/steps, (g - cg)/steps)
        for i in range(steps):
            cpos[0] += diff[0]
            cpos[1] += diff[1]
            cpos[2] += diff[2]
            cpos[3] += diff[3]
            q = self.inverse(*cpos)
            validate = self.validate_angles(q[0], q[1], q[2], q[3])
            if validate:
                q1 = self.pwm_from_angle_by_motor(0, q[0])
                q2 = self.pwm_from_angle_by_motor(1, q[1])
                q3 = self.pwm_from_angle_by_motor(2, q[2])
                q4 = self.pwm_from_angle_by_motor(3, q[3])
                self.motors[0]['duty_u16'](q1)
                self.motors[1]['duty_u16'](q2)
                self.motors[2]['duty_u16'](q3)
                self.motors[3]['duty_u16'](q4)
                self.currentAngle = q
                self.currentPos = cpos
                await asyncio.sleep_ms(1)
            else:
                return 'LS\n'
        return 'ACK\n'
        
    def pwm_from_angle_by_motor(self, motor, angle):
        return self.pwm_from_angle(
            self.motors[motor]['min'],
            self.motors[motor]['max'],
            self.motors[motor]['minAngle'],
            self.motors[motor]['maxAngle'],
            angle
            )
        
    def pwm_from_angle(self, minimum, maximum, minAngle, maxAngle, angle):
        angleRange = maxAngle - minAngle
        pwmRange = maximum - minimum
        anglePos = angle - minAngle
        pwmPos = int(pwmRange*anglePos/angleRange) + minimum
        return pwmPos

    def create_motor(self, min, max, minAngle, maxAngle, pin, startAngle):
        pwm =  PWM(Pin(pin))
        pwm.freq(50)
        center = self.pwm_from_angle(min, max, minAngle, maxAngle, startAngle)
        self.motors.append({
            'min':min,
            'max':max,
            'minAngle':minAngle,
            'maxAngle':maxAngle,
            'current':center,
            'currentAngle':startAngle,
            'pwm':pwm,
            'duty_u16':pwm.duty_u16
            })
        
async def start_kinematics():
    kinematics = Kinematics()
    kinematics.create_motor(900, 10000, 0, 3.14, 1.5, 6)
    while True:
        await asyncio.sleep(0.5)