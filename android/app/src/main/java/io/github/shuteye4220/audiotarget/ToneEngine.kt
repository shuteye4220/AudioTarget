package io.github.shuteye4220.audiotarget

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import kotlin.math.PI
import kotlin.math.sin

/** Continuous stereo sine with click-free gain ramps, like the gun module's output. */
class ToneEngine {
    @Volatile var tone: Tone = Tone.SILENT
    @Volatile var volume = 0.5
    @Volatile private var running = false
    private var thread: Thread? = null

    fun start() {
        if (running) return
        running = true
        thread = Thread({ loop() }, "tone").apply { priority = Thread.MAX_PRIORITY; start() }
    }

    fun stop() {
        running = false
        thread?.join(500)
        thread = null
    }

    private fun loop() {
        // A phone with no usable audio output (or an emulator) mustn't crash the app.
        try {
            play()
        } catch (e: Exception) {
            running = false
        }
    }

    private fun play() {
        val rate = 48000
        val block = 256
        val minBuf = AudioTrack.getMinBufferSize(rate, AudioFormat.CHANNEL_OUT_STEREO, AudioFormat.ENCODING_PCM_FLOAT)
        val track = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setSampleRate(rate)
                    .setEncoding(AudioFormat.ENCODING_PCM_FLOAT)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_STEREO)
                    .build()
            )
            .setBufferSizeInBytes(maxOf(minBuf, block * 2 * 4 * 4))
            .setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()
        track.play()
        val buf = FloatArray(block * 2)
        var phase = 0.0
        var samples = 0L
        var curL = 0.0
        var curR = 0.0
        try {
            while (running) {
                val t = tone
                val tMs = samples * 1000 / rate
                val on = ToneMap.gateOn(t.flags, tMs)
                val v = volume
                val tgtL = if (on) t.gainL * v else 0.0
                val tgtR = if (on) t.gainR * v else 0.0
                val inc = 2 * PI * t.freqHz / rate
                for (i in 0 until block) {
                    val k = i.toDouble() / block
                    val s = sin(phase)
                    phase += inc
                    if (phase > 2 * PI) phase -= 2 * PI
                    buf[2 * i] = (s * (curL + (tgtL - curL) * k) * 0.8).toFloat()
                    buf[2 * i + 1] = (s * (curR + (tgtR - curR) * k) * 0.8).toFloat()
                }
                curL = tgtL
                curR = tgtR
                samples += block
                track.write(buf, 0, buf.size, AudioTrack.WRITE_BLOCKING)
            }
        } finally {
            track.stop()
            track.release()
        }
    }
}
