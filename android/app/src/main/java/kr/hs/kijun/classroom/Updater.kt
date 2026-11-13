package kr.hs.kijun.classroom

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * 자동 업데이트 — Supabase Storage `desk-releases/classroom-android/latest.json` 을 보고 새 판(versionCode 가 큰 것)을
 * 받아 둔다(SHA-256 확인). 설치는 안드로이드 설치 창이 떠야 해서 사람이 QR 화면의 [새 판 설치]를 누른다.
 * 위조는 안드로이드가 막는다 — 같은 서명 키로 서명한 APK 가 아니면 설치(덮어쓰기)가 거부된다.
 * 올리기: deploy/classroom-android/build.py
 */
class Updater(private val context: Context) {
    @Volatile var latest: JSONObject? = null; private set
    @Volatile var ready: File? = null; private set

    private val folder get() = File(context.cacheDir, "update")

    private fun get(url: String): ByteArray {
        val conn = URL(url).openConnection() as HttpURLConnection
        try {
            conn.connectTimeout = 15_000
            conn.readTimeout = 120_000
            conn.useCaches = false
            if (conn.responseCode != 200) throw IllegalStateException("새 판 정보를 받지 못했습니다(${conn.responseCode}).")
            return conn.inputStream.use { it.readBytes() }
        } finally {
            conn.disconnect()
        }
    }

    /** 새 판이 있으면 받아 둔다 → 받아 둔 새 판 정보(없으면 null) */
    fun checkAndDownload(): JSONObject? {
        val manifest = JSONObject(String(get("${Server.RELEASES}/latest.json?t=${System.currentTimeMillis()}")))
        latest = manifest
        if (manifest.optInt("versionCode") <= BuildConfig.VERSION_CODE) {
            ready = null
            folder.deleteRecursively()
            return null
        }
        val name = manifest.getString("file")
        require(Regex("^SpacekijunClassroom-[0-9.]+\\.apk$").matches(name)) { "새 판 파일 이름이 이상합니다." }
        val target = File(folder, name)
        if (target.exists() && sha256(target) == manifest.getString("sha256")) {
            ready = target
            return manifest
        }
        folder.deleteRecursively()
        folder.mkdirs()
        val bytes = get("${Server.RELEASES}/$name")
        val digest = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
        if (digest != manifest.getString("sha256")) throw IllegalStateException("받은 새 판이 목록과 다릅니다.")
        target.writeBytes(bytes)
        ready = target
        return manifest
    }

    private fun sha256(file: File) =
        MessageDigest.getInstance("SHA-256").digest(file.readBytes()).joinToString("") { "%02x".format(it) }

    /** 설치 창을 띄운다. 이 앱의 «알 수 없는 앱 설치» 허용이 없으면 그 설정 화면부터 → 안내 문구 */
    fun install(activity: Activity): String {
        val file = ready ?: return "받아 둔 새 판이 없습니다."
        if (Build.VERSION.SDK_INT >= 26 && !activity.packageManager.canRequestPackageInstalls()) {
            activity.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + activity.packageName)))
            return "«이 출처 허용»을 켠 뒤 [새 판 설치]를 다시 눌러 주세요."
        }
        val uri = FileProvider.getUriForFile(activity, activity.packageName + ".files", file)
        activity.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK))
        return "설치 창에서 [설치]를 누르고, 끝나면 [열기]를 눌러 주세요."
    }
}
