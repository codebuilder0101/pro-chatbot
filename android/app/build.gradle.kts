plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

android {
    namespace = "br.com.iara.chat"
    compileSdk = 37

    defaultConfig {
        applicationId = "br.com.iara.chat"
        minSdk = 26
        targetSdk = 37
        versionCode = 3
        versionName = "1.2.0"

        // Nao ha chave de API aqui, e nao pode haver. Um APK e descompilavel.
        // O unico segredo embarcado e a chave do proprio token server, que so
        // autoriza pedir um token de sala de escopo minimo e prazo curto.
        buildConfigField(
            "String",
            "TOKEN_SERVER_URL",
            "\"${project.findProperty("iara.tokenServerUrl") ?: "http://10.0.2.2:8080/"}\"",
        )
        buildConfigField(
            "String",
            "TOKEN_SERVER_KEY",
            "\"${project.findProperty("iara.tokenServerKey") ?: "troque-isto"}\"",
        )
    }

    signingConfigs {
        create("release") {
            val storePath = project.findProperty("iara.storeFile") as String?
            if (storePath != null) {
                storeFile = file(storePath)
                storePassword = project.findProperty("iara.storePassword") as String?
                keyAlias = project.findProperty("iara.keyAlias") as String?
                keyPassword = project.findProperty("iara.keyPassword") as String?
            }
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            if (project.hasProperty("iara.storeFile")) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    // APK universal (padrao) leva o WebRTC nativo das quatro arquiteturas e
    // passa de 65 MB. Com -Piara.abiSplit sai um APK por arquitetura: o de
    // arm64-v8a, que serve qualquer celular moderno, fica perto de 20 MB.
    //
    // Fica desligado por padrao para a entrega continuar sendo um arquivo so,
    // instalavel em qualquer aparelho de teste sem escolher variante.
    splits {
        abi {
            isEnable = project.hasProperty("iara.abiSplit")
            reset()
            include("arm64-v8a", "armeabi-v7a", "x86_64")
            isUniversalApk = false
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.kotlinx.coroutines.android)

    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons.extended)
    debugImplementation(libs.compose.ui.tooling)

    implementation(libs.livekit.android)

    implementation(libs.retrofit)
    implementation(libs.retrofit.serialization)
    implementation(libs.okhttp)
    implementation(libs.okhttp.logging)
    implementation(libs.kotlinx.serialization.json)
}
