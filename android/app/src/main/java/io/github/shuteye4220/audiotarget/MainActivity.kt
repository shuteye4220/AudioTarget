package io.github.shuteye4220.audiotarget

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.util.Size
import android.view.KeyEvent
import android.view.Surface
import android.view.View
import android.view.WindowManager
import android.view.accessibility.AccessibilityManager
import android.widget.Button
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import java.io.File
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import kotlin.math.asin
import kotlin.math.atan
import kotlin.math.atan2
import kotlin.math.sqrt
import kotlin.math.tan

/**
 * AudioTarget phone prototype: the phone's camera stands in for the gun camera,
 * an ONNX model stands in for the Pi 5's ML fallback, and the phone plays the
 * same guidance tone as the gun module.
 */
class MainActivity : AppCompatActivity(), SensorEventListener {

    private val prefs by lazy { getSharedPreferences("audiotarget", Context.MODE_PRIVATE) }
    private val tone = ToneEngine()
    private lateinit var announcer: Announcer
    private lateinit var cameraExecutor: ExecutorService
    private val modelExecutor = Executors.newSingleThreadExecutor()
    private var camera: Camera? = null

    @Volatile private var detector: OnnxDetector? = null
    @Volatile private var tracker: MlTracker? = null

    // Settings (cycled by buttons, saved in prefs)
    private val zooms = doubleArrayOf(1.0, 2.0, 5.0, 10.0)
    private val paces = listOf(
        Triple("phone speed", 0L, "phone"),
        Triple("like a Pi 5", 100L, "pi5"),
        Triple("like a Pi Zero 2 W", 1000L, "zero"),
    )
    private val steps = intArrayOf(50, 100, 200, 500)
    private val confs = floatArrayOf(0.15f, 0.25f, 0.4f)

    // Aim state, guarded by `lock`
    private val lock = Any()
    private var hfovDeg = 70.0
    private var frameW = 1280
    private var frameH = 720
    private var targetAz = 0.0
    private var targetEl = 0.0
    private var lastFix = 0L
    private var lastClass = -1
    private var zeroAz = 0.0
    private var zeroEl = 0.0
    private var pitchMdeg = 0.0
    private var rollDeg = 0.0
    private var pitch0 = 0.0
    private var roll0: Double? = null
    private var tiltZeroed = false
    private var hadTarget = false
    private var lostSince = 0L
    private var frames = 0
    private var fpsWindowStart = 0L
    @Volatile private var fps = 0.0

    @Volatile private var muted = false

