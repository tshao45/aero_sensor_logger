#!/usr/bin/env python

import serial
import sys
import struct
import threading
import queue
import os
import time
import signal
import atexit

from datetime import datetime
from aero_sensor_protos_np_proto_py.aero_sensor import aero_sensor_pb2
from mcap_protobuf.writer import Writer


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

def process_buffer(buffer):
    """Extracts eight 32-bit floats from the buffer."""
    if len(buffer) < 32:
        raise ValueError("Buffer does not contain enough data for eight 32-bit floats.")
    # Unpack 8 32-bit floats (4 bytes each) in little-endian order
    floats = struct.unpack("<8f", buffer[:32])
    return floats

def serial_reader(ports, queues):
    ser_ports = [serial.Serial(port, 500000, timeout=1) for port in ports]
    for ser in ser_ports:
        ser.write(b"@")
        print(f"Successfully wrote '@' to {ser.port}")
        ser.write(b"D")
        print(f"Successfully wrote 'D' to {ser.port}")

    while True:
        for ser, q in zip(ser_ports, queues):
            buffer = b""
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                buffer += data
                if b"#" in buffer:
                    parts = buffer.split(b"#", 1)
                    before_hash = parts[0]
                    after_hash = parts[1]

                    if len(after_hash) >= 46:
                        floats = process_buffer(after_hash[:32])
                        q.put((ser.port, floats))
                        buffer = after_hash[46:]
                    else:
                        buffer = b"#" + after_hash

def write_and_read_serial(ports, mcap_writer, writing_file):
    try:
        queues = [queue.Queue() for _ in ports]

        reader_thread = threading.Thread(target=serial_reader, args=(ports, queues))
        reader_thread.start()
        # Process data from the queues
        while True:
            for q in queues:
                port, data = q.get()
                log_sensor_data(mcap_writer, data, port)
                writing_file.flush()
                # print(f"Data from port {port}: {data}")

    except serial.SerialException as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        cleanup()

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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <serial_port1> <serial_port2> ...")
    else:
        path_to_mcap = "."
        if os.path.exists("/etc/nixos"):
            path_to_mcap = "/home/nixos/aero_sensor_recordings"
        now = datetime.now()
        date_time_filename = now.strftime("%m_%d_%Y_%H_%M_%S" + ".mcap")
        serial_ports = sys.argv[1:]
        date_time_mcap_path = os.path.join(path_to_mcap, date_time_filename)
        writing_file = open(date_time_mcap_path, "wb")
        mcap_writer = Writer(writing_file)

        # Register signal handlers for SIGINT and SIGTERM
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
        atexit.register(cleanup)

        write_and_read_serial(serial_ports, mcap_writer, writing_file)
