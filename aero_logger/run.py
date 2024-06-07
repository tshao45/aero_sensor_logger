#!/usr/bin/env python
import asyncio
import serial
import serial_asyncio
from aiohttp import web
# from utils import log_sensor_data, process_buffer
from mcap_protobuf.writer import Writer
from datetime import datetime
import sys
import struct
import threading
import queue
import os
import time
import signal
import atexit


import time
import struct
from aero_sensor_protos_np_proto_py.aero_sensor import aero_sensor_pb2

start_new_log = False
stop_current_log = False
def log_sensor_data(mcap_logger, data, port_name):
    msg = aero_sensor_pb2.aero_data()
    msg.readings_pa.extend(data)
    sensor_name = port_name.split("/")[-1]
    
    mcap_logger.write_message(
        topic=msg.DESCRIPTOR.name + "_" + sensor_name + "_data",
        message=msg,
        log_time=int(time.time_ns()),
        publish_time=int(time.time_ns()),
    )

async def append_sensor_data(queue, data, port_name):
    await queue.put((data, port_name))

def process_buffer(buffer):
    """Extracts eight 32-bit floats from the buffer."""
    if len(buffer) < 32:
        raise ValueError("Buffer does not contain enough data for eight 32-bit floats.")
    # Unpack 8 32-bit floats (4 bytes each) in little-endian order
    floats = struct.unpack("<8f", buffer[:32])
    return floats

def open_new_writer():
    path_to_mcap = "."
    if os.path.exists("/etc/nixos"):
        path_to_mcap = "/home/nixos/aero_sensor_recordings"
    now = datetime.now()
    date_time_filename = now.strftime("%m_%d_%Y_%H_%M_%S" + ".mcap")
    
    date_time_mcap_path = os.path.join(path_to_mcap, date_time_filename)
    writing_file = open(date_time_mcap_path, "wb")
    return Writer(writing_file), writing_file

def cleanup():
    global mcap_writer, writing_file
    if mcap_writer:
        print("Finalizing MCAP writer...")
        mcap_writer.finish()
    if writing_file:
        writing_file.close()

def handle_signal(signal, frame):
    print(f"Received signal {signal}, running cleanup...")
    cleanup()
    sys.exit(0)

class Listener(asyncio.Protocol):
    def connection_made(self, transport):
        self.transport = transport
        self.logging_enabled = True
        self.transport.write(b"@")
        print(f"Successfully wrote '@'")
        self.transport.write(b"D")
        print(f"Successfully wrote 'D'")

        print("Connection made")
        
    def data_received(self, data):
        # print(data)
        self.buffer += data
        if b"#" in self.buffer:
            parts = self.buffer.split(b"#", 1)
            before_hash = parts[0]
            after_hash = parts[1]

            if len(after_hash) >= 46:
                floats = process_buffer(after_hash[:32])
                if self.logging_enabled:
                    asyncio.get_event_loop().create_task(append_sensor_data(self.queue, floats, self.port_name))
                    
                    # log_sensor_data(self.queue, floats, self.port_name)
                    # print(floats)
                self.buffer = after_hash[46:]
            else:
                self.buffer = b"#" + after_hash
    def connection_lost(self, exc):
        print("Connection lost")

    def setup_listener(self, queue, port_name):
        self.buffer = b""
        self.queue = queue
        self.port_name = port_name

    def enable_queue(self):
        self.logging_enabled = True

    def disable_queue(self):
        self.logging_enabled = False

async def handle_start(request):
    global start_new_log
    start_new_log = True
    return web.Response(text="Queue appending started")

async def handle_stop(request):
    global stop_current_log
    stop_current_log = True
    # listener.disable_queue()
    # listener2.disable_queue()
    return web.Response(text="Queue appending stopped")

async def handle_index(request):
    html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Queue Control</title>
    <style>
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
    </style>
</head>
<body>
    <h1>Queue Control</h1>
    <button id="startButton" onclick="startQueue()">Start</button>
    <button id="stopButton" onclick="stopQueue()" disabled>Stop</button>
    <script>
        async function startQueue() {
            await fetch('/start');
            document.getElementById('startButton').disabled = true;
            document.getElementById('stopButton').disabled = false;
        }

        async function stopQueue() {
            await fetch('/stop');
            document.getElementById('startButton').disabled = false;
            document.getElementById('stopButton').disabled = true;
        }

        // Ensure the "Start" button is enabled and the "Stop" button is disabled on page load
        document.addEventListener('DOMContentLoaded', (event) => {
            document.getElementById('startButton').disabled = true;
            document.getElementById('stopButton').disabled = false;
        });
    </script>
</body>
</html>

    """
    return web.Response(text=html_content, content_type='text/html')

async def init_http_server():
    app = web.Application()
    app.add_routes([
        web.get('/', handle_index),
        web.get('/start', handle_start),
        web.get('/stop', handle_stop),
    ])
    return app

async def worker(queue):
    global start_new_log, stop_current_log
    mcap_logger, writing_file = open_new_writer()
    not_logging = False
    while True:
        message = await queue.get()  # Wait until a message is available
        if start_new_log:
            mcap_logger, writing_file = open_new_writer()
            start_new_log = False
            not_logging = False
        if stop_current_log:
            mcap_logger.finish()
            writing_file.close()
            not_logging = True
            stop_current_log = False
        if not not_logging:
            log_sensor_data(mcap_logger, message[0], message[1])
        queue.task_done()  # Mark the task as done

async def main():
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    atexit.register(cleanup)

    global listener, listener2
    loop = asyncio.get_running_loop()
    
    
    # Set up serial connections
    ports = ['/dev/ttyACM0', '/dev/ttyACM1']
    coro1 = serial_asyncio.create_serial_connection(loop, Listener, ports[0], baudrate=500000)
    coro2 = serial_asyncio.create_serial_connection(loop, Listener, ports[1], baudrate=500000)
    transport1, listener = await coro1
    transport2, listener2 = await coro2
    
    # Set shared queue
    queue = asyncio.Queue()
    
    loop.create_task(worker(queue))
    listener.setup_listener(queue, ports[0])
    listener2.setup_listener(queue, ports[1])
    
    # Set up and run HTTP server
    app = await init_http_server()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 4111)
    await site.start()
    
    print("HTTP server running on http://localhost:8080")
    
    # Keep the event loop running
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass

loop = asyncio.get_event_loop()
try:
    loop.run_until_complete(main())
finally:
    loop.close()