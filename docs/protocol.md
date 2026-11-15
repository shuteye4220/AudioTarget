# Pi to gun module protocol

Both the wired UART (115200 baud, 8N1) and the Bluetooth link carry the same
plain-text lines. Bluetooth uses the Nordic UART Service:

- Service `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
- Pi writes to RX `6e400002-...`
- Gun module notifies on TX `6e400003-...`

Each line is printable ASCII, fields separated by single spaces, ending in
`\n`, at most 63 characters. Integers are decimal. Anything malformed or out of
range is dropped. The gun module only accepts Bluetooth data over an encrypted,
bonded connection.

## Pi to gun module

| Line | Meaning |
|---|---|
| `H <version> <role>` | Hello, sent every second. Version is 1, role is `pi` |
| `C <seq> <az> <el> <range_cm> <age_ms>` | Target seen. `az`/`el`: target centre relative to the camera axis, millidegrees, + = right / up, at most ±45000. `range_cm`: 0 if unknown. `age_ms`: time from exposure to sending, at most 2000 |
| `N <seq>` | Frame processed, no target |

## Gun module to Pi

| Line | Meaning |
|---|---|
| `H 1 nrf` | Hello, every 2 seconds and on connect |
| `A <route>` | Output route: 1 = wired, 2 = Bluetooth through the Pi, 3 = both |
| `T <freq_dHz> <left%> <right%> <flags>` | Tone for the Pi to play, 25 times a second when the route includes Bluetooth. Frequency in tenths of a Hz. Flags: 1 = cant flutter, 2 = target-lost beeps. The Pi goes silent if these stop for 300 ms |
| `Z <cam>` | Zeroed. 1 = camera and tilt, 0 = tilt only |

## How the gun module uses camera data

The gun module keeps its own estimate of aim error and moves it with the gyro
at 100 Hz. When a `C` line arrives, it looks back `age_ms` (plus a small link
allowance) in its gyro history to see where it was pointing when that frame
was exposed. It then corrects its estimate by the difference. So a frame that is
60 ms old doesn't drag the tone back to where you were 60 ms ago.
