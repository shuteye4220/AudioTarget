package io.github.shuteye4220.audiotarget

import android.Manifest
import android.graphics.Rect
import android.view.View
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.rule.GrantPermissionRule
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
                        R.id.btn_detail, R.id.btn_announce, R.id.btn_keys)) {
                    val r = Rect()
                    val v = a.findViewById<View>(id)
                    assertTrue("${a.resources.getResourceEntryName(id)} visible", v.getGlobalVisibleRect(r))
                    assertTrue("${a.resources.getResourceEntryName(id)} big enough", r.height() > 20 && r.width() > 40)
                }
            }
        }
    }
}
