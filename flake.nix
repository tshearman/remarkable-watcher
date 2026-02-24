{
  description = "reMarkable file watcher — converts .rm files to PDF on change";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in {
        devShells.default = pkgs.mkShell {
          packages = [ pkgs.python3 pkgs.inkscape ];

          shellHook = ''
            export FONTCONFIG_FILE=${pkgs.fontconfig.out}/etc/fonts/fonts.conf

            # Create and activate a virtualenv so pip installs work normally.
            if [ ! -d .venv ]; then
              python3 -m venv .venv
            fi
            source .venv/bin/activate
            pip install -q -e ".[dev]"

            # rm2pdf (pre-v6 files) is a Go binary — install it separately:
            #   nix profile install nixpkgs#rm2pdf          (if packaged)
            #   go install github.com/rorycl/rm2pdf@latest  (via Go toolchain)
          '';
        };
      }
    );
}
