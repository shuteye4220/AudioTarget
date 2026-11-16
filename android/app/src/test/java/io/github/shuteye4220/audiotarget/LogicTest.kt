package io.github.shuteye4220.audiotarget

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs
import kotlin.math.hypot

class ToneMapTest {
    private val cfg = ToneCfg()

    @Test fun onTargetIsA440() {
        val t = ToneMap.compute(cfg, 0, 0, true, false, 0)
        assertEquals(440.0, t.freqHz, 0.01)
        assertEquals(1.0, t.gainL, 0.0)
        assertEquals(1.0, t.gainR, 0.0)
        assertEquals(0, t.flags)
    }

    @Test fun pitchAndClampAndQuantize() {
        assertEquals(880.0, ToneMap.compute(cfg, 1200, 0, false, false, 0).freqHz, 0.1)
        assertEquals(415.30, ToneMap.compute(cfg, -140, 0, false, false, 0).freqHz, 0.1)
        assertEquals(110.0, ToneMap.compute(cfg, -100000, 0, false, false, 0).freqHz, 0.1)
    }

    @Test fun louderEarIsTheTargetSide() {
        val t = ToneMap.compute(cfg, 0, 5000, true, false, 0) // aiming right: target to the left
        assertEquals(1.0, t.gainL, 0.0)
        assertEquals(cfg.minSideGain, t.gainR, 1e-9)
        val ignored = ToneMap.compute(cfg, 0, 5000, false, false, 0)
        assertEquals(1.0, ignored.gainR, 0.0)
    }

    @Test fun flagsAndGates() {
        val t = ToneMap.compute(cfg, 0, 0, false, true, -2500)
        assertEquals(ToneMap.FLAG_CANT or ToneMap.FLAG_LOST, t.flags)
        assertTrue(ToneMap.gateOn(ToneMap.FLAG_CANT, 10))
        assertTrue(!ToneMap.gateOn(ToneMap.FLAG_CANT, 70))
        assertTrue(ToneMap.gateOn(ToneMap.FLAG_LOST, 100))
        assertTrue(!ToneMap.gateOn(ToneMap.FLAG_LOST, 200))
    }

    @Test fun describe() {
        assertEquals("Target 1.2 degrees right, level, 12 metres", describeTarget(1234.0, -20.0, 12.4))
        assertEquals("Target 0.5 degrees left, 0.8 degrees up", describeTarget(-500.0, 800.0, null))
    }
}

class DecodeTest {
    @Test fun rawWithMaskCoefficients() {
        val nc = 3
        val n = 50
        val rows = 4 + nc + 32
        val d = FloatArray(rows * n)
        for (r in 4 + nc until rows) for (i in 0 until n) d[r * n + i] = 5f // big mask coefs, ignored
        d[0 * n + 9] = 10f; d[1 * n + 9] = 20f; d[2 * n + 9] = 30f; d[3 * n + 9] = 40f
        d[(4 + 1) * n + 9] = 0.7f
        val out = YoloDecode.decode(d, longArrayOf(1, rows.toLong(), n.toLong()), intArrayOf(0, 1, 2), 0.5f)
        assertArrayEquals(floatArrayOf(10f, 20f, 30f, 40f, 0.7f, 1f), out, 1e-6f)
        assertNull(YoloDecode.decode(d, longArrayOf(1, rows.toLong(), n.toLong()), intArrayOf(0, 1, 2), 0.8f))
    }

    @Test fun endToEnd() {
        val d = FloatArray(300 * 6)
        floatArrayOf(100f, 50f, 140f, 90f, 0.8f, 2f).copyInto(d, 4 * 6)
        floatArrayOf(0f, 0f, 10f, 10f, 0.9f, 7f).copyInto(d, 5 * 6)
        val out = YoloDecode.decode(d, longArrayOf(1, 300, 6), intArrayOf(2), 0.5f)
        assertArrayEquals(floatArrayOf(120f, 70f, 40f, 40f, 0.8f, 2f), out, 1e-6f)
        assertNull(YoloDecode.decode(d, longArrayOf(1, 300, 6), intArrayOf(3), 0.5f))
    }

