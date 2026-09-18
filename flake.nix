{
  description = "CS/INFO 5306 Project 1 — Community Notes first-note outcomes and retention";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/8ce4ef6cb6f871616146b9fe26d2a5ae594e94fe";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in {
      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          name = "cn-retention";
          packages = [
            (pkgs.python3.withPackages (ps: with ps; [
              duckdb
              pyarrow
              pandas
              numpy
              scipy
              statsmodels
              matplotlib
            ]))
            pkgs.duckdb
            pkgs.unzip
            pkgs.curl
          ];
        };
      });
    };
}
