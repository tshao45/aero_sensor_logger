{
  description = "aero sensor logger system (TODO make part of data_acq)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-23.11";
    utils.url = "github:numtide/flake-utils";
    mcap-protobuf.url = "github:RCMast3r/mcap-protobuf-support-flake";
    flake-utils.url = "github:numtide/flake-utils";
    mcap.url = "github:RCMast3r/py_mcap_nix";
    nix-proto = { url = "github:notalltim/nix-proto"; };
  };

  outputs = { self, nixpkgs, utils, mcap-protobuf, mcap, nix-proto, flake-utils, ... }@inputs:
    flake-utils.lib.eachSystem [ "x86_64-linux" "aarch64-darwin" "x86_64-darwin" "aarch64-linux" ] (system:
    let
      makePackageSet = pkgs: {
        aero_sensor_logger_pkg = pkgs.aero_sensor_logger_pkg;
      };

      aero_sensor_logger_pkg_overlay = final: prev: {
        aero_sensor_logger_pkg = final.callPackage ./default.nix { };
      };

      nix_protos_overlays = nix-proto.generateOverlays' {
        aero_sensor_protos_np =
          nix-proto.mkProtoDerivation {
            name = "aero_sensor_protos_np";
            src = nix-proto.lib.srcFromNamespace {
              root = ./proto;
              namespace = "aero_sensor";
            };
            version = "1.0.0";
          };
      };

      my_overlays = [
        aero_sensor_logger_pkg_overlay
        mcap-protobuf.overlays.default
        mcap.overlays.default
      ] ++ nix-proto.lib.overlayToList nix_protos_overlays;

      pkgs = import nixpkgs {
        overlays = my_overlays;
        inherit system;
        config = {
          allowUnsupportedSystem = true;
        };
      };

      shared_shell = pkgs.mkShell rec {
        name = "nix-devshell";
        packages = with pkgs; [
          aero_sensor_logger_pkg
        ];
        shellHook =
          let icon = "f121";
          in ''
            echo -e "PYTHONPATH=$PYTHONPATH" > .env
            export PS1="$(echo -e '\u${icon}') {\[$(tput sgr0)\]\[\033[38;5;228m\]\w\[$(tput sgr0)\]\[\033[38;5;15m\]} (${name}) \\$ \[$(tput sgr0)\]"
          '';
      };
    in
    {
      overlays = my_overlays;
      devShells = {
        default = shared_shell;
      };

      packages = rec {
        default = pkgs.aero_sensor_logger_pkg;
        aero_sensor_protos_np = pkgs.aero_sensor_protos_np;
      };

      nixosModules = {
        aero-sensor-logger = { config, lib, pkgs, ... }: {
          options = {
            aero-sensor-logger.enable = lib.mkEnableOption "Enable the aero sensor logger service.";
          };

          config = lib.mkIf config.aero-sensor-logger.enable {
            systemd.services.aero-sensor-logger = {
              description = "Aero Sensor Logger Service";
              wantedBy = [ "multi-user.target" ];
              after = [ "network.target" ];

              serviceConfig = {
                ExecStart = "${pkgs.aero_sensor_logger_pkg}/bin/run.py /dev/ttyACM0 /dev/ttyACM1";
                Restart = "always";
                RestartSec = "5s";
                KillSignal = "SIGINT";
                Environment = "PYTHONUNBUFFERED=1";
              };

              install.wantedBy = [ "multi-user.target" ];
            };
          };
        };
      };
    });
}
