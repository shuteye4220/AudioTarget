package io.github.shuteye4220.audiotarget

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import ai.onnxruntime.TensorInfo
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import kotlin.math.max
import kotlin.math.min

/**
 * YOLO / YOLOE ONNX model on ONNX Runtime (CPU with XNNPACK). No Play services.
 *
 * Like the Pi: looks first at a native-resolution square in the middle of the
 * frame (far targets stay sharp), and every fourth try at the whole frame.
 */
class OnnxDetector(modelPath: String, useXnnpack: Boolean) : SlowDetector, AutoCloseable {
    private val env = OrtEnvironment.getEnvironment()
    private val session: OrtSession
    private val inputName: String
    val size: Int
    val classNames: List<String>
    val classCount: Int
    /** Which classes count as a target (default: all). */
    @Volatile var classes: IntArray
    @Volatile var conf = 0.25f
    private var tries = 0
    private val input: FloatBuffer
    private lateinit var plane: FloatArray
    private var outBuf = FloatArray(0)  // model output, reused between detections

    init {
        val opts = OrtSession.SessionOptions()
        if (useXnnpack) {
            opts.addXnnpack(mapOf("intra_op_num_threads" to "4"))
            opts.setIntraOpNumThreads(1)
        } else {
            opts.setIntraOpNumThreads(4)
        }
        session = env.createSession(modelPath, opts)
        inputName = session.inputNames.first()
        val shape = (session.inputInfo.getValue(inputName).info as TensorInfo).shape
        size = shape.last().toInt().let { if (it > 0) it else 320 }
        val names = try { session.metadata.customMetadata["names"] } catch (e: Exception) { null }
        classNames = YoloDecode.classNames(names)
        classCount = YoloDecode.classCount(names)
        classes = IntArray(classCount) { it }
        input = ByteBuffer.allocateDirect(4 * 3 * size * size).order(ByteOrder.nativeOrder()).asFloatBuffer()
        plane = FloatArray(size * size)
    }

    override fun detect(f: Frame): Detection? {
        tries++
        val crop = min(f.w, f.h) > size && tries % FULL_FRAME_EVERY != 0
        val x0: Int
        val y0: Int
        val rw: Int
        val rh: Int
        if (crop) {
            x0 = (f.w - size) / 2; y0 = (f.h - size) / 2; rw = size; rh = size
        } else {
            x0 = 0; y0 = 0; rw = f.w; rh = f.h
        }
        // Letterbox the region into size x size, grey replicated to 3 channels.
        val scale = size.toDouble() / max(rw, rh)
        val nw = (rw * scale).toInt()
        val nh = (rh * scale).toInt()
        val left = (size - nw) / 2
        val top = (size - nh) / 2
        input.rewind()
        val tmp = plane
        tmp.fill(114f / 255f)
        for (y in 0 until nh) {
            val sy = y0 + min(rh - 1, (y / scale).toInt())
            val row = (top + y) * size + left
            for (x in 0 until nw) {
                val sx = x0 + min(rw - 1, (x / scale).toInt())
                tmp[row + x] = f.at(sx, sy) / 255f
            }
        }
        input.put(tmp); input.put(tmp); input.put(tmp)
        input.rewind()

        val best = OnnxTensor.createTensor(env, input, longArrayOf(1, 3, size.toLong(), size.toLong())).use { t ->
            session.run(mapOf(inputName to t)).use { res ->
                val out = res.get(0) as OnnxTensor
                val fb = out.floatBuffer
                val n = fb.remaining()
                if (outBuf.size != n) outBuf = FloatArray(n)
                fb.get(outBuf, 0, n)
                YoloDecode.decode(outBuf, out.info.shape, classes, conf)
            }
        } ?: return null

        val cx = (best[0] - left) / scale
        val cy = (best[1] - top) / scale
        val bw = best[2] / scale
        val bh = best[3] / scale
        if (crop && (cx - bw / 2 < 2 || cy - bh / 2 < 2 || cx + bw / 2 > size - 2 || cy + bh / 2 > size - 2)) {
            tries = FULL_FRAME_EVERY - 1 // cut off by the crop: look at the whole frame next
            return null
        }
        return Detection(cx + x0, cy + y0, max(bw, bh), best[4].toDouble(), best[5].toInt())
    }

    override fun close() {
        session.close()
    }

    companion object {
        const val FULL_FRAME_EVERY = 4
    }
}
