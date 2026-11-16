package io.github.shuteye4220.audiotarget

import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

fun interface SlowDetector {
    fun detect(f: Frame): Detection?
}

/**
 * Detect slowly, track quickly (same design as the Pi's ml_tracker.py).
 *
 * The model runs on a background thread on the newest frame, no more often
 * than [minIntervalMs] (to imitate a slower Pi). Each result becomes a
 * template that is followed in every frame by correlation. With
 * [trackBetween] off, only frames the model itself answered get a fix, which
 * shows what the tracking adds.
 */
class MlTracker(private val detector: SlowDetector) {
    @Volatile var minIntervalMs: Long = 0
    @Volatile var refreshMs: Long = 500
    @Volatile var trackBetween: Boolean = true

    private val worker = Executors.newSingleThreadExecutor { r -> Thread(r, "ml").apply { isDaemon = true } }
    private val busy = AtomicBoolean(false)
    private val result = AtomicReference<Pair<Frame, Detection?>?>(null)
    private var lastSubmit = 0L

    // Written by the camera thread, reset from the UI thread.
    @Volatile private var template: Template? = null
    @Volatile private var pos: Pair<Double, Double>? = null
    private var size = 0.0
    private var score = 0.0

    // Stats, read by the status announcement
    @Volatile var lastInferenceMs = 0L
        private set
    private val runTimes = ArrayDeque<Long>()
    val runsPerSecond: Double
        get() = synchronized(runTimes) {
            if (runTimes.size < 2) 0.0 else (runTimes.size - 1) * 1000.0 / (runTimes.last() - runTimes.first()).coerceAtLeast(1)
        }

    fun reset() {
        template = null
        pos = null
    }

    private fun submit(f: Frame, now: Long) {
        if (!busy.compareAndSet(false, true)) return
        lastSubmit = now
        val copy = Frame(f.data.copyOf(), f.w, f.h)
        try { worker.execute {
            val t0 = System.nanoTime()
            val det = try { detector.detect(copy) } catch (e: Exception) { null }
            lastInferenceMs = (System.nanoTime() - t0) / 1_000_000
            synchronized(runTimes) {
                runTimes.addLast(System.currentTimeMillis())
                while (runTimes.size > 20) runTimes.removeFirst()
            }
            result.set(copy to det)
            busy.set(false)
        } } catch (e: java.util.concurrent.RejectedExecutionException) {
            busy.set(false) // closed while a model swap was in progress
        }
    }

    /** Call for every camera frame. Returns the aim point, or null. */
    fun process(f: Frame, now: Long = System.currentTimeMillis()): Detection? {
        val r = result.getAndSet(null)
        var fresh: Detection? = null
        if (r != null) {
            val (frame, det) = r
            if (det != null) {
                val t = Template.cut(frame, det.x, det.y, det.size)
                if (t != null) {
                    template = t
                    pos = det.x to det.y
                    size = det.size
                    fresh = det
                }
            } else if (template == null) {
                reset()
            }
        }
        val due = now - lastSubmit >= maxOf(minIntervalMs, if (template == null) 0L else refreshMs)
        if (due) submit(f, now)

        if (!trackBetween) {
            // Model answers only, no tracking in between.
            if (fresh == null) reset()
            return fresh
        }
        val t = template ?: return null
        val p = pos ?: return null
        val m = t.match(f, p.first, p.second) ?: run { reset(); return null }
        if (m.third < MATCH_MIN) {
            reset()
            return null
        }
        pos = m.first to m.second
        score = m.third
        return Detection(m.first, m.second, size, score)
    }

    /** Stop the worker and wait for a running detection to finish. */
    fun close() {
        worker.shutdown()
        worker.awaitTermination(3, java.util.concurrent.TimeUnit.SECONDS)
    }

    companion object {
        const val MATCH_MIN = 0.6
    }
}
