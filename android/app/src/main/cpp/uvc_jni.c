/*
 * USB (UVC) cameras without the phone's camera service.
 *
 * Many phones, Pixels among them, don't offer USB cameras to apps through
 * Camera2. Android's USB host API still lets an app open the device, so the
 * Kotlin side (UvcCamera.kt) gets permission, opens it and hands the file
 * descriptor here; libusb + libuvc do the streaming.
 *
 * Frames are kept "latest only": the stream callback copies each one into a
 * single buffer, and nativeGrab() hands the newest to Kotlin, as grey pixels
 * for raw formats or as JPEG bytes for MJPEG (decoded in Kotlin by OpenCV).
 */
#include <jni.h>
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <android/log.h>

#include "libusb.h"
#include "libuvc/libuvc.h"

#define TAG "AudioTargetUvc"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, TAG, __VA_ARGS__)
#define LOGW(...) __android_log_print(ANDROID_LOG_WARN, TAG, __VA_ARGS__)

/* Biggest frame we accept: 1920x1080 is the most the app asks for, so this is
 * generous room for MJPEG and raw formats alike. */
#define MAX_FRAME_BYTES (16u * 1024u * 1024u)
#define MAX_PIXELS (1920 * 1080)

enum { KIND_GREY = 0, KIND_JPEG = 1 };

typedef struct {
    libusb_context *usb;
    uvc_context_t *uvc;
    uvc_device_handle_t *devh;
    pthread_t events;
    int events_started;
    int stop_events; /* read by libusb in the event thread */
    int streaming;

    pthread_mutex_t mu;
    pthread_cond_t cv;
    uint8_t *data;
    size_t cap, len;
    int w, h;
    enum uvc_frame_format fmt;
    uint64_t seq, taken;
    int closing;

    char desc[96];
} cam_t;

static char g_error[160];

static void set_error(const char *what, int code) {
    snprintf(g_error, sizeof g_error, "%s: %s", what, uvc_strerror((uvc_error_t)code));
    LOGW("%s", g_error);
}

static void *event_loop(void *arg) {
    cam_t *c = arg;
    while (!__atomic_load_n(&c->stop_events, __ATOMIC_ACQUIRE)) {
        struct timeval tv = {0, 100000};
        libusb_handle_events_timeout_completed(c->usb, &tv, &c->stop_events);
    }
    return NULL;
}

static void on_frame(uvc_frame_t *f, void *user) {
    cam_t *c = user;
    if (!f->data || f->data_bytes == 0 || f->data_bytes > MAX_FRAME_BYTES) return;
    pthread_mutex_lock(&c->mu);
    if (f->data_bytes > c->cap) {
        uint8_t *n = realloc(c->data, f->data_bytes);
        if (!n) { pthread_mutex_unlock(&c->mu); return; }
        c->data = n;
        c->cap = f->data_bytes;
    }
    memcpy(c->data, f->data, f->data_bytes);
    c->len = f->data_bytes;
    c->w = (int)f->width;
    c->h = (int)f->height;
    c->fmt = f->frame_format;
    c->seq++;
    pthread_cond_signal(&c->cv);
    pthread_mutex_unlock(&c->mu);
}

static int supported(enum uvc_frame_format f) {
    switch (f) {
    case UVC_FRAME_FORMAT_MJPEG:
    case UVC_FRAME_FORMAT_YUYV:
    case UVC_FRAME_FORMAT_UYVY:
    case UVC_FRAME_FORMAT_NV12:
    case UVC_FRAME_FORMAT_NV21:
    case UVC_FRAME_FORMAT_I420:
    case UVC_FRAME_FORMAT_GRAY8:
        return 1;
    default:
        return 0;
    }
}

static const char *fmt_name(enum uvc_frame_format f) {
    switch (f) {
    case UVC_FRAME_FORMAT_MJPEG: return "MJPEG";
    case UVC_FRAME_FORMAT_YUYV: return "YUYV";
    case UVC_FRAME_FORMAT_UYVY: return "UYVY";
    case UVC_FRAME_FORMAT_NV12: return "NV12";
    case UVC_FRAME_FORMAT_NV21: return "NV21";
    case UVC_FRAME_FORMAT_I420: return "I420";
    case UVC_FRAME_FORMAT_GRAY8: return "grey";
    default: return "other";
    }
}

/* Interval (100 ns units) closest to 30 frames a second without going faster,
 * or the slowest on offer if every rate is faster; 0 if none. */
static uint32_t best_interval(const uvc_frame_desc_t *fr) {
    const uint32_t cap30 = 10000000u / 30u;
    uint32_t best = 0, slowest = 0;
    if (fr->intervals) {
        for (const uint32_t *i = fr->intervals; *i; ++i) {
            if (*i >= cap30 && (best == 0 || *i < best)) best = *i;
            if (*i > slowest) slowest = *i;
        }
        return best ? best : slowest;
    }
    if (fr->dwMinFrameInterval == 0) return 0;
    best = fr->dwMinFrameInterval < cap30 ? cap30 : fr->dwMinFrameInterval;
    return best <= fr->dwMaxFrameInterval ? best : fr->dwMinFrameInterval;
}