    private val pickModel = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) importModel(uri)
    }

    // ------------------------------------------------------------------ lifecycle
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        announcer = Announcer(this, findViewById(R.id.status))
        cameraExecutor = Executors.newSingleThreadExecutor()

        bind(R.id.btn_zero) { zero() }
        bind(R.id.btn_where) { where() }
        bind(R.id.btn_mute) { toggleMute() }
        bind(R.id.btn_zoom) { cycle("zoom", zooms.size); applyZoom(); say("Zoom ${zoomName()}") }
        bind(R.id.btn_pace) { cycle("pace", paces.size); applyPace(); say("Model speed ${paces[idx("pace")].first}") }
        bind(R.id.btn_track) {
            prefs.edit().putBoolean("track", !prefs.getBoolean("track", true)).apply()
            applyPace()
            say(if (prefs.getBoolean("track", true)) "Tracking between detections on" else "Tracking off: model answers only")
        }
        bind(R.id.btn_step) { cycle("step", steps.size); say("Each semitone is ${stepName()}") }
        bind(R.id.btn_conf) { cycle("conf", confs.size); detector?.conf = confs[idx("conf")]; say("Minimum score ${confs[idx("conf")]}") }
        bind(R.id.btn_status) { say(statusText()) }
        bind(R.id.btn_model) { pickModel.launch(arrayOf("application/octet-stream", "*/*")) }
        bind(R.id.btn_lookfor) {
            val opts = lookForOptions()
            val next = opts[(opts.indexOf(lookForName()) + 1) % opts.size]
            prefs.edit().putString("lookfor", next).apply()
            applyLookFor()
            say("Looking for $next")
        }
        bind(R.id.btn_modelsrc) {
            if (!modelFile().exists()) {
                say("No model file of your own yet. Use Load model.")
            } else {
                prefs.edit().putBoolean("custom", !prefs.getBoolean("custom", false))
                    .putString("lookfor", ANYTHING).apply()
                loadModel(initial = false)
            }
        }
        bind(R.id.btn_keys) {
            prefs.edit().putBoolean("volkeys", !prefs.getBoolean("volkeys", false)).apply()
            say(if (prefs.getBoolean("volkeys", false)) "Volume up zeroes, volume down says where the target is"
                else "Volume keys back to normal")
        }
        bind(R.id.btn_announce) {
            prefs.edit().putBoolean("announce", !prefs.getBoolean("announce", true)).apply()
            say(if (prefs.getBoolean("announce", true)) "Announcements on" else "Announcements off")
        }
        refreshLabels()

        tone.start()
        loadModel(initial = true)
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            startCamera()
        } else {
            requestPermissions(arrayOf(Manifest.permission.CAMERA), 1)
        }
    }

    override fun onRequestPermissionsResult(code: Int, perms: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(code, perms, results)
        if (results.firstOrNull() == PackageManager.PERMISSION_GRANTED) startCamera()
        else say("Camera permission is needed. Tilt guidance still works.")
    }

    override fun onResume() {
        super.onResume()
        val sm = getSystemService(SensorManager::class.java)
        sm.getDefaultSensor(Sensor.TYPE_GRAVITY)?.let { sm.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME) }
        tone.start()
    }

    override fun onPause() {
        super.onPause()
        getSystemService(SensorManager::class.java).unregisterListener(this)
        tone.stop() // silence when you leave the app
    }

    override fun onDestroy() {
        super.onDestroy()
        cameraExecutor.shutdown()
        modelExecutor.execute {
            tracker?.close()
            detector?.close()
        }
        modelExecutor.shutdown()
        announcer.shutdown()
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (prefs.getBoolean("volkeys", false)) {
            when (keyCode) {
                KeyEvent.KEYCODE_VOLUME_UP -> { if (event?.repeatCount == 0) zero(); return true }
                KeyEvent.KEYCODE_VOLUME_DOWN -> { if (event?.repeatCount == 0) where(); return true }
            }
        }
        return super.onKeyDown(keyCode, event)
    }

    // ------------------------------------------------------------------ settings helpers
    private fun bind(id: Int, action: () -> Unit) {
        findViewById<Button>(id).setOnClickListener { action(); refreshLabels() }
    }

    private fun idx(key: String): Int = prefs.getInt(key, when (key) { "step" -> 1; "conf" -> 1; "pace" -> 1; else -> 0 })
    private fun cycle(key: String, n: Int) = prefs.edit().putInt(key, (idx(key) + 1) % n).apply()
    private fun zoomName() = "${zooms[idx("zoom")].toInt()} times" + if (zooms[idx("zoom")] >= 5.0) ", telephoto" else ""
    private fun stepName() = "%.2f degrees".format(steps[idx("step")] / 1000.0)

    private fun refreshLabels() {
        fun label(id: Int, text: String) { findViewById<Button>(id).text = text }
        label(R.id.btn_mute, if (muted) "Unmute" else "Mute")
        label(R.id.btn_zoom, "Zoom: ${zooms[idx("zoom")].toInt()}x")
        label(R.id.btn_pace, "Model speed: ${paces[idx("pace")].first}")
        label(R.id.btn_track, "Tracking between detections: ${if (prefs.getBoolean("track", true)) "on" else "off"}")
        label(R.id.btn_step, "Semitone step: ${stepName()}")
        label(R.id.btn_conf, "Minimum score: ${confs[idx("conf")]}")
        label(R.id.btn_keys, "Volume keys as buttons: ${if (prefs.getBoolean("volkeys", false)) "on" else "off"}")
        label(R.id.btn_announce, "Announcements: ${if (prefs.getBoolean("announce", true)) "on" else "off"}")
        label(R.id.btn_lookfor, "Look for: ${lookForName()}")
        label(R.id.btn_modelsrc, "Model: ${if (useCustom()) "your file" else "built-in objects"}")
    }

    private fun say(text: String) = announcer.say(text)

    // ------------------------------------------------------------------ model
    private fun modelFile() = File(filesDir, "targets.onnx")
    private fun builtinFile() = File(filesDir, BUILTIN_ASSET)
    private fun useCustom() = prefs.getBoolean("custom", false) && modelFile().exists()

    /** Copy the built-in model out of the APK (again if the APK's copy changed). */
    private fun extractBuiltin(): File? = try {
        val f = builtinFile()
        assets.openFd(BUILTIN_ASSET).use { fd ->
            if (!f.exists() || f.length() != fd.length) {
                assets.open(BUILTIN_ASSET).use { input -> f.outputStream().use { input.copyTo(it) } }
            }
        }
        f
    } catch (e: Exception) {
        null
    }

    private fun loadModel(initial: Boolean) {
        modelExecutor.execute {
            val f = if (useCustom()) modelFile() else extractBuiltin()
            if (f == null) {
                runOnUiThread { say("No target model in this build. Tilt guidance only. Use Load model to add one.") }
                return@execute
            }
            val d = try {
                OnnxDetector(f.path, useXnnpack = true)
            } catch (e: Exception) {
                try { OnnxDetector(f.path, useXnnpack = false) } catch (e2: Exception) { null }
            }
            if (d == null) {
                runOnUiThread { say("That model file couldn't be loaded.") }
                return@execute
            }
            d.conf = confs[idx("conf")]
            val oldDetector = detector
            val oldTracker = tracker
            tracker = MlTracker(d)
            detector = d
            oldTracker?.close()   // waits for any detection still running on the old model
            oldDetector?.close()
            runOnUiThread {
                applyPace()
                applyLookFor()
                refreshLabels()
                val which = if (useCustom()) "your model" else "built-in object model"
                say((if (initial) "AudioTarget ready, " else "Loaded ") + which + ". Looking for ${lookForName()}.")
            }
        }
    }

    /** What the user can choose to look for with the current model. */
    private fun lookForOptions(): List<String> {
        val d = detector ?: return listOf(ANYTHING)
        val names = d.classNames
        return if (names.size == 80 && names.firstOrNull() == "person") {
            listOf(ANYTHING) + COCO_CHOICES.filter { it in names }
        } else {
            listOf(ANYTHING) + names
        }
    }

    private fun lookForName(): String {
        val opts = lookForOptions()
        val saved = prefs.getString("lookfor", ANYTHING) ?: ANYTHING
        return if (saved in opts) saved else ANYTHING
    }

    private fun applyLookFor() {
        val d = detector ?: return
        val name = lookForName()
        val i = d.classNames.indexOf(name)
        d.classes = if (name == ANYTHING || i < 0) IntArray(d.classCount) { it } else intArrayOf(i)
        tracker?.reset()
    }

    private fun className(id: Int): String {
        val names = detector?.classNames ?: return "Target"
        return names.getOrNull(id)?.replaceFirstChar { it.uppercase() } ?: "Target"
    }

    private fun importModel(uri: Uri) {
        modelExecutor.execute {
            try {
                val tmp = File(filesDir, "targets.onnx.tmp")
                contentResolver.openInputStream(uri)?.use { input ->
                    tmp.outputStream().use { out ->
                        // Stop at a sane size rather than filling storage.
                        val chunk = ByteArray(1 shl 16)
                        var total = 0L
                        while (true) {
                            val n = input.read(chunk)
                            if (n < 0) break
                            total += n
                            require(total <= MAX_MODEL_BYTES) { "too big" }
                            out.write(chunk, 0, n)
                        }
                        require(total > 0) { "empty" }
                    }
                } ?: error("unreadable")
                check(tmp.renameTo(modelFile()))
                prefs.edit().putBoolean("custom", true).putString("lookfor", ANYTHING).apply()
                loadModel(initial = false)
            } catch (e: Exception) {
                File(filesDir, "targets.onnx.tmp").delete()
                runOnUiThread { say("Couldn't import that file.") }
            }
        }
    }

    private fun applyPace() {
        val t = tracker ?: return
        t.minIntervalMs = paces[idx("pace")].second
        t.trackBetween = prefs.getBoolean("track", true)
        t.reset()
    }

    // ------------------------------------------------------------------ camera
    private fun startCamera() {
        hfovDeg = mainCameraHfov() ?: 70.0
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            val provider = future.get()
            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(findViewById<PreviewView>(R.id.preview).surfaceProvider)
            }
            val selector = ResolutionSelector.Builder()
                .setResolutionStrategy(ResolutionStrategy(Size(1280, 720), ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER))
                .setAspectRatioStrategy(AspectRatioStrategy.RATIO_16_9_FALLBACK_AUTO_STRATEGY)
                .build()
            val analysis = ImageAnalysis.Builder()
                .setResolutionSelector(selector)
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
                .build()
            analysis.setAnalyzer(cameraExecutor) { img -> analyze(img) }
            try {
                provider.unbindAll()
                camera = provider.bindToLifecycle(this, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
                applyZoom()
            } catch (e: Exception) {
                say("Couldn't start the camera.")
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun mainCameraHfov(): Double? = try {
        val cm = getSystemService(CameraManager::class.java)
        val id = cm.cameraIdList.first {
            cm.getCameraCharacteristics(it).get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK
        }
        val ch = cm.getCameraCharacteristics(id)
        val w = ch.get(CameraCharacteristics.SENSOR_INFO_PHYSICAL_SIZE)!!.width.toDouble()
        val f = ch.get(CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS)!!.first().toDouble()
        Math.toDegrees(2 * atan(w / (2 * f)))
    } catch (e: Exception) {
        null
    }

    private fun applyZoom() {
        val cam = camera ?: return
        val max = cam.cameraInfo.zoomState.value?.maxZoomRatio ?: 1f
        cam.cameraControl.setZoomRatio(minOf(zooms[idx("zoom")].toFloat(), max))
        synchronized(lock) { lastFix = 0 }
        tracker?.reset()
    }

    private var buf = ByteArray(0)

    private fun analyze(img: ImageProxy) {
        try {
            val f = toUprightGrey(img)
            val now = System.currentTimeMillis()
            val det = tracker?.process(f, now)
            val zoomNow = camera?.cameraInfo?.zoomState?.value?.zoomRatio?.toDouble() ?: 1.0
            synchronized(lock) {
                frameW = f.w; frameH = f.h
                frames++
                if (now - fpsWindowStart >= 2000) {
                    fps = frames * 1000.0 / (now - fpsWindowStart).coerceAtLeast(1)
                    frames = 0; fpsWindowStart = now
                }
                if (det != null) {
                    // Pixel -> angle from the optical axis (+right, +up), millidegrees.
                    val fx = (f.w / 2.0) / tan(Math.toRadians(hfovDeg) / 2) * zoomNow
                    targetAz = Math.toDegrees(atan2(det.x - f.w / 2.0, fx)) * 1000
                    targetEl = Math.toDegrees(atan2(f.h / 2.0 - det.y, fx)) * 1000
                    lastFix = now
                    lastClass = det.classId
                }
            }
            updateTone()
        } finally {
            img.close()
        }
    }

    private fun toUprightGrey(img: ImageProxy): Frame {
        val plane = img.planes[0]
        val w = img.width
        val h = img.height
        if (buf.size != w * h) buf = ByteArray(w * h)
        val src = plane.buffer
        val rs = plane.rowStride
        for (y in 0 until h) {
            src.position(y * rs)
            src.get(buf, y * w, w)
        }
        return when (img.imageInfo.rotationDegrees) {
            90 -> Frame(rotate(buf, w, h, 90), h, w)
            180 -> Frame(rotate(buf, w, h, 180), w, h)
            270 -> Frame(rotate(buf, w, h, 270), h, w)
            else -> Frame(buf, w, h)
        }
    }

    private fun rotate(s: ByteArray, w: Int, h: Int, deg: Int): ByteArray {
        val d = ByteArray(w * h)
        when (deg) {
            90 -> for (y in 0 until h) for (x in 0 until w) d[x * h + (h - 1 - y)] = s[y * w + x]
            180 -> for (i in 0 until w * h) d[w * h - 1 - i] = s[i]
            270 -> for (y in 0 until h) for (x in 0 until w) d[(w - 1 - x) * h + y] = s[y * w + x]
        }
        return d
    }

    // ------------------------------------------------------------------ tilt (gravity)
    override fun onSensorChanged(e: SensorEvent) {
        val (gx, gy, gz) = Triple(e.values[0].toDouble(), e.values[1].toDouble(), e.values[2].toDouble())
        val g = sqrt(gx * gx + gy * gy + gz * gz).coerceAtLeast(1e-3)
        synchronized(lock) {
            // The camera looks out of the back (-Z): elevation of that axis.
            pitchMdeg = Math.toDegrees(asin((-gz / g).coerceIn(-1.0, 1.0))) * 1000
            rollDeg = Math.toDegrees(atan2(gx, gy))
        }
        updateTone()
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    /** Sideways tilt relative to the zero (or to level landscape before zeroing), in mdeg. */
    private fun cantMdeg(): Int {
        val rotation = if (Build.VERSION.SDK_INT >= 30) display?.rotation
            else @Suppress("DEPRECATION") windowManager.defaultDisplay.rotation
        val ref = roll0 ?: when (rotation ?: Surface.ROTATION_90) {
            Surface.ROTATION_270 -> -90.0
            else -> 90.0
        }
        var d = rollDeg - ref
        while (d > 180) d -= 360
        while (d < -180) d += 360
        return (d * 1000).toInt()
    }

    // ------------------------------------------------------------------ guidance
    private fun updateTone() {
        val now = System.currentTimeMillis()
        var announce: String? = null
        val t: Tone
        synchronized(lock) {
            val cam = now - lastFix < 300
            val cfg = ToneCfg(mdegPerSemitone = steps[idx("step")])
            val lost = tracker != null && !cam
            t = if (cam) {
                ToneMap.compute(cfg, (zeroEl - targetEl).toInt(), (zeroAz - targetAz).toInt(), true, false, cantMdeg())
            } else {
                val p0 = if (tiltZeroed) pitch0 else 0.0
                ToneMap.compute(cfg, (pitchMdeg - p0).toInt(), 0, false, lost, cantMdeg())
            }
            if (cam && !hadTarget) {
                hadTarget = true
                announce = "${className(lastClass)} found"
            } else if (!cam && hadTarget) {
                if (lostSince == 0L) lostSince = now
                if (now - lostSince > 1000) {
                    hadTarget = false
                    announce = "Target lost"
                }
            }
            if (cam) lostSince = 0L
        }
        tone.tone = if (muted) Tone.SILENT else t
        val msg = announce
        if (msg != null && prefs.getBoolean("announce", true)) runOnUiThread { say(msg) }
    }

    private fun zero() {
        val camZero: Boolean
        synchronized(lock) {
            camZero = System.currentTimeMillis() - lastFix < 300
            if (camZero) { zeroAz = targetAz; zeroEl = targetEl }
            pitch0 = pitchMdeg
            roll0 = rollDeg
            tiltZeroed = true
        }
        say(if (camZero) "Zeroed on target" else "Zeroed, tilt only")
    }

    private fun where() {
        val text = synchronized(lock) {
            if (System.currentTimeMillis() - lastFix < 1000) describeTarget(targetAz, targetEl, null, className(lastClass)) else "No target"
        }
        say(text)
    }

    private fun toggleMute() {
        muted = !muted
        if (muted) tone.tone = Tone.SILENT
        say(if (muted) "Muted" else "Unmuted")
    }

    private fun statusText(): String {
        val t = tracker
        val d = detector
        val parts = mutableListOf<String>()
        parts += "Camera %.0f frames per second, zoom %s, field of view %.0f degrees".format(
            fps, zoomName(), hfovDeg / zooms[idx("zoom")])
        if (t == null || d == null) {
            parts += "No model, tilt only"
        } else {
            parts += "Looking for ${lookForName()}"
            parts += "Model input ${d.size}, %.0f milliseconds per detection, %.1f detections per second, %s"
                .format(t.lastInferenceMs.toDouble(), t.runsPerSecond, paces[idx("pace")].first)
            parts += if (prefs.getBoolean("track", true)) "tracking between detections" else "no tracking"
        }
        return parts.joinToString(". ") + "."
    }

    companion object {
        const val MAX_MODEL_BYTES = 200L * 1024 * 1024
        const val BUILTIN_ASSET = "coco.onnx"
        const val ANYTHING = "anything"

        /** Everyday COCO objects that make sensible practice targets. */
        val COCO_CHOICES = listOf(
            "person", "chair", "couch", "bench", "potted plant", "bottle", "cup", "sports ball",
            "backpack", "suitcase", "tv", "laptop", "teddy bear", "stop sign", "fire hydrant", "car",
        )
    }
}

/**
 * Speaks through the screen reader when one is running (its voice, its rate),
 * otherwise through text-to-speech.
 */
class Announcer(private val ctx: Context, private val live: TextView) {
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var toggle = false

    init {
        tts = TextToSpeech(ctx) { status -> ttsReady = status == TextToSpeech.SUCCESS }
    }

    fun say(text: String) {
        val am = ctx.getSystemService(AccessibilityManager::class.java)
        if (am.isEnabled && am.isTouchExplorationEnabled) {
            // Polite live region: the screen reader announces each change.
            toggle = !toggle
            live.text = if (toggle) text else "$text "
            live.accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_POLITE
        } else {
            live.text = text
            if (ttsReady) tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "at")
        }
    }

    fun shutdown() {
        tts?.shutdown()
    }
}
