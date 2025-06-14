{ pkgs }: {
  deps = [
    pkgs.ffmpeg
    pkgs.python311Full
    pkgs.python311Packages.pynacl
    pkgs.python311Packages.discordpy
  ];
}