typedef struct {
    enum uvc_frame_format fmt;
    int w, h, fps;
    long long score;
} choice_t;

/*
 * Largest picture up to 1920x1080 that still runs at 10 frames a second or
 * more; MJPEG wins ties (raw formats usually only manage big frames slowly).
 */
static int choose_mode(uvc_device_handle_t *devh, choice_t *out) {
    int found = 0;
    for (const uvc_format_desc_t *fd = uvc_get_format_descs(devh); fd; fd = fd->next) {
        enum uvc_frame_format ff = uvc_frame_format_for_guid((uint8_t *)fd->guidFormat);
        if (!supported(ff)) continue;
        for (const uvc_frame_desc_t *fr = fd->frame_descs; fr; fr = fr->next) {
            long px = (long)fr->wWidth * fr->wHeight;
            if (px <= 0 || px > MAX_PIXELS) continue;
            uint32_t iv = best_interval(fr);
            if (!iv) continue;
            int fps = (int)(10000000u / iv);
            /* 10+ frames a second first, then size, then MJPEG. */
            long long score = (fps >= 10 ? (1LL << 40) : 0) + px * 2LL + (ff == UVC_FRAME_FORMAT_MJPEG ? 1 : 0);
            if (!found || score > out->score) {
                out->fmt = ff; out->w = fr->wWidth; out->h = fr->wHeight; out->fps = fps;
                out->score = score;
                found = 1;
            }
        }
    }
    return found;
}

static void destroy(cam_t *c) {
    if (c->streaming) uvc_stop_streaming(c->devh);
    if (c->devh) uvc_close(c->devh); /* needs the event thread to cancel transfers */
    if (c->events_started) {
        __atomic_store_n(&c->stop_events, 1, __ATOMIC_RELEASE);
        libusb_interrupt_event_handler(c->usb);
        pthread_join(c->events, NULL);
    }
    if (c->uvc) uvc_exit(c->uvc);
    if (c->usb) libusb_exit(c->usb);
    pthread_mutex_destroy(&c->mu);
    pthread_cond_destroy(&c->cv);
    free(c->data);
    free(c);
}

JNIEXPORT jlong JNICALL
Java_io_github_shuteye4220_audiotarget_UvcCamera_nativeOpen(JNIEnv *env, jclass cls, jint fd) {
    g_error[0] = 0;
    cam_t *c = calloc(1, sizeof *c);
    if (!c) return 0;
    pthread_mutex_init(&c->mu, NULL);
    pthread_condattr_t ca;
    pthread_condattr_init(&ca);
    pthread_condattr_setclock(&ca, CLOCK_MONOTONIC);
    pthread_cond_init(&c->cv, &ca);
    pthread_condattr_destroy(&ca);

    /* No device scanning: Android apps can't read /dev/bus/usb themselves. */
    libusb_set_option(NULL, LIBUSB_OPTION_NO_DEVICE_DISCOVERY);
    int r = libusb_init(&c->usb);
    if (r != 0) { set_error("libusb", r); c->usb = NULL; destroy(c); return 0; }
    r = uvc_init(&c->uvc, c->usb);
    if (r != UVC_SUCCESS) { set_error("init", r); c->uvc = NULL; destroy(c); return 0; }
    if (pthread_create(&c->events, NULL, event_loop, c) != 0) {
        snprintf(g_error, sizeof g_error, "event thread");
        destroy(c);
        return 0;
    }
    c->events_started = 1;

    r = uvc_wrap(fd, c->uvc, &c->devh);
    if (r != UVC_SUCCESS) { set_error("open", r); c->devh = NULL; destroy(c); return 0; }

    choice_t ch;
    if (!choose_mode(c->devh, &ch)) {
        snprintf(g_error, sizeof g_error, "no picture format the app can read");
        destroy(c);
        return 0;
    }
    uvc_stream_ctrl_t ctrl;
    r = uvc_get_stream_ctrl_format_size(c->devh, &ctrl, ch.fmt, ch.w, ch.h, ch.fps);
    if (r != UVC_SUCCESS) {
        /* Let the camera pick its own rate for that size. */
        r = uvc_get_stream_ctrl_format_size(c->devh, &ctrl, ch.fmt, ch.w, ch.h, 0);
    }
    if (r != UVC_SUCCESS) { set_error("format", r); destroy(c); return 0; }
    r = uvc_start_streaming(c->devh, &ctrl, on_frame, c, 0);
    if (r != UVC_SUCCESS) { set_error("stream", r); destroy(c); return 0; }
    c->streaming = 1;
    snprintf(c->desc, sizeof c->desc, "%s %d by %d, up to %d frames per second",
             fmt_name(ch.fmt), ch.w, ch.h, ch.fps);
    LOGI("streaming %s", c->desc);
    return (jlong)(intptr_t)c;
}

