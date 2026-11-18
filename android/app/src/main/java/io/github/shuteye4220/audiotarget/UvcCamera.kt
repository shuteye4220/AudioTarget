package io.github.shuteye4220.audiotarget

import android.hardware.usb.UsbConstants
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbDeviceConnection
import android.hardware.usb.UsbManager
import org.opencv.android.OpenCVLoader
import org.opencv.core.CvType
import org.opencv.core.Mat
import org.opencv.imgcodecs.Imgcodecs
import java.io.IOException

/**
 * A USB (UVC) camera opened directly through Android's USB host API, for phones
 * whose camera service doesn't offer USB cameras to apps (Pixels among them).
 * The streaming is done by libusb + libuvc in native code (cpp/uvc_jni.c);
 * this class hands out frames as grey [Frame]s.
 *
 * Not thread-safe: one thread grabs, then closes.
 */
class UvcCamera private constructor(
    private val conn: UsbDeviceConnection,
    private val handle: Long,
    /** For Status, e.g. "MJPEG 1920 by 1080, up to 30 frames per second". */
    val description: String,
) : AutoCloseable {
    private var raw = ByteArray(1920 * 1080)
    private val info = IntArray(4)
    private var grey = ByteArray(0)
    private var closed = false

    /** Count of frames that couldn't be decoded, for diagnosis. */
    var badFrames = 0
        private set

    /** The next new frame, or null if none came within [timeoutMs]. */
    fun grab(timeoutMs: Int): Frame? {
        check(!closed)
        val n = nativeGrab(handle, raw, info, timeoutMs)
        when {
            n == -1 -> { raw = ByteArray(info[3]); return null } // fits from the next frame on
            n == -3 -> throw IOException("USB camera closed")
            n <= 0 -> { if (n == -2) badFrames++; return null }
        }
        val w = info[1]
        val h = info[2]
        return if (info[0] == KIND_GREY) {
            if (grey.size != w * h) grey = ByteArray(w * h)
            System.arraycopy(raw, 0, grey, 0, w * h)
            Frame(grey, w, h)
        } else {
            decodeJpeg(n)
        }
    }

    private fun decodeJpeg(n: Int): Frame? {
        val m = Mat(1, n, CvType.CV_8UC1)
        val g: Mat
        try {
            m.put(0, 0, raw, 0, n)
            // Cameras often leave out the standard Huffman tables; OpenCV's
            // libjpeg-turbo fills them in.
            g = Imgcodecs.imdecode(m, Imgcodecs.IMREAD_GRAYSCALE)
        } finally {
            m.release()
        }
        try {
            if (g.empty() || g.type() != CvType.CV_8UC1) { badFrames++; return null }
            val w = g.cols()
            val h = g.rows()
            if (grey.size != w * h) grey = ByteArray(w * h)
            g.get(0, 0, grey)
            return Frame(grey, w, h)
        } finally {
            g.release()
        }
    }

    override fun close() {
        if (closed) return
        closed = true
        nativeClose(handle)
        conn.close()
    }

    companion object {
        private const val KIND_GREY = 0

        private val loaded: Boolean by lazy {
            try {
                System.loadLibrary("audiotarget_uvc")
                OpenCVLoader.initLocal()
            } catch (e: Throwable) {
                false
            }
        }

        fun isCamera(d: UsbDevice): Boolean =
            (0 until d.interfaceCount).any { d.getInterface(it).interfaceClass == UsbConstants.USB_CLASS_VIDEO }

        fun find(um: UsbManager?): UsbDevice? = um?.deviceList?.values?.firstOrNull { isCamera(it) }

        /** Opens and starts streaming; the app must already have USB permission for [d]. */
        fun open(um: UsbManager, d: UsbDevice): UvcCamera {
            if (!loaded) throw IOException("the USB camera driver didn't load")
            val conn = um.openDevice(d) ?: throw IOException("Android wouldn't open it")
            try {
                // Take the video interfaces from any kernel driver first; libusb
                // then finds them already ours on the same connection.
                for (i in 0 until d.interfaceCount) {
                    val intf = d.getInterface(i)
                    if (intf.interfaceClass == UsbConstants.USB_CLASS_VIDEO) conn.claimInterface(intf, true)
                }
                val h = nativeOpen(conn.fileDescriptor)
                if (h == 0L) throw IOException(nativeLastError())
                return UvcCamera(conn, h, nativeDescribe(h))
            } catch (e: Throwable) {
                conn.close()
                throw e
            }
        }

        @JvmStatic private external fun nativeOpen(fd: Int): Long
        @JvmStatic private external fun nativeLastError(): String
        @JvmStatic private external fun nativeDescribe(handle: Long): String
        @JvmStatic private external fun nativeGrab(handle: Long, out: ByteArray, info: IntArray, timeoutMs: Int): Int
        @JvmStatic private external fun nativeClose(handle: Long)
    }
}
