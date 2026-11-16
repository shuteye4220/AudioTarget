package io.github.shuteye4220.audiotarget

import kotlin.math.abs
import kotlin.math.pow
import kotlin.math.roundToInt

/** Same mapping as the gun module firmware (firmware/src/tonemap.c). */
data class ToneCfg(
    val baseHz: Double = 440.0,
    val mdegPerSemitone: Int = 100,
    val quantize: Boolean = true,
    val maxSemitones: Int = 24,
    val azFullMdeg: Int = 2000,
    val azDeadbandMdeg: Int = 100,
    val minSideGain: Double = 0.1,
    val cantWarnMdeg: Int = 2000,
)

data class Tone(val freqHz: Double, val gainL: Double, val gainR: Double, val flags: Int) {
    companion object {
        val SILENT = Tone(440.0, 0.0, 0.0, 0)
    }
}

object ToneMap {
    const val FLAG_CANT = 1
    const val FLAG_LOST = 2

    /**
     * elErr: + = aiming high, azErr: + = aiming right (millidegrees).
     * The louder ear is the side the target is on.
     */
    fun compute(cfg: ToneCfg, elErr: Int, azErr: Int, azValid: Boolean, lost: Boolean, cant: Int): Tone {
        var semis = elErr.toDouble() / cfg.mdegPerSemitone
        if (cfg.quantize) semis = semis.roundToInt().toDouble()
        semis = semis.coerceIn(-cfg.maxSemitones.toDouble(), cfg.maxSemitones.toDouble())
        val freq = cfg.baseHz * 2.0.pow(semis / 12.0)

        var gl = 1.0
        var gr = 1.0
        if (azValid && abs(azErr) > cfg.azDeadbandMdeg) {
            val span = (cfg.azFullMdeg - cfg.azDeadbandMdeg).toDouble()
            val mag = (abs(azErr) - cfg.azDeadbandMdeg).toDouble()
            val far = 1.0 - (mag / span).coerceIn(0.0, 1.0) * (1.0 - cfg.minSideGain)
            if (azErr > 0) gr = far else gl = far
        }
        var flags = 0
        if (abs(cant) > cfg.cantWarnMdeg) flags = flags or FLAG_CANT
        if (lost) flags = flags or FLAG_LOST
        return Tone(freq, gl, gr, flags)
    }

    /** Flutter / beep patterns, identical to the firmware and the Pi. */
    fun gateOn(flags: Int, tMs: Long): Boolean {
        var on = true
        if (flags and FLAG_CANT != 0) on = on && ((tMs / 62) and 1L) == 0L
        if (flags and FLAG_LOST != 0) on = on && (tMs % 500) < 150
        return on
    }
}

/** Where the target is, in words. */
fun describeTarget(azMdeg: Double, elMdeg: Double, rangeM: Double?): String {
    fun part(v: Double, pos: String, neg: String, zero: String): String {
        val d = abs(v) / 1000.0
        if (d < 0.05) return zero
        return "%.1f degrees %s".format(d, if (v > 0) pos else neg)
    }
    var s = "Target ${part(azMdeg, "right", "left", "centred")}, ${part(elMdeg, "up", "down", "level")}"
    if (rangeM != null) s += ", %.0f metres".format(rangeM)
    return s
}