JNIEXPORT jstring JNICALL
Java_io_github_shuteye4220_audiotarget_UvcCamera_nativeLastError(JNIEnv *env, jclass cls) {
    return (*env)->NewStringUTF(env, g_error[0] ? g_error : "unknown error");
}

JNIEXPORT jstring JNICALL
Java_io_github_shuteye4220_audiotarget_UvcCamera_nativeDescribe(JNIEnv *env, jclass cls, jlong h) {
    cam_t *c = (cam_t *)(intptr_t)h;
    return (*env)->NewStringUTF(env, c ? c->desc : "");
}

/*
 * Waits up to timeoutMs for a frame newer than the last one taken.
 * Writes grey pixels (KIND_GREY, w*h bytes) or JPEG bytes (KIND_JPEG) into
 * out; info = {kind, w, h, bytes needed}.
 * Returns bytes written, 0 on timeout, -1 if out is too small (see info[3]),
 * -2 if the frame was unreadable, -3 if the camera is closing.
 */
JNIEXPORT jint JNICALL
Java_io_github_shuteye4220_audiotarget_UvcCamera_nativeGrab(
        JNIEnv *env, jclass cls, jlong h, jbyteArray out, jintArray info, jint timeoutMs) {
    cam_t *c = (cam_t *)(intptr_t)h;
    if (!c || (*env)->GetArrayLength(env, info) < 4) return -3;

    struct timespec dl;
    clock_gettime(CLOCK_MONOTONIC, &dl);
    dl.tv_sec += timeoutMs / 1000;
    dl.tv_nsec += (long)(timeoutMs % 1000) * 1000000L;
    if (dl.tv_nsec >= 1000000000L) { dl.tv_sec++; dl.tv_nsec -= 1000000000L; }

    pthread_mutex_lock(&c->mu);
    while (c->seq == c->taken && !c->closing) {
        if (pthread_cond_timedwait(&c->cv, &c->mu, &dl) == ETIMEDOUT) break;
    }
    if (c->closing) { pthread_mutex_unlock(&c->mu); return -3; }
    if (c->seq == c->taken) { pthread_mutex_unlock(&c->mu); return 0; }
    c->taken = c->seq;

    const int w = c->w, hh = c->h;
    const size_t px = (size_t)w * (size_t)hh;
    const int jpeg = c->fmt == UVC_FRAME_FORMAT_MJPEG;
    const size_t need = jpeg ? c->len : px;
    jint inf[4] = {jpeg ? KIND_JPEG : KIND_GREY, w, hh, (jint)need};
    (*env)->SetIntArrayRegion(env, info, 0, 4, inf);
    const size_t cap = (size_t)(*env)->GetArrayLength(env, out);
    if (need > cap) { pthread_mutex_unlock(&c->mu); return -1; }

    jint ret = (jint)need;
    jbyte *dst = (*env)->GetPrimitiveArrayCritical(env, out, NULL);
    if (!dst) { pthread_mutex_unlock(&c->mu); return -2; }
    const uint8_t *s = c->data;
    switch (c->fmt) {
    case UVC_FRAME_FORMAT_MJPEG:
        memcpy(dst, s, c->len);
        break;
    case UVC_FRAME_FORMAT_YUYV: /* Y U Y V: luma on even bytes */
    case UVC_FRAME_FORMAT_UYVY: /* U Y V Y: luma on odd bytes */
        if (c->len < px * 2) { ret = -2; break; }
        {
            const uint8_t *y = s + (c->fmt == UVC_FRAME_FORMAT_UYVY ? 1 : 0);
            for (size_t i = 0; i < px; ++i) dst[i] = (jbyte)y[i * 2];
        }
        break;
    default: /* NV12, NV21, I420, grey: a full-size luma plane first */
        if (c->len < px) { ret = -2; break; }
        memcpy(dst, s, px);
        break;
    }
    (*env)->ReleasePrimitiveArrayCritical(env, out, dst, ret > 0 ? 0 : JNI_ABORT);
    pthread_mutex_unlock(&c->mu);
    return ret;
}

JNIEXPORT void JNICALL
Java_io_github_shuteye4220_audiotarget_UvcCamera_nativeClose(JNIEnv *env, jclass cls, jlong h) {
    cam_t *c = (cam_t *)(intptr_t)h;
    if (!c) return;
    pthread_mutex_lock(&c->mu);
    c->closing = 1;
    pthread_cond_broadcast(&c->cv);
    pthread_mutex_unlock(&c->mu);
    destroy(c);
}
