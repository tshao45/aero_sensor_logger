import time
import struct
from aero_sensor_protos_np_proto_py.aero_sensor import aero_sensor_pb2

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