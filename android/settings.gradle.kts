pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        // O livekit-android depende de com.github.davidliu:audioswitch, que
        // so existe no JitPack. Escopado para o grupo, para nao abrir o
        // JitPack inteiro como fonte de dependencia do projeto.
        maven {
            url = uri("https://jitpack.io")
            content { includeGroup("com.github.davidliu") }
        }
    }
}

rootProject.name = "IARA"
include(":app")
