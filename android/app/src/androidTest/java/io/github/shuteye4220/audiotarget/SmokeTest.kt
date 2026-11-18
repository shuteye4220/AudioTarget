package io.github.shuteye4220.audiotarget

import android.Manifest
import android.graphics.Rect
import android.view.View
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.rule.GrantPermissionRule
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Runs on an emulator in CI (Android 10 and Android 15) and on any phone with
 * `gradle connectedDebugAndroidTest`: does the app start, does the built-in
 * model run on this device's CPU, and are all buttons on screen?
 */
@RunWith(AndroidJUnit4::class)
class SmokeTest {
    @get:Rule
    val camera: GrantPermissionRule = GrantPermissionRule.grant(Manifest.permission.CAMERA)

    private val ctx get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun modelFromAssets(name: String): File {
        val f = File(ctx.cacheDir, name)
        ctx.assets.open(name).use { input -> f.outputStream().use { input.copyTo(it) } }
        return f
    }

    @Test
    fun builtInModelsRunOnThisCpu() {
        for (name in listOf(MainActivity.BUILTIN_ASSET, MainActivity.BUILTIN_FAST)) {
            val det = OnnxDetector(modelFromAssets(name).path, useXnnpack = true)
            assertTrue("$name should know 80 object types", det.classCount == 80)
            assertTrue(det.classNames.contains("chair"))
            // A synthetic frame: the result doesn't matter, running without a crash does.
            val w = 1280
            val h = 720
            val data = ByteArray(w * h) { ((it * 31) % 251).toByte() }
            repeat(3) { det.detect(Frame(data, w, h)) }
            det.close()
        }
    }

    /** Draw the printed card (markers from OpenCV itself) into a camera-sized frame. */
    private fun cardFrame(pxPerMm: Double, ox: Int, oy: Int): Frame {
        CardDetector() // loads OpenCV
        val w = 1280
        val h = 720
        val data = ByteArray(w * h) { 140.toByte() }
        val side = (CardGeometry.SIZE_MM * pxPerMm).toInt()
        for (y in 0 until side) for (x in 0 until side) data[(oy + y) * w + ox + x] = 255.toByte()
        val dict = org.opencv.objdetect.Objdetect.getPredefinedDictionary(org.opencv.objdetect.Objdetect.DICT_4X4_50)
        val m = (CardGeometry.MARKER_MM * pxPerMm).toInt()
        for (id in CardGeometry.IDS) {
            val img = org.opencv.core.Mat()
            org.opencv.objdetect.Objdetect.generateImageMarker(dict, id, m, img)
            val (mx, my) = CardGeometry.markerCorners(id)[0]
            val px = ByteArray(m * m)
            img.get(0, 0, px)
            for (y in 0 until m) for (x in 0 until m) {
                data[(oy + (my * pxPerMm).toInt() + y) * w + ox + (mx * pxPerMm).toInt() + x] = px[y * m + x]
            }
            img.release()
        }
        return Frame(data, w, h)
    }

    @Test
    fun findsThePrintedCardAndNamesRings() {
        val pxPerMm = 2.5
        val f = cardFrame(pxPerMm, 300, 100)
        val det = CardDetector().detect(f)
        assertTrue("card should be found", det != null)
        val cx = 300 + 100 * pxPerMm
        val cy = 100 + 100 * pxPerMm
        assertTrue("centre off by ${det!!.x - cx}, ${det.y - cy}",
            kotlin.math.abs(det.x - cx) < 1.5 && kotlin.math.abs(det.y - cy) < 1.5)
        val inv = CardGeometry.invert(det.cardH!!)!!
        // A point 30 mm above the centre on the paper is in the second ring (24-36 mm), high.
        val (mx, my) = CardGeometry.apply(inv, cx, cy - 30 * pxPerMm)!!
        assertEquals("second ring, high", CardGeometry.zone(mx, my))
    }

    @Test
    fun appStartsLoadsModelAndShowsAllButtons() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            var ready = false
            for (i in 0 until 60) {
                scenario.onActivity { ready = it.modelReady() }
                if (ready) break
                Thread.sleep(500)
            }
            assertTrue("model should load within 30 s", ready)
            scenario.onActivity { a ->
                val root = a.findViewById<View>(R.id.root)
                val screen = Rect()
                root.getGlobalVisibleRect(screen)
                for (id in listOf(R.id.btn_zero, R.id.btn_where, R.id.btn_mute, R.id.btn_lookfor,
                        R.id.btn_detail, R.id.btn_announce, R.id.btn_keys, R.id.btn_rings, R.id.btn_camera, R.id.btn_save, R.id.btn_lens)) {
                    val r = Rect()
                    val v = a.findViewById<View>(id)
                    assertTrue("${a.resources.getResourceEntryName(id)} visible", v.getGlobalVisibleRect(r))
                    assertTrue("${a.resources.getResourceEntryName(id)} big enough", r.height() > 20 && r.width() > 40)
                }
            }
        }
    }
}
