// 스페이스기전 교실 — 안드로이드(전자칠판)판. 빌드·올리기: deploy/classroom-android/build.py
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// 서명 — 키 파일과 암호는 deploy/classroom-android/build.py 가 환경 변수로 넘긴다(저장소에 두지 않는다)
val releaseKeystore: String? = System.getenv("CLASSROOM_KEYSTORE")

android {
    namespace = "kr.hs.kijun.classroom"
    compileSdk = 35

    defaultConfig {
        applicationId = "kr.hs.kijun.classroom"
        minSdk = 26
        targetSdk = 34
        // 🚨 새로 내보낼 때마다 둘 다 올린다 — 자동 업데이트가 versionCode 로 견준다
        versionCode = 13
        versionName = "1.3.3"
    }

    signingConfigs {
        if (releaseKeystore != null) {
            create("release") {
                storeFile = file(releaseKeystore)
                storePassword = System.getenv("CLASSROOM_KEYSTORE_PASSWORD")
                keyAlias = "classroom"
                keyPassword = System.getenv("CLASSROOM_KEYSTORE_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (releaseKeystore != null) signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        buildConfig = true
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
        unitTests.isIncludeAndroidResources = true
    }
    // Windows 교실판과 같은 글꼴·아이콘(app/web)을 빌드할 때 복사해 넣는다 — 한 곳에서만 고친다
    sourceSets["main"].assets.srcDir(layout.buildDirectory.dir("shared-assets"))
}

val copySharedWeb by tasks.registering(Copy::class) {
    from("../../app/web") {
        include("fonts/**", "fonts.css", "icons/**", "gtools.js", "gtools.css")
    }
    into(layout.buildDirectory.dir("shared-assets/web"))
}
tasks.named("preBuild") { dependsOn(copySharedWeb) }

dependencies {
    implementation("androidx.core:core:1.13.1")
    implementation("com.google.zxing:core:3.5.3")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
    // 앱을 JVM 에서 띄워 보는 시험(AppSmokeTest) — 에뮬레이터 없이 시작·화면·다리·브라우저가 죽지 않는지
    testImplementation("org.robolectric:robolectric:4.14.1")
}