    @Test fun onlyChosenClassesCount() {
        // 80-class raw output: a strong "chair" (56) and a weaker "person" (0) elsewhere.
        val n = 10
        val rows = 84
        val d = FloatArray(rows * n)
        d[(4 + 56) * n + 2] = 0.9f
        d[(4 + 0) * n + 7] = 0.6f
        val shape = longArrayOf(1, rows.toLong(), n.toLong())
        assertEquals(56f, YoloDecode.decode(d, shape, IntArray(80) { it }, 0.3f)!![5], 0f)
        val personOnly = YoloDecode.decode(d, shape, intArrayOf(0), 0.3f)!!
        assertEquals(0f, personOnly[5], 0f)
        assertEquals(0.6f, personOnly[4], 1e-6f)
    }

    @Test fun metadataNames() {
        val meta = "{0: 'bullseye', 1: 'shooting target', 2: 'round steel target'}"
        assertEquals(3, YoloDecode.classCount(meta))
        assertEquals(listOf("bullseye", "shooting target", "round steel target"), YoloDecode.classNames(meta))
        assertEquals(1, YoloDecode.classCount(null))
    }
}

/** Synthetic scene: a bullseye (dark rings on white) on grey, at a sub-pixel position. */
fun scene(w: Int, h: Int, cx: Double, cy: Double, r: Double, seed: Int = 0): Frame {
    val d = ByteArray(w * h)
    val rnd = java.util.Random(seed.toLong())
    for (y in 0 until h) for (x in 0 until w) {
        // 4x supersampling for smooth edges
        var acc = 0.0
        for (sy in 0 until 2) for (sx in 0 until 2) {
            val dx = x + (sx + 0.5) / 2 - cx
            val dy = y + (sy + 0.5) / 2 - cy
            val dist = hypot(dx, dy)
            acc += when {
                abs(dx) < r * 1.4 && abs(dy) < r * 1.4 && dist >= r -> 240.0 // white card
                dist < r -> if (((dist / r) * 10).toInt() % 2 == 0) 20.0 else 240.0 // rings
                else -> 140.0 // background
            }
        }
        val v = acc / 4 + rnd.nextGaussian() * 2
        d[y * w + x] = v.coerceIn(0.0, 255.0).toInt().toByte()
    }
    return Frame(d, w, h)
}

class TrackingTest {
    @Test fun templateFollowsMovingTarget() {
        val f0 = scene(400, 300, 200.3, 150.6, 40.0)
        val t = Template.cut(f0, 200.3, 150.6, 80.0)
        assertNotNull(t)
        var px = 200.3
        var py = 150.6
        for (k in 1..10) {
            val tx = 200.3 + k * 2.7
            val ty = 150.6 - k * 1.3
            val m = t!!.match(scene(400, 300, tx, ty, 40.0, seed = k), px, py)
            assertNotNull(m)
            assertTrue("score ${m!!.third}", m.third > 0.8)
            assertTrue("err ${hypot(m.first - tx, m.second - ty)}", hypot(m.first - tx, m.second - ty) < 1.0)
            px = m.first; py = m.second
        }
    }

    @Test fun flatPatchRefused() {
        val f = Frame(ByteArray(200 * 200) { 100 }, 200, 200)
        assertNull(Template.cut(f, 100.0, 100.0, 40.0))
    }

    @Test fun slowDetectorPlusTrackingFixesMostFrames() {
        var calls = 0
        val truth = HashMap<Int, Pair<Double, Double>>()
        val slow = SlowDetector { f ->
            calls++
            Thread.sleep(120) // a slow model
            val p = synchronized(truth) { truth.getValue(java.util.Arrays.hashCode(f.data)) }
            Detection(p.first, p.second, 80.0, 0.8)
        }
        val tr = MlTracker(slow)
        tr.refreshMs = 400
        var got = 0
        var maxErr = 0.0
        var now = 0L
        for (k in 0 until 40) {
            val tx = 180.0 + k * 0.8
            val ty = 140.0 + k * 0.3
            val f = scene(400, 300, tx, ty, 40.0, seed = k)
            synchronized(truth) { truth[java.util.Arrays.hashCode(f.data)] = tx to ty }
            val d = tr.process(f, now)
            if (d != null) {
                got++
                maxErr = maxOf(maxErr, hypot(d.x - tx, d.y - ty))
            }
            Thread.sleep(33)
            now += 33
        }
        tr.close()
        assertTrue("model ran $calls times", calls <= 8)
        assertTrue("fix in $got of 40 frames", got >= 30)
        assertTrue("max error $maxErr", maxErr < 1.5)
    }
}
