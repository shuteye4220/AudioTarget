package io.github.shuteye4220.audiotarget

import org.opencv.android.OpenCVLoader
import org.opencv.calib3d.Calib3d
import org.opencv.core.CvType
import org.opencv.core.Mat
import org.opencv.core.MatOfPoint2f
import org.opencv.core.Point
import org.opencv.objdetect.ArucoDetector
import org.opencv.objdetect.DetectorParameters
import org.opencv.objdetect.Objdetect
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min

/**
 * The printed AudioTarget card (targets/*.pdf): four ArUco markers, IDs 0-3,
 * in the corners. Same geometry as the Pi (pi/audiotarget/card.py). Pure
 * Kotlin, so it can be unit tested without OpenCV.
 */
object CardGeometry {
    const val SIZE_MM = 200.0
    const val MARKER_MM = 40.0
    const val MARGIN_MM = 8.0
    val IDS = 0..3

    /** Marker corners in card millimetres, OpenCV order: TL, TR, BR, BL. */
    fun markerCorners(index: Int): List<Pair<Double, Double>> {
        val near = MARGIN_MM
        val far = SIZE_MM - MARGIN_MM - MARKER_MM
        val (x, y) = listOf(near to near, far to near, far to far, near to far)[index]
        val s = MARKER_MM
        return listOf(x to y, x + s to y, x + s to y + s, x to y + s)
    }

    // Bullseye: 120 mm across, 10 alternating 6 mm bands (black outermost).
    // Scoring zones pair them up: bull's eye, then rings 1-4, 12 mm each.
    const val ZONE_MM = 12.0
    const val ZONES = 5
    val ZONE_NAMES = listOf("bull's eye", "first ring", "second ring", "third ring", "fourth ring")

    /**
     * Name the area of the card at (x, y) card millimetres, with a direction from
     * the centre, e.g. "second ring, high left". Card y runs downward.
     */
    fun zone(x: Double, y: Double): String {
        val c = SIZE_MM / 2
        val dx = x - c
        val dy = y - c
        val r = hypot(dx, dy)
        val area = when {
            r < ZONE_MM * ZONES -> ZONE_NAMES[(r / ZONE_MM).toInt()]
            x in 0.0..SIZE_MM && y in 0.0..SIZE_MM -> "on the card, outside the rings"
            else -> "off the card"
        }
        if (r < ZONE_MM) return area
        // Only name a direction component if it's a real part of the offset.
        val v = when { dy < -0.38 * r -> "high"; dy > 0.38 * r -> "low"; else -> "" }
        val h = when { dx < -0.38 * r -> "left"; dx > 0.38 * r -> "right"; else -> "" }
        val dir = listOf(v, h).filter { it.isNotEmpty() }.joinToString(" ")
        return if (dir.isEmpty()) area else "$area, $dir"
    }

    /** Inverse of a row-major 3x3 matrix, or null if singular. */
    fun invert(m: DoubleArray): DoubleArray? {
        val (a, b, c) = Triple(m[0], m[1], m[2])
        val (d, e, f) = Triple(m[3], m[4], m[5])
        val (g, h, i) = Triple(m[6], m[7], m[8])
        val A = e * i - f * h
        val B = -(d * i - f * g)
        val C = d * h - e * g
        val det = a * A + b * B + c * C
        if (kotlin.math.abs(det) < 1e-15) return null
        val inv = doubleArrayOf(
            A, -(b * i - c * h), b * f - c * e,
            B, a * i - c * g, -(a * f - c * d),
            C, -(a * h - b * g), a * e - b * d,
        )
        return DoubleArray(9) { inv[it] / det }
    }

    /** Apply a row-major 3x3 homography. */
    fun apply(h: DoubleArray, x: Double, y: Double): Pair<Double, Double>? {
        val w = h[6] * x + h[7] * y + h[8]
        if (kotlin.math.abs(w) < 1e-12) return null
        return (h[0] * x + h[1] * y + h[2]) / w to (h[3] * x + h[4] * y + h[5]) / w
    }
}

/** Finds the card with OpenCV's ArUco detector; searches near the last hit first. */
class CardDetector {
    private val aruco: ArucoDetector

    init {
        check(OpenCVLoader.initLocal()) { "OpenCV failed to load" }
        val params = DetectorParameters()
        params.set_cornerRefinementMethod(Objdetect.CORNER_REFINE_SUBPIX)
        aruco = ArucoDetector(Objdetect.getPredefinedDictionary(Objdetect.DICT_4X4_50), params)
    }

    private var last: Detection? = null

    fun reset() {
        last = null
    }

    fun detect(f: Frame): Detection? {
        val prev = last
        if (prev != null) {
            val half = max(160.0, prev.size * 1.5)
            val x0 = max(0, (prev.x - half).toInt())
            val y0 = max(0, (prev.y - half).toInt())
            val x1 = min(f.w, (prev.x + half).toInt())
            val y1 = min(f.h, (prev.y + half).toInt())
            if (x1 - x0 >= 64 && y1 - y0 >= 64) {
                detectIn(f, x0, y0, x1 - x0, y1 - y0)?.let { last = it; return it }
            }
        }
        last = detectIn(f, 0, 0, f.w, f.h)
        return last
    }

    private fun detectIn(f: Frame, x0: Int, y0: Int, w: Int, h: Int): Detection? {
        val crop = if (x0 == 0 && y0 == 0 && w == f.w && h == f.h) f.data else {
            ByteArray(w * h).also { out ->
                for (y in 0 until h) System.arraycopy(f.data, (y0 + y) * f.w + x0, out, y * w, w)
            }
        }
        val img = Mat(h, w, CvType.CV_8UC1)
        val ids = Mat()
        val corners = ArrayList<Mat>()
        try {
            img.put(0, 0, crop)
            aruco.detectMarkers(img, corners, ids)
            val obj = ArrayList<Point>()
            val px = ArrayList<Point>()
            var sides = 0.0
            var found = 0
            for (i in 0 until ids.rows()) {
                val id = ids.get(i, 0)[0].toInt()
                if (id !in CardGeometry.IDS) continue
                val c = corners[i]
                val pts = (0 until 4).map { k -> c.get(0, k).let { Point(it[0] + x0, it[1] + y0) } }
                CardGeometry.markerCorners(id).forEach { (mx, my) -> obj.add(Point(mx, my)) }
                px.addAll(pts)
                sides += hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y)
                found++
            }
            if (found == 0) return null
            val src = MatOfPoint2f(*obj.toTypedArray())
            val dst = MatOfPoint2f(*px.toTypedArray())
            val hm = Calib3d.findHomography(src, dst)
            src.release(); dst.release()
            if (hm.empty()) return null
            val h9 = DoubleArray(9)
            hm.get(0, 0, h9)
            hm.release()
            val (cx, cy) = CardGeometry.apply(h9, CardGeometry.SIZE_MM / 2, CardGeometry.SIZE_MM / 2) ?: return null
            val cardPx = sides / found * CardGeometry.SIZE_MM / CardGeometry.MARKER_MM
            return Detection(cx, cy, cardPx, found / 4.0, CARD_CLASS, h9)
        } finally {
            img.release()
            ids.release()
            corners.forEach { it.release() }
        }
    }

    companion object {
        const val CARD_CLASS = -2
    }
}
