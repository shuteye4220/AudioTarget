# The Pi SD-card image

One 64-bit image runs on the Raspberry Pi Zero 2 W, 3, 4, 5 and 500. It picks
camera settings for the board it finds itself on. The original Zero, Zero W
and Pi 1 aren't supported: they're 32-bit only and too slow for the camera.

## Flashing

1. Download `audiotarget-*.img.xz` from the repository's Releases page.
2. Write it with Raspberry Pi Imager: under Operating System choose "Use
   custom", then pick the file. In Imager's OS customisation settings, set a
   username and password, Wi-Fi if you want it, and turn on SSH if you want
   remote access. The image has no usable default login.
3. Put the card in the Pi and power it up. The first boot takes a minute or two
   longer than later ones.

On Linux you can also write it from a terminal:
`xzcat audiotarget-*.img.xz | sudo dd of=/dev/sdX bs=4M conv=fsync status=progress`,
replacing `/dev/sdX` with your card. Check that name carefully first. Without
Imager's customisation you won't have a login, but the spoken menu works.

## Hearing it the first time

The Zero 2 W and Pi 5 have no headphone jack, so the Pi needs a way to talk:

- **Bluetooth headset or speaker:** put it in pairing mode **before** powering
  the Pi on. With no other audio output, the Pi pairs with the first headset or
  speaker it finds in pairing mode, says "Connected to" and its name, then
  "AudioTarget ready". It keeps looking for about 3 minutes.
- **USB sound card:** plug it in with earphones attached. It's used straight away.

## The spoken menu

| Key (keypad / keyboard) | Belt-case button | Does |
|---|---|---|
| 8 or Up arrow | Up | Previous item |
| 2 or Down arrow | Down | Next item |
| 5, Enter, Space or Right arrow | Select | Choose |
| 0, Backspace, Esc or Left arrow | Hold Select for about a second | Back |
| + / - | | Volume |
| * | | Repeat the last thing said |
| / or Home | | Back to the top menu |

Each item is read with its position, for example "Camera. 7 of 9".

- **Status:** tracking, gun-module connection, camera frame rate, and how often
  the card is being seen
- **Where is the target:** the target's position relative to the camera, for example
  "target 1.2 degrees right, level, 12 metres"
- **Follow the target:** repeats that every 2 seconds until you press any key.
  Handy for lining up the camera
- **Pause / resume tracking**
- **Bluetooth audio:** search for headphones and speakers and connect; forget
  paired devices
- **Gun module:** pair by Bluetooth, connection type (wire, Bluetooth or both),
  whether this Pi also plays the guidance tones
- **Camera:** camera and lens preset, target type, flip the picture
- **Speech:** faster, slower, status announcements on or off
- **System:** speak the network address, restart, shut down. Restart and shut
  down ask you to press Select a second time to confirm.

Settings that change how tracking runs save and then restart the service. You
hear "Restarting" and it's back in a few seconds.

## Pairing the gun module by Bluetooth

1. On the gun module, hold MODE until the second click, then let go. You hear
   three quick beeps. A gun module with no Pi paired yet is already in
   pairing mode for 2 minutes after power-on.
2. On the Pi menu: Gun module, then Pair a gun module by Bluetooth.
3. The Pi restarts, connects, and says "Gun module connected by Bluetooth". The
   gun module plays two rising high notes.

The Pi then remembers that one gun module by its address.

## Where things live

- Settings: `/var/lib/audiotarget/audiotarget.toml` (every option is listed in
  `pi/config.example.toml`)
- Logs: `journalctl --user -M audiotarget@ -u audiotarget -f` (or
  `sudo journalctl -f` to see everything)
- The service runs as the `audiotarget` user, in that user's own systemd
  session, so it can use PipeWire for Bluetooth audio.
- Belt buttons and UART settings: the "AudioTarget" block in
  `/boot/firmware/config.txt`

## Updating or installing on an existing Pi

On Raspberry Pi OS Lite 64-bit (Bookworm or Trixie):

```
git clone https://github.com/shuteye4220/AudioTarget
cd AudioTarget
sudo ./image/install.sh
sudo reboot
```

Running it again later updates the software and keeps your settings.
