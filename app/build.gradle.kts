plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.deviceagent"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.deviceagent"
        minSdk = 26
        targetSdk = 34
        versionCode = 7
        versionName = "0.6.1"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    // MQTT for heartbeat + command subscription (compatible with Solace broker)
    implementation("org.eclipse.paho:org.eclipse.paho.client.mqttv3:1.2.5")
}
