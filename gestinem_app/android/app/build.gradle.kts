import com.android.build.api.dsl.ApplicationExtension
import java.util.Properties
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

if (file("google-services.json").exists()) {
    apply(plugin = "com.google.gms.google-services")
}

val keystoreProperties = Properties()
val keystorePropertiesFile = rootProject.file("key.properties")
val isReleaseBuild = gradle.startParameter.taskNames.any {
    it.contains("release", ignoreCase = true)
}
if (keystorePropertiesFile.exists()) {
    keystorePropertiesFile.inputStream().use(keystoreProperties::load)
}

val requiredSigningProperties = listOf(
    "storePassword",
    "keyPassword",
    "keyAlias",
    "storeFile",
)
val missingSigningProperties = requiredSigningProperties.filter {
    keystoreProperties.getProperty(it).isNullOrBlank()
}

if (isReleaseBuild && (!keystorePropertiesFile.exists() || missingSigningProperties.isNotEmpty())) {
    throw GradleException(
        "No se puede generar una version release sin la clave de carga. " +
            "Copia android/key.properties.example como android/key.properties " +
            "y completa todas sus propiedades.",
    )
}

extensions.configure<ApplicationExtension>("android") {
    namespace = "es.gestinem.app"
    // flutter_secure_storage requiere actualmente compilar contra API 37.
    // targetSdk se mantiene gestionado por Flutter para no cambiar el comportamiento runtime.
    compileSdk = 37
    ndkVersion = flutter.ndkVersion

    compileOptions {
        isCoreLibraryDesugaringEnabled = true
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "es.gestinem.app"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    if (keystorePropertiesFile.exists()) {
        signingConfigs {
            create("release") {
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
                storeFile = file(keystoreProperties.getProperty("storeFile"))
                storePassword = keystoreProperties.getProperty("storePassword")
            }
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.findByName("release")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

flutter {
    source = "../.."
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.5")
}
