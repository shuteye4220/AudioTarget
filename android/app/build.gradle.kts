plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "io.github.shuteye4220.audiotarget"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.github.shuteye4220.audiotarget"
        minSdk = 29
        targetSdk = 35
        versionCode = 3
        versionName = "0.3-prototype"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        // 64-bit phones (and 32-bit ARM for older budget models), plus x86_64 for
        // the CI emulators. Leaving out 32-bit x86 keeps the APK smaller.
        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")
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
    androidResources {
        noCompress += "onnx"
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
