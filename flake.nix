{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };
      in with pkgs; {
        devShell = mkShell {
          buildInputs = [
            (pkgs.python312.withPackages (ps: [
                ps.pip
                ps.black
                ps.flake8
                ps.isort
            ]))
            just
          ];
        };
      }
    );
}
