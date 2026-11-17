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
import androidx.camera.core.ExperimentalLensFacing
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
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
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
    @Volatile private var speedChecked = false
    @Volatile private var card: CardDetector? = null
    @Volatile private var cardFailed = false

    /** For the instrumented smoke test. */
    fun modelReady(): Boolean = detector != null

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
    private var spokenClass = -1       // the object we last told the user about
    private var pendingClass = -1      // a different object, waiting to be confirmed
    private var pendingSince = 0L
    private var zoneNow: String? = null       // card area under the aim point
    private var spokenZone: String? = null
    private var pendingZone: String? = null
    private var pendingZoneSince = 0L
    private var cardRangeM: Double? = null
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
    @Volatile private var displayRotation = Surface.ROTATION_90
    @Volatile private var usingUsb = false

    private val pickModel = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) importModel(uri)
    }

    // ------------------------------------------------------------------ lifecycle
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        // Android 15+ draws apps edge to edge; keep the buttons clear of the
        // navigation bar, status bar and camera cut-out on every phone.
        WindowCompat.setDecorFitsSystemWindows(window, false)
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.root)) { v, insets ->
            val b = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            v.setPadding(b.left, b.top, b.right, b.bottom)
            insets
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        announcer = Announcer(this, findViewById(R.id.status))
        cameraExecutor = Executors.newSingleThreadExecutor()

        bind(R.id.btn_zero) { zero() }
        bind(R.id.btn_where) { where() }
        bind(R.id.btn_mute) { toggleMute() }
        bind(R.id.btn_camera) {
            val next = if (prefs.getString("cam", "auto") == "auto") "phone" else "auto"
            prefs.edit().putString("cam", next).apply()
            when {
                next == "phone" -> say("Phone camera only")
                externalIds().isNotEmpty() -> say("USB camera when plugged in")
                phoneSupportsUsbCameras() -> say("USB camera when plugged in. None found yet.")
                else -> say("USB camera when plugged in, but this phone doesn't offer USB cameras to apps.")
            }
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) startCamera()
        }
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
        bind(R.id.btn_save) {
            if (camera == null) say("The camera isn't running") else saveRequested = true
        }
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
                    .putString("lookfor", CARD_OR_ANY).apply()
                loadModel(initial = false)
            }
        }
        bind(R.id.btn_keys) {
            prefs.edit().putBoolean("volkeys", !prefs.getBoolean("volkeys", false)).apply()
            say(if (prefs.getBoolean("volkeys", false)) "Volume up zeroes, volume down says where the target is"
                else "Volume keys back to normal")
        }
        bind(R.id.btn_detail) {
            val order = listOf("auto", "high", "fast")
            val next = order[(order.indexOf(detail()) + 1) % order.size]
            prefs.edit().putString("detail", next).putBoolean("auto_fast", false).apply()
            speedChecked = false
            say("Detail $next")
            if (!useCustom()) loadModel(initial = false)
        }
        bind(R.id.btn_rings) {
            prefs.edit().putBoolean("rings", !prefs.getBoolean("rings", true)).apply()
            say(if (prefs.getBoolean("rings", true)) "Ring callouts on" else "Ring callouts off")
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
        val gravity = sm.getDefaultSensor(Sensor.TYPE_GRAVITY)
            ?: sm.getDefaultSensor(Sensor.TYPE_ACCELEROMETER) // budget phones without a gyroscope
        gravity?.let { sm.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME) }
        displayRotation = if (Build.VERSION.SDK_INT >= 30) display?.rotation ?: Surface.ROTATION_90
            else @Suppress("DEPRECATION") windowManager.defaultDisplay.rotation
        cameraManager.registerAvailabilityCallback(cameraWatch, null)
        tone.start()
    }

    override fun onPause() {
        super.onPause()
        getSystemService(SensorManager::class.java).unregisterListener(this)
        cameraManager.unregisterAvailabilityCallback(cameraWatch)
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
        label(R.id.btn_camera, "Camera: " + when {
            prefs.getString("cam", "auto") == "phone" -> "phone"
            usingUsb -> "USB, in use"
            else -> "USB if plugged in"
        })
        label(R.id.btn_rings, "Ring callouts: ${if (prefs.getBoolean("rings", true)) "on" else "off"}")
        label(R.id.btn_detail, "Detail: " + when (detail()) {
            "high" -> "high"
            "fast" -> "fast"
            else -> if (prefs.getBoolean("auto_fast", false)) "auto, using fast" else "auto"
        })
        label(R.id.btn_modelsrc, "Model: ${if (useCustom()) "your file" else "built-in objects"}")
    }

    private fun say(text: String) = announcer.say(text)

    // ------------------------------------------------------------------ model
    private fun modelFile() = File(filesDir, "targets.onnx")
    private fun useCustom() = prefs.getBoolean("custom", false) && modelFile().exists()

    /** "high" = 640 input (sees smaller, further things), "fast" = 320 input. */
    private fun detail(): String = prefs.getString("detail", "auto") ?: "auto"
    private fun builtinAsset(): String =
        if (detail() == "fast" || (detail() == "auto" && prefs.getBoolean("auto_fast", false))) BUILTIN_FAST else BUILTIN_ASSET

    /** Copy a built-in model out of the APK (again if the APK's copy changed). */
    private fun extractBuiltin(): File? = try {
        val name = builtinAsset()
        val f = File(filesDir, name)
        assets.openFd(name).use { fd ->
            if (!f.exists() || f.length() != fd.length) {
                assets.open(name).use { input -> f.outputStream().use { input.copyTo(it) } }
            }
        }
        f
    } catch (e: Exception) {
        null
    }

    /**
     * On "auto", watch the first few detections; if this phone takes too long
     * with the detailed model, switch to the fast one once and remember it.
     */
    private fun checkSpeed() {
        val t = tracker ?: return
        if (detail() != "auto" || useCustom() || prefs.getBoolean("auto_fast", false) || speedChecked) return
        if (t.runs < 6) return
        speedChecked = true
        if (t.medianInferenceMs > SLOW_MS) {
            prefs.edit().putBoolean("auto_fast", true).apply()
            runOnUiThread {
                say("This phone is slow with the detailed model, switching to the fast one.")
                loadModel(initial = false)
            }
        }
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
        val cardOpts = listOf(CARD_OR_ANY, CARD_ONLY)
        val d = detector ?: return cardOpts
        val names = d.classNames
        // The card is searched first unless one specific object is chosen. (An old
        // saved "anything" isn't in this list any more, so it falls back to the card.)
        return cardOpts + if (names.size == 80 && names.firstOrNull() == "person") {
            COCO_CHOICES.filter { it in names }
        } else {
            names
        }
    }

    private fun lookForName(): String {
        val opts = lookForOptions()
        val saved = prefs.getString("lookfor", CARD_OR_ANY) ?: CARD_OR_ANY
        return if (saved in opts) saved else CARD_OR_ANY
    }

    private fun applyLookFor() {
        val d = detector ?: return
        val name = lookForName()
        val i = d.classNames.indexOf(name)
        d.classes = if (i < 0) IntArray(d.classCount) { it } else intArrayOf(i)
        card?.reset()
        tracker?.reset()
    }

    private fun className(id: Int): String {
        if (id == CardDetector.CARD_CLASS) return "Card"
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
                prefs.edit().putBoolean("custom", true).putString("lookfor", CARD_OR_ANY).apply()
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
    private val cameraManager by lazy { getSystemService(CameraManager::class.java) }
    private var externalPresent = false

    /** USB cameras come and go: rebind when one appears or disappears. */
    private val cameraWatch = object : CameraManager.AvailabilityCallback() {
        override fun onCameraAvailable(id: String) = recheckExternal()
        override fun onCameraUnavailable(id: String) = recheckExternal()
    }

    private fun externalIds(): List<String> = try {
        cameraManager.cameraIdList.filter {
            cameraManager.getCameraCharacteristics(it).get(CameraCharacteristics.LENS_FACING) ==
                CameraCharacteristics.LENS_FACING_EXTERNAL
        }
    } catch (e: Exception) {
        emptyList()
    }

    private fun recheckExternal() {
        val now = externalIds().isNotEmpty()
        if (now != externalPresent) {
            externalPresent = now
            if (prefs.getString("cam", "auto") == "auto" &&
                ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
            ) startCamera()
        }
    }

    private fun phoneSupportsUsbCameras() = packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_EXTERNAL)

    @androidx.annotation.OptIn(markerClass = [ExperimentalLensFacing::class])
    private fun externalSelector(): CameraSelector =
        CameraSelector.Builder().requireLensFacing(CameraSelector.LENS_FACING_EXTERNAL).build()

    private fun startCamera() {
        externalPresent = externalIds().isNotEmpty()
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            val provider = future.get()
            val wantUsb = prefs.getString("cam", "auto") == "auto"
            val usb = wantUsb && try { provider.hasCamera(externalSelector()) } catch (e: Exception) { false }
            val cameraSel = if (usb) externalSelector() else CameraSelector.DEFAULT_BACK_CAMERA
            hfovDeg = (if (usb) externalHfov() else mainCameraHfov()) ?: if (usb) 60.0 else 70.0

            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(findViewById<PreviewView>(R.id.preview).surfaceProvider)
            }
            val selector = ResolutionSelector.Builder()
                .setResolutionStrategy(ResolutionStrategy(Size(1920, 1080), ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER))
                .setAspectRatioStrategy(AspectRatioStrategy.RATIO_16_9_FALLBACK_AUTO_STRATEGY)
                .build()
            val analysis = ImageAnalysis.Builder()
                .setResolutionSelector(selector)
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
                .build()
            analysis.setAnalyzer(cameraExecutor) { img -> analyze(img) }
            provider.unbindAll()
            camera = try {
                provider.bindToLifecycle(this, cameraSel, preview, analysis)
            } catch (e: Exception) {
                // Many USB cameras can't feed a preview and analysis at once: analysis only.
                try {
                    provider.unbindAll()
                    provider.bindToLifecycle(this, cameraSel, analysis)
                } catch (e2: Exception) {
                    null
                }
            }
            if (camera == null) {
                say(if (usb) "Couldn't start the USB camera." else "Couldn't start the camera.")
                if (usb) { prefs.edit().putString("cam", "phone").apply(); refreshLabels(); startCamera() }
                return@addListener
            }
            val changed = usb != usingUsb
            usingUsb = usb
            synchronized(lock) { lastFix = 0 }
            tracker?.reset()
            card?.reset()
            applyZoom()
            refreshLabels()
            if (changed) say(if (usb) "Using the USB camera" else "Using the phone camera")
        }, ContextCompat.getMainExecutor(this))
    }

    private fun hfovOf(id: String): Double? = try {
        val ch = cameraManager.getCameraCharacteristics(id)
        val w = ch.get(CameraCharacteristics.SENSOR_INFO_PHYSICAL_SIZE)!!.width.toDouble()
        val f = ch.get(CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS)!!.first().toDouble()
        Math.toDegrees(2 * atan(w / (2 * f))).takeIf { it in 5.0..170.0 }
    } catch (e: Exception) {
        null
    }

    private fun mainCameraHfov(): Double? = try {
        hfovOf(cameraManager.cameraIdList.first {
            cameraManager.getCameraCharacteristics(it).get(CameraCharacteristics.LENS_FACING) ==
                CameraCharacteristics.LENS_FACING_BACK
        })
    } catch (e: Exception) {
        null
    }

    /** USB cameras often don't report their optics; then a typical 60 degrees is assumed. */
    private fun externalHfov(): Double? = externalIds().firstOrNull()?.let { hfovOf(it) }

    private fun applyZoom() {
        val cam = camera ?: return
        val max = cam.cameraInfo.zoomState.value?.maxZoomRatio ?: 1f
        cam.cameraControl.setZoomRatio(minOf(zooms[idx("zoom")].toFloat(), max))
        synchronized(lock) { lastFix = 0 }
        tracker?.reset()
    }

    private var buf = ByteArray(0)
    @Volatile private var saveRequested = false

    private fun analyze(img: ImageProxy) {
        try {
            val f = toUprightGrey(img)
            val now = System.currentTimeMillis()
            if (saveRequested) {
                saveRequested = false
                val copy = Frame(f.data.copyOf(), f.w, f.h)
                modelExecutor.execute { savePicture(copy) }
            }
            val lf = lookForName()
            val wantCard = lf == CARD_OR_ANY || lf == CARD_ONLY
            if (wantCard && card == null && !cardFailed) {
                card = try { CardDetector() } catch (e: Throwable) {
                    cardFailed = true
                    runOnUiThread { say("Card detection isn't available on this phone.") }
                    null
                }
            }
            val det: Detection? = run {
                val c = if (wantCard) card?.detect(f) else null
                if (c != null) {
                    tracker?.reset() // the card is better: let the model rest
                    c
                } else if (lf != CARD_ONLY) {
                    tracker?.process(f, now).also { checkSpeed() }
                } else {
                    null
                }
            }
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
                    val h = det.cardH
                    if (h != null) {
                        // Where on the card does the aim point (the zero, or the
                        // middle of the picture before zeroing) fall?
                        val ax = f.w / 2.0 + fx * tan(Math.toRadians(zeroAz / 1000))
                        val ay = f.h / 2.0 - fx * tan(Math.toRadians(zeroEl / 1000))
                        val mm = CardGeometry.invert(h)?.let { CardGeometry.apply(it, ax, ay) }
                        zoneNow = mm?.let { CardGeometry.zone(it.first, it.second) }
                        cardRangeM = fx * CardGeometry.SIZE_MM / det.size / 1000
                    } else {
                        zoneNow = null
                        cardRangeM = null
                    }
                }
            }
            updateTone()
        } finally {
            img.close()
        }
    }

    /** Save exactly what the detector sees, so a failure can be diagnosed later. */
    private fun savePicture(f: Frame) {
        var uri: android.net.Uri? = null
        val ok = try {
            val px = IntArray(f.w * f.h) { i ->
                val v = f.data[i].toInt() and 0xFF
                (0xFF shl 24) or (v shl 16) or (v shl 8) or v
            }
            val bmp = android.graphics.Bitmap.createBitmap(px, f.w, f.h, android.graphics.Bitmap.Config.ARGB_8888)
            val name = "audiotarget-" + java.text.SimpleDateFormat("yyyyMMdd-HHmmss", java.util.Locale.US)
                .format(java.util.Date()) + ".png"
            val values = android.content.ContentValues().apply {
                put(android.provider.MediaStore.Images.Media.DISPLAY_NAME, name)
                put(android.provider.MediaStore.Images.Media.MIME_TYPE, "image/png")
                put(android.provider.MediaStore.Images.Media.RELATIVE_PATH, "Pictures/AudioTarget")
            }
            val u = contentResolver.insert(android.provider.MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
                ?: error("no uri")
            uri = u
            val written = contentResolver.openOutputStream(u)?.use {
                bmp.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it)
            } ?: false
            bmp.recycle()
            check(written) { "not written" }
            true
        } catch (e: Exception) {
            uri?.let { u -> runCatching { contentResolver.delete(u, null, null) } }
            false
        }
        runOnUiThread { say(if (ok) "Saved camera picture in Pictures, AudioTarget" else "Couldn't save the picture") }
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
        return when (if (usingUsb) 0 else img.imageInfo.rotationDegrees) {
            90 -> Frame(rotate(buf, w, h, 90), h, w)
            180 -> Frame(rotate(buf, w, h, 180), w, h)
            270 -> Frame(rotate(buf, w, h, 270), h, w)
            else -> Frame(buf, w, h)
        }
    }

    private var rbuf = ByteArray(0)

    // Reuses one buffer: everything that keeps a frame past this call copies it.
    private fun rotate(s: ByteArray, w: Int, h: Int, deg: Int): ByteArray {
        if (rbuf.size != w * h) rbuf = ByteArray(w * h)
        val d = rbuf
        when (deg) {
            90 -> for (y in 0 until h) for (x in 0 until w) d[x * h + (h - 1 - y)] = s[y * w + x]
            180 -> for (i in 0 until w * h) d[w * h - 1 - i] = s[i]
            270 -> for (y in 0 until h) for (x in 0 until w) d[(w - 1 - x) * h + y] = s[y * w + x]
        }
        return d
    }

    // ------------------------------------------------------------------ tilt (gravity)
    private val lowPass = DoubleArray(3)
    private var lowPassPrimed = false

    override fun onSensorChanged(e: SensorEvent) {
        var (gx, gy, gz) = Triple(e.values[0].toDouble(), e.values[1].toDouble(), e.values[2].toDouble())
        if (e.sensor.type == Sensor.TYPE_ACCELEROMETER) {
            // Raw accelerometer includes hand movement: smooth it to approximate gravity.
            if (!lowPassPrimed) { lowPass[0] = gx; lowPass[1] = gy; lowPass[2] = gz; lowPassPrimed = true }
            lowPass[0] += 0.1 * (gx - lowPass[0]); lowPass[1] += 0.1 * (gy - lowPass[1]); lowPass[2] += 0.1 * (gz - lowPass[2])
            gx = lowPass[0]; gy = lowPass[1]; gz = lowPass[2]
        }
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
        val ref = roll0 ?: when (displayRotation) {
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
                ToneMap.compute(cfg, (zeroEl - targetEl).toInt(), (zeroAz - targetAz).toInt(), true, false,
                    if (usingUsb) 0 else cantMdeg())
            } else {
                val p0 = if (tiltZeroed) pitch0 else 0.0
                // With a USB camera the phone's own tilt says nothing about aim:
                // just the "lost" beeps, at the on-target note.
                if (usingUsb) ToneMap.compute(cfg, 0, 0, false, lost, 0)
                else ToneMap.compute(cfg, (pitchMdeg - p0).toInt(), 0, false, lost, cantMdeg())
            }
            val zones = prefs.getBoolean("rings", true)
            if (cam && !hadTarget) {
                hadTarget = true
                spokenClass = lastClass
                pendingClass = -1
                spokenZone = zoneNow
                pendingZone = null
                announce = "${className(lastClass)} found" + if (zones && zoneNow != null) ", $zoneNow" else ""
            } else if (cam && lastClass != spokenClass) {
                // Locked onto a different kind of object: say so once it has held
                // for a moment, so a single doubtful detection doesn't chatter.
                if (lastClass != pendingClass) {
                    pendingClass = lastClass
                    pendingSince = now
                } else if (now - pendingSince > CLASS_CONFIRM_MS) {
                    spokenClass = lastClass
                    pendingClass = -1
                    announce = "Now on ${className(lastClass).lowercase()}"
                }
            } else if (!cam && hadTarget) {
                if (lostSince == 0L) lostSince = now
                if (now - lostSince > 1000) {
                    hadTarget = false
                    announce = "Target lost"
                }
            }
            if (cam) lostSince = 0L
            // Card area under the aim point: say it when it changes and holds briefly.
            val z = zoneNow
            if (zones && cam && announce == null && z != null && z != spokenZone) {
                if (z != pendingZone) {
                    pendingZone = z
                    pendingZoneSince = now
                } else if (now - pendingZoneSince > ZONE_CONFIRM_MS) {
                    spokenZone = z
                    pendingZone = null
                    announce = z.replaceFirstChar { it.uppercase() }
                }
            }
        }
        tone.tone = if (muted) Tone.SILENT else t
        val msg = announce
        if (msg != null && prefs.getBoolean("announce", true)) runOnUiThread { say(msg) }
    }

    private fun zero() {
        val camZero: Boolean
        var zeroedOn = "target"
        synchronized(lock) {
            camZero = System.currentTimeMillis() - lastFix < 300
            if (camZero) { zeroAz = targetAz; zeroEl = targetEl; zeroedOn = className(lastClass).lowercase() }
            pitch0 = pitchMdeg
            roll0 = rollDeg
            tiltZeroed = true
        }
        say(if (camZero) "Zeroed on $zeroedOn" else "Zeroed, tilt only")
    }

    private fun where() {
        val text = synchronized(lock) {
            if (System.currentTimeMillis() - lastFix >= 1000) "No target"
            else describeTarget(targetAz, targetEl, cardRangeM, className(lastClass)) +
                (zoneNow?.let { ". Aim point: $it" } ?: "")
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
        parts += (if (usingUsb) "USB camera" else "Phone camera") +
            if (phoneSupportsUsbCameras()) ", this phone supports USB cameras" else ", this phone doesn't offer USB cameras to apps"
        val (fw, fh) = synchronized(lock) { frameW to frameH }
        parts += "Camera %d by %d, %.0f frames per second, zoom %s, field of view %.0f degrees".format(
            fw, fh, fps, zoomName(), hfovDeg / zooms[idx("zoom")])
        val lf = lookForName()
        if (lf == CARD_OR_ANY || lf == CARD_ONLY) {
            parts += card?.seenSummary() ?: if (cardFailed) "Card detection unavailable" else "Card search starting"
        }
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
        const val BUILTIN_ASSET = "coco.onnx"       // 640 input
        const val BUILTIN_FAST = "coco320.onnx"     // 320 input, about 4x less work
        const val SLOW_MS = 250L                    // median ms per detection that counts as slow
        const val CLASS_CONFIRM_MS = 700L
        const val CARD_OR_ANY = "the card, or any object"
        const val CARD_ONLY = "the card only"
        const val ZONE_CONFIRM_MS = 400L

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
