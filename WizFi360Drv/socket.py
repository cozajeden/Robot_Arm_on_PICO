import uasyncio as asyncio
from WizFi360Drv.WizFi360 import WLAN
from WizFi360Drv.commands import *
import gc
        
class Socket(WLAN):
        
    def listen(self, port):
        "Start listening on a given port."
        listenStr = START_SER + str(port).encode() + EOL
        self.write(MUL_CONN_EN)
        for i in range(3):
            self.readline()
        self.write(listenStr)
        for i in range(3):
            self.readline()
        print('[SOCKET] Server started at port {0}'.format(port))
        return (asyncio.StreamWriter(self.uart, {}), asyncio.StreamReader(self.uart))
        
    def bind(self, addr, port):
        "Bind to a given socket."
        connectStr = SOC_CLIENT+'"{0}",{1}'.format(addr, port).encode()+EOL
        self.write(connectStr)
        self.read(len(connectStr))
        if self.readline() != CONNECTED:
            self.clear_buffer()
            return 'ERROR', 0
        self.readline()
        print('[SOCKET] Connected to: {0}:{1}'.format(addr, port))
        return (asyncio.StreamWriter(self.uart, {}), asyncio.StreamReader(self.uart))

gc.collect()