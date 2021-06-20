from machine import Pin, PWM
from time import sleep
import uasyncio as asyncio, gc
from queue import Queue
from network import start_listening, Client
import WizFi360Drv.commands as cmd
from kinematics import Kinematics

clients = {}
        
async def handle_message(msg, sendQ, kinematics):
    if len(msg) > 0:
        if msg[2:] == cmd.CONNECTED:
            if msg[0]-48 not in clients.keys():
                clients[msg[0]-48] = Client(msg[0]-48, None, sendQ)
        elif msg[2:] == cmd.CLOSED:
            if msg[0]-48 in clients:
                clients.pop(msg[0]-48)
                print('[CLIENT {0}] DISCONNECTED!'.format(msg[0]-48))
                gc.collect()
        elif msg[:4] == b'+IPD':
            client = msg[5]-48
            msg = str(msg)
            msg = msg[msg.find(':')+1:-3]
            if msg[0] == 'P':
                response = await kinematics.command(('P' , float(msg[1:5]), float(msg[5:9]), float(msg[9:13]), float(msg[13:17])))
                await clients[client].send(response)
            elif msg[0] in ('X', 'Y', 'Z', 'G', 'F'):
                response = await kinematics.command((msg[0] , float(msg[1:5])))
                await clients[client].send(response)
            elif msg[0] == 'C':
                response = await kinematics.command((msg[0] , msg[1]))
                await clients[client].send(response)
        
async def listener(lock, queue, sendQ, kinematics):
    while True:
        msg = cmd.BUSY
        while msg == cmd.BUSY or msg == cmd.EOL or msg == cmd.ACK:
            msg = await queue.get()
        asyncio.create_task(handle_message(msg, sendQ, kinematics))

async def main():
    kinematics = Kinematics(100., 130., 150., 90.)
    lock = asyncio.Lock()
    recvQ = Queue()
    sendQ = Queue()
    asyncio.create_task(start_listening(lock, recvQ, sendQ))
    asyncio.create_task(listener(lock, recvQ, sendQ, kinematics))
    while True:
        await asyncio.sleep(0)

    
asyncio.run(main())