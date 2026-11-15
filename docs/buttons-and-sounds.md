# Gun module: buttons and sounds

The gun module has two buttons on its lid. **ZERO** has a round cap and sits
toward the muzzle. **MODE** has a square cap and sits toward you. An engraved
arrow on the lid points at the muzzle.

While you hold a button, a short click marks 0.7 seconds (a "long" press) and
another marks 2.5 seconds (a "very long" press). Let go after the click you
want.

## The guidance tone

- **Pitch = high or low.** On target plays A4 (440 Hz). Each semitone above A
  means about 0.1 degree high, and each semitone below means 0.1 degree low.
  Pitch moves in whole semitones, so with perfect pitch you can read the error
  straight off the note. At 20 m, 0.1 degree is about 3.5 cm. Both the note and
  the degrees per semitone can be changed in the firmware settings
  (`CONFIG_AT_BASE_NOTE_HZ`, `CONFIG_AT_MDEG_PER_SEMITONE`).
- **Left or right (camera only):** the target is on the side of the **louder
  ear**, so turn toward the louder sound. Both ears are equal when you're within
  0.1 degree.
- **Fast flutter** (8 per second): the gun is tipped sideways (canted) by more
  than 2 degrees from how it was when you zeroed.
- **Slow beeping** (2 per second): the camera is running but can't see the card.
  Pitch falls back to tilt only until the card is found again.

## Buttons

| Press | ZERO (round) | MODE (square) |
|---|---|---|
| Short | **Zero here.** Two rising notes = zeroed on the camera and tilt. One note = tilt only (camera not seeing the card). Low buzz = couldn't zero | **Mute / unmute** guidance. Falling notes = muted, rising = unmuted. Status sounds still play |
| Long (0.7 s) | **Volume:** steps through 4 levels and plays a sample at the new level | **Output:** steps through 1 beep = wired earphones, 2 beeps = Bluetooth through the Pi, 3 beeps = both |
| Very long (2.5 s) | **Clear zero** (high note then low note) | **Bluetooth pairing:** three quick beeps, then the next new device has 2 minutes to pair |
| Both together, very long | **Mount calibration**, see below | |

If you choose Bluetooth output and the Pi isn't connected, the tone stays on
the wired output so you're never left without sound.

## Mount calibration (once, with the box on the gun)

This teaches the module which way its sensor faces on your gun. Redo it if you
move the box.

1. Hold **both** buttons until the second click, then let go. A long tone plays.
2. Hold the gun **level and still**. After a couple of seconds it plays two
   beeps.
3. Point the muzzle **well up** (at least 30 degrees) and hold still.
4. A rising four-note chime means done. A low buzz means it failed or timed out
   after 30 seconds; start again.

Calibrating clears the tilt zero, so zero again afterwards.

## Other sounds

| Sound | Meaning |
|---|---|
| Rising three notes (C E G) | Switched on |
| Two quick rising high notes | Pi connected by Bluetooth |
| Two quick falling high notes | Pi disconnected |
| Falling four notes | Powering off: 10 minutes without movement. Press MODE to wake it |
| Low buzz | Error (also plays if the motion sensor stops responding) |

## First power-on

With no Pi paired yet, the module accepts Bluetooth pairing for 2 minutes after
each power-on. After that, only paired Pis can connect, unless you open the
pairing window again with a very long MODE press.
