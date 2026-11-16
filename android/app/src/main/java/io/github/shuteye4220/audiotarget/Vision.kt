package io.github.shuteye4220.audiotarget

import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sqrt

/** A greyscale camera frame, upright. */
class Frame(val data: ByteArray, val w: Int, val h: Int) {
    fun at(x: Int, y: Int): Int = data[y * w + x].toInt() and 0xFF
}

/**
 * Aim point in full-frame pixels, and what kind of thing it is (class id, -1 if
 * unknown). For the printed card, [cardH] maps card millimetres to pixels.
 */
data class Detection(
    val x: Double,
    val y: Double,
    val size: Double,
    val score: Double,
    val classId: Int = -1,
    val cardH: DoubleArray? = null,
)

/**
 * YOLO output decoding (mirror of pi/audiotarget/detectors/onnx.py).
 * Raw: (1, 4 + nc [+ mask coefs], N). End-to-end: (1, N, 6) = x1 y1 x2 y2 score class.
 * Returns [cx, cy, w, h, score, classId] in network-input pixels, or null.
 */
object YoloDecode {
    fun decode(data: FloatArray, shape: LongArray, classes: IntArray, conf: Float): FloatArray? {
        val dims = shape.filter { it != 1L }.map { it.toInt() }
        if (dims.size != 2) return null
        val (a, b) = dims
        if (b == 6 && a != 6) { // end-to-end, rows of 6
            var best = -1
            for (i in 0 until a) {
                val s = data[i * 6 + 4]
                val c = data[i * 6 + 5].roundToInt()
                if (s >= conf && c in classes && (best < 0 || s > data[best * 6 + 4])) best = i
            }
            if (best < 0) return null
            val o = best * 6
            val x1 = data[o]; val y1 = data[o + 1]; val x2 = data[o + 2]; val y2 = data[o + 3]
            return floatArrayOf((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1, data[o + 4], data[o + 5])
        }
        // Raw: channels-first (rows = 4 + nc..., cols = candidates)
        val rows = a
        val n = b
        val classRows = classes.map { 4 + it }.filter { it < rows }
        if (classRows.isEmpty()) return null
        var bestI = -1
        var bestR = -1
        var bestS = -1f
        for (r in classRows) {
            val base = r * n
            for (i in 0 until n) {
                val s = data[base + i]
                if (s > bestS) { bestS = s; bestI = i; bestR = r }
            }
        }
        if (bestI < 0 || bestS < conf || bestS.isNaN()) return null
        return floatArrayOf(
            data[bestI], data[n + bestI], data[2 * n + bestI], data[3 * n + bestI], bestS, (bestR - 4).toFloat()
        )
    }

    /** Count classes from Ultralytics' "names" metadata, e.g. "{0: 'bullseye', 1: 'x'}". */
    fun classCount(namesMeta: String?): Int {
        if (namesMeta == null) return 1
        return Regex("""(\d+)\s*:""").findAll(namesMeta).count().coerceAtLeast(1)
    }

    fun classNames(namesMeta: String?): List<String> {
        if (namesMeta == null) return emptyList()
        return Regex("""\d+\s*:\s*'([^']*)'""").findAll(namesMeta).map { it.groupValues[1] }.toList()
    }
}

/**
 * Normalised cross-correlation template tracking on a downscaled grid
 * (mirror of the Pi's ml_tracker.py, written without OpenCV).
 */
class Template private constructor(
    private val t: FloatArray, // zero-mean, unit-norm
    val tw: Int,
    val th: Int,
    val scale: Int,
    val fullSize: Int,
) {
    companion object {
        const val GRID = 32 // template side in grid cells

        /** Cut a square template of side ~1.2 x detection size centred on (cx, cy). */
        fun cut(f: Frame, cx: Double, cy: Double, size: Double): Template? {
            val full = (size * 1.2).coerceIn(16.0, 320.0).roundToInt()
            val scale = max(1, (full + GRID - 1) / GRID)
            val side = full / scale
            val x0 = (cx - side * scale / 2.0).roundToInt()
            val y0 = (cy - side * scale / 2.0).roundToInt()
            if (x0 < 0 || y0 < 0 || x0 + side * scale > f.w || y0 + side * scale > f.h) return null
            val t = boxDown(f, x0, y0, side, side, scale)
            if (!normalise(t)) return null
            return Template(t, side, side, scale, side * scale)
        }

        fun boxDown(f: Frame, x0: Int, y0: Int, cw: Int, ch: Int, s: Int): FloatArray {
            val out = FloatArray(cw * ch)
            val inv = 1f / (s * s)
            for (gy in 0 until ch) for (gx in 0 until cw) {
                var acc = 0
                val bx = x0 + gx * s
                val by = y0 + gy * s
                for (yy in by until by + s) {
                    val row = yy * f.w
                    for (xx in bx until bx + s) acc += f.data[row + xx].toInt() and 0xFF
                }
                out[gy * cw + gx] = acc * inv
            }
            return out
        }

        private fun normalise(t: FloatArray): Boolean {
            val mean = t.average().toFloat()
            var ss = 0f
            for (i in t.indices) { t[i] -= mean; ss += t[i] * t[i] }
            if (ss < 1e-3f * t.size) return false // flat patch: nothing to track
            val inv = 1f / sqrt(ss)
            for (i in t.indices) t[i] *= inv
            return true
        }
    }

    /**
     * Search a window of `searchScale` x template size around (px, py).
     * Returns (x, y, score) of the template centre in full-frame pixels.
     */
    fun match(f: Frame, px: Double, py: Double, searchScale: Double = 2.5): Triple<Double, Double, Double>? {
        val sw = (tw * searchScale).roundToInt()
        val sh = (th * searchScale).roundToInt()
        var x0 = (px - sw * scale / 2.0).roundToInt()
        var y0 = (py - sh * scale / 2.0).roundToInt()
        x0 = x0.coerceIn(0, max(0, f.w - sw * scale))
        y0 = y0.coerceIn(0, max(0, f.h - sh * scale))
        val cw = min(sw, (f.w - x0) / scale)
        val ch = min(sh, (f.h - y0) / scale)
        if (cw < tw || ch < th) return null
        val win = boxDown(f, x0, y0, cw, ch, scale)
        val ow = cw - tw + 1
        val oh = ch - th + 1
        val res = FloatArray(ow * oh)
        val n = tw * th
        for (oy in 0 until oh) for (ox in 0 until ow) {
            var sum = 0f; var sumSq = 0f; var dot = 0f
            var k = 0
            for (ty in 0 until th) {
                val row = (oy + ty) * cw + ox
                for (tx in 0 until tw) {
                    val v = win[row + tx]
                    sum += v; sumSq += v * v; dot += v * t[k++]
                }
            }
            // t is zero-mean, so the window mean drops out of the dot product
            val varW = sumSq - sum * sum / n
            res[oy * ow + ox] = if (varW > 1e-3f) dot / sqrt(varW) else 0f
        }
        var bi = 0
        for (i in res.indices) if (res[i] > res[bi]) bi = i
        val bx = bi % ow
        val by = bi / ow
        val subX = bx + parabola(res, ow, oh, bx, by, true)
        val subY = by + parabola(res, ow, oh, bx, by, false)
        val cx = x0 + (subX + tw / 2.0) * scale
        val cy = y0 + (subY + th / 2.0) * scale
        return Triple(cx, cy, res[bi].toDouble())
    }

    private fun parabola(r: FloatArray, w: Int, h: Int, x: Int, y: Int, horiz: Boolean): Double {
        val (a, c, b) = if (horiz) {
            if (x <= 0 || x >= w - 1) return 0.0
            Triple(r[y * w + x - 1], r[y * w + x], r[y * w + x + 1])
        } else {
            if (y <= 0 || y >= h - 1) return 0.0
            Triple(r[(y - 1) * w + x], r[y * w + x], r[(y + 1) * w + x])
        }
        val d = a - 2 * c + b
        if (d == 0f) return 0.0
        return (0.5 * (a - b) / d).coerceIn(-0.5, 0.5)
    }
}
