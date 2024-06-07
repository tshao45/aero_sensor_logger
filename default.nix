{ lib, python311Packages, mcap_support_pkg, py_mcap_pkg, aero_sensor_protos_np_proto_py}:

python311Packages.buildPythonApplication {
  pname = "aero_sensor_mcap_logger";
  version = "0.0.1";
  propagatedBuildInputs = with python311Packages; [
    lz4
    zstandard
    protobuf
    mcap_support_pkg
    py_mcap_pkg
    pyserial
    pyserial-asyncio
    aero_sensor_protos_np_proto_py
    aiohttp
  ];
  src = ./aero_logger;
}