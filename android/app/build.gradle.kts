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
        versionCode = 1
        versionName = "0.1-prototype"
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
    testImplementation("junit:junit:4.13.2")
}

tasks.withType<Test> {
    testLogging {
        events("passed", "failed", "skipped")
        showStandardStreams = false
    }
}
