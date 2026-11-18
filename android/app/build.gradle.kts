plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "io.github.shuteye4220.audiotarget"
    compileSdk = 35
    ndkVersion = "27.2.12479018"

    defaultConfig {
        applicationId = "io.github.shuteye4220.audiotarget"
        minSdk = 29
        targetSdk = 35
        versionCode = 5
        versionName = "0.5-prototype"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        // Processor types to include. Phones from the last several years are all
        // arm64-v8a; x86_64 is for the CI emulators. The published APK is built
        // with -Pabis=arm64-v8a to keep the download small; add armeabi-v7a for
        // very old 32-bit phones.
        val abis = (project.findProperty("abis") as String?)?.split(",") ?: listOf("arm64-v8a", "x86_64")
        ndk {
            abiFilters += abis
        }
    }

    // One fixed key for every build, so a newer APK installs over an older one.
    // It's deliberately public (committed): fine for a camera-only prototype with
    // no internet permission, NOT for anything you'd publish to an app store.
    signingConfigs {
        create("prototype") {
            storeFile = rootProject.file("prototype.keystore")
            storePassword = "audiotarget-prototype"
            keyAlias = "prototype"
            keyPassword = "audiotarget-prototype"
        }
    }

    buildTypes {
        debug {
            signingConfig = signingConfigs.getByName("prototype")
        }
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("prototype")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    // USB camera driver (libusb + libuvc), for phones that don't offer USB cameras to apps.
    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }
    androidResources {
        noCompress += "onnx"
    }
    packaging {
        // Compress OpenCV / ONNX Runtime inside the APK: a much smaller download,
        // unpacked once at install.
        jniLibs {
            useLegacyPackaging = true
        }
    }
}

dependencies {
    val camerax = "1.4.2"
    implementation("androidx.camera:camera-core:$camerax")
    implementation("androidx.camera:camera-camera2:$camerax")
    implementation("androidx.camera:camera-lifecycle:$camerax")
    implementation("androidx.camera:camera-view:$camerax")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.core:core-ktx:1.13.1")
    // No Google Play services anywhere, so it runs on GrapheneOS as-is.
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.20.0")
    // ArUco markers on the printed card (same decoder the Pi uses).
    implementation("org.opencv:opencv:4.10.0")
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test:core:1.6.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test:rules:1.6.1")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
}

tasks.withType<Test> {
    testLogging {
        events("passed", "failed", "skipped")
        showStandardStreams = false
    }
}
