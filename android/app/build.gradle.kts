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
        versionCode = 5
        versionName = "1.3.0"

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

        // Motor de avatar que este APK pede ao servidor: heygen (LiveAvatar)
        // ou bithuman. O motor roda no servidor, nao aqui; o app so diz qual
        // quer, e o token server despacha para o worker correspondente.
        //
        // Existe para o cliente comparar os dois lado a lado. Os dois APKs
        // recebem applicationId diferente de proposito, senao um substituiria
        // o outro no aparelho e a comparacao exigiria desinstalar e reinstalar
        // a cada troca.
        val motorAvatar = (project.findProperty("iara.avatarEngine") as String?) ?: "heygen"
        require(motorAvatar in listOf("heygen", "bithuman")) {
            "iara.avatarEngine deve ser heygen ou bithuman, veio: $motorAvatar"
        }
        buildConfigField("String", "AVATAR_ENGINE", "\"$motorAvatar\"")

        if (motorAvatar == "bithuman") {
            applicationIdSuffix = ".bithuman"
            resValue("string", "app_name", "IARA bitHuman")
        } else {
            resValue("string", "app_name", "IARA")
        }
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
        // Necessario para o resValue do nome do app por variante. No AGP 9
        // isto vem desligado por padrao e o build falha com
        // "defaultConfig contains custom resource values".
        resValues = true
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
