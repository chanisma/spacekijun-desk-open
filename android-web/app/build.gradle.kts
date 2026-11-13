// 스페이스기전 웹앱 — 안드로이드 TWA(Chrome 이 띄우는 앱). 빌드: deploy/web-android/build.py · 상세: android-web/README.md
plugins {
    id("com.android.application")
}

// 서명 — 키 파일과 암호는 deploy/web-android/build.py 가 환경 변수로 넘긴다(저장소에 두지 않는다)
val releaseKeystore: String? = System.getenv("WEB_KEYSTORE")

android {
    namespace = "kr.hs.kijun.spacekijun"
    compileSdk = 35

    defaultConfig {
        applicationId = "kr.hs.kijun.spacekijun"
        minSdk = 23
        targetSdk = 35
        // 🚨 새로 내보낼 때마다 둘 다 올린다
        versionCode = 1
        versionName = "1.0.0"
        // 🚨 주소를 바꾸면 그 사이트의 /.well-known/assetlinks.json 도 있어야 주소창 없이 뜬다
        manifestPlaceholders["host"] = "spacekijun.lovable.app"
    }

    signingConfigs {
        if (releaseKeystore != null) {
            create("release") {
                storeFile = file(releaseKeystore)
                storePassword = System.getenv("WEB_KEYSTORE_PASSWORD")
                keyAlias = "spacekijun"
                keyPassword = System.getenv("WEB_KEYSTORE_PASSWORD")
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
}

dependencies {
    implementation("com.google.androidbrowserhelper:androidbrowserhelper:2.5.0")
}
