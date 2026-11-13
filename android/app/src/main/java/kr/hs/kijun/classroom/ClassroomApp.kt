package kr.hs.kijun.classroom

import android.app.Application
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.webkit.CookieManager
import android.webkit.WebStorage
import android.webkit.WebView
import android.webkit.WebViewDatabase
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

/**
 * 앱 하나에 하나 — 흐름(Controller)과 그 바퀴(loop), 화면 밖 일(AppHost). 화면(MainActivity)이 닫혀도 수업은 이어진다.
 */
open class ClassroomApp : Application() {
    lateinit var prefs: DevicePrefs
    lateinit var host: AppHost
    lateinit var controller: Controller
    lateinit var updater: Updater
    lateinit var link: LinkClient
    val executor: ExecutorService = Executors.newFixedThreadPool(4)
    private var loop: Thread? = null

    val sessionsDir: File get() = File(filesDir, "sessions")

    /** 앱 안 브라우저 프로세스(:web)인가 */
    val isWebProcess: Boolean by lazy { processName().endsWith(":web") }

    private fun processName(): String = if (android.os.Build.VERSION.SDK_INT >= 28) Application.getProcessName()
        else runCatching { File("/proc/self/cmdline").readText().trim('\u0000', ' ', '\n') }.getOrDefault(packageName)

    override fun onCreate() {
        super.onCreate()
        if (isWebProcess) {
            // 브라우저 프로세스 — 자기 웹 데이터 폴더(app_webview_web)를 쓰고, 수업 흐름은 돌리지 않는다
            if (android.os.Build.VERSION.SDK_INT >= 28) runCatching { android.webkit.WebView.setDataDirectorySuffix(WebVault.SUFFIX) }
            androidx.core.content.ContextCompat.registerReceiver(this, object : android.content.BroadcastReceiver() {
                override fun onReceive(context: android.content.Context, intent: Intent) {
                    // 수업이 끝난다 — 쿠키를 디스크에 쓰고 창을 닫고 프로세스를 끝낸다(메인이 폴더를 묶거나 지운다)
                    runCatching { android.webkit.CookieManager.getInstance().flush() }
                    BrowserActivity.finishAll()
                    Handler(Looper.getMainLooper()).postDelayed({ android.os.Process.killProcess(android.os.Process.myPid()) }, 400)
                }
            }, android.content.IntentFilter(AppHost.ACTION_CLOSE_WEB), androidx.core.content.ContextCompat.RECEIVER_NOT_EXPORTED)
            return
        }
        prefs = DevicePrefs(this)
        host = AppHost(this)
        updater = Updater(this)
        sweepLeftovers()
        val client = LinkClient(DeviceKey.get(this))
        link = client
        controller = Controller(
            client, { prefs.name },
            { handoff -> Session(handoff, host, sessionsDir, UnsentBox(File(filesDir, "unsent"))) },
            onFinished = { host.bringToFront() },
        )
    }

    /** 지난번에 앱이 갑자기 끝났다면(수업 중 강제 종료 등) 남은 수업 폴더·로그인을 지운다 */
    private fun sweepLeftovers() {
        sessionsDir.deleteRecursively()
        File(filesDir, "handoff").deleteRecursively()
        runCatching { host.wipeWebData() }
        runCatching { host.finishWeb(null) }        // 앱 안 브라우저 데이터도(보관하지 않고)
        runCatching { host.vault.sweep() }
    }

    /** 흐름을 돌린다(한 번만) — QR 만들기·승인 묻기·수업 시간 지키기·드라이브 되올리기 */
    open fun startLoop() {
        if (loop != null) return
        loop = thread(isDaemon = true, name = "classroom-loop") {
            var nextUpdateCheck = System.currentTimeMillis() + 90_000
            while (true) {
                val delay = runCatching { controller.step() }.getOrDefault(2.0)
                // 새 판: 켜고 90초 뒤, 그 뒤 30분마다 — 받아만 두고 설치는 QR 화면의 단추로(설치 창은 사람이 눌러야 한다)
                if (System.currentTimeMillis() >= nextUpdateCheck && controller.phase == "qr") {
                    nextUpdateCheck = System.currentTimeMillis() + 30 * 60_000L
                    runCatching { updater.checkAndDownload() }
                }
                Thread.sleep((delay * 1000).toLong().coerceIn(200, 15_000))
            }
        }
    }
}

/** 메인 스레드에서 돌리고 결과를 기다린다(바퀴·브리지 스레드에서 화면을 건드릴 때) */
fun <T> onMain(block: () -> T): T {
    if (Looper.myLooper() == Looper.getMainLooper()) return block()
    var result: Result<T>? = null
    val latch = CountDownLatch(1)
    Handler(Looper.getMainLooper()).post {
        result = runCatching(block)
        latch.countDown()
    }
    latch.await(20, TimeUnit.SECONDS)
    return (result ?: Result.failure(IllegalStateException("화면이 응답하지 않습니다."))).getOrThrow()
}

class AppHost(private val app: ClassroomApp) : Host {
    companion object {
        const val ACTION_CLOSE_WEB = "kr.hs.kijun.classroom.CLOSE_WEB"
    }

    val vault = WebVault(File(app.applicationInfo.dataDir), app.cacheDir, File(app.filesDir, "vault"))
    /** 로그인 보관은 안드로이드 9+ (웹 데이터 폴더를 프로세스마다 따로 쓸 수 있어야 한다) */
    val vaultSupported = android.os.Build.VERSION.SDK_INT >= 28

    private fun webPid(): Int? = (app.getSystemService(Context.ACTIVITY_SERVICE) as android.app.ActivityManager)
        .runningAppProcesses?.firstOrNull { it.processName == app.packageName + ":web" }?.pid

    /** 앱 안 브라우저를 닫는다 — 쿠키를 쓰게 하고 기다렸다가, 남아 있으면 끝낸다(바퀴 스레드에서) */
    fun closeWebProcess() {
        if (webPid() == null) return
        app.sendBroadcast(Intent(ACTION_CLOSE_WEB).setPackage(app.packageName))
        val deadline = System.currentTimeMillis() + 2500
        while (webPid() != null && System.currentTimeMillis() < deadline) Thread.sleep(150)
        webPid()?.let { android.os.Process.killProcess(it) }
        Thread.sleep(200)
    }

    /** 수업 시작 — 앱 안 브라우저를 비우고, 보관 열쇠가 있으면 그 선생님 로그인을 풀어 넣는다 → 풀었으면 true */
    override fun prepareWeb(profile: JSONObject?): Boolean {
        closeWebProcess()
        if (!vaultSupported) { runCatching { onMain { wipeWebData() } }; return false }
        vault.wipe()
        val ref = profile?.str("ref").orEmpty()
        val key = profile?.str("key").orEmpty()
        return ref.isNotEmpty() && key.isNotEmpty() && runCatching { vault.restore(ref, key) }.getOrDefault(false)
    }

    /** 수업 끝 — 앱 안 브라우저를 닫고, 열쇠가 있으면 로그인을 잠가 남긴 뒤 비운다 */
    override fun finishWeb(profile: JSONObject?) {
        closeWebProcess()
        if (!vaultSupported) { runCatching { onMain { wipeWebData() } }; return }
        val ref = profile?.str("ref").orEmpty()
        val key = profile?.str("key").orEmpty()
        if (ref.isNotEmpty() && key.isNotEmpty() && vault.live.exists()) runCatching { vault.save(ref, key) }
        vault.wipe()
    }

    /** 이 칠판의 로그인 보관 지우기 — 보관 파일과 지금 브라우저 데이터를 지운다 */
    override fun forgetWeb(ref: String?) {
        closeWebProcess()
        ref?.let { vault.forget(it) }
        if (vaultSupported) vault.wipe() else runCatching { onMain { wipeWebData() } }
    }

    override fun webVaultSupported() = vaultSupported

    override fun webGoogleLogin(): Boolean? = if (vaultSupported) vault.googleLoginIn() else null

    override fun openWeb(url: String, title: String, space: JSONObject?) {
        // 앱 안 브라우저는 다른 프로세스(:web) — 수업 코드·이메일(휴대폰으로 입력용)을 넘긴다
        val session = app.controller.session as? Session
        onMain {
            val intent = Intent(app, BrowserActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                .putExtra(BrowserActivity.EXTRA_URL, url)
                .putExtra(BrowserActivity.EXTRA_TITLE, title)
                .putExtra(BrowserActivity.EXTRA_SESSION_CODE, app.controller.sessionCode)
                .putExtra(BrowserActivity.EXTRA_EMAIL, session?.email)
            // 스페이스기전 로그인은 화면 전달(Intent)에 싣지 않고 앱 전용 파일로 맡긴다(브라우저가 읽고 지운다)
            if (space != null) intent.putExtra(BrowserActivity.EXTRA_SPACE, BrowserActivity.holdSpace(app, space))
            app.startActivity(intent)
        }
    }

    private fun programIntent(key: String): Intent? {
        val candidates = Programs.KNOWN[key]?.second ?: return null
        val pm = app.packageManager
        candidates.firstNotNullOfOrNull { pm.getLaunchIntentForPackage(it) }?.let { return it }
        if (key == "calculator") {
            return Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_CALCULATOR)
                .takeIf { it.resolveActivity(pm) != null }
        }
        return null
    }

    override fun hasProgram(key: String) = programIntent(key) != null

    override fun launchProgram(key: String): String? {
        val label = Programs.label(key)
        val candidates = Programs.KNOWN[key]?.second ?: return "이 기기에서 열 수 없는 프로그램입니다($label)."
        val intent = programIntent(key)
        if (intent == null) {
            return if (candidates.isEmpty()) "«$label»은(는) Windows 프로그램이라 전자칠판에는 없습니다."
            else "이 칠판에 «$label» 앱이 없습니다. 관리자에게 설치를 부탁해 주세요."
        }
        return try {
            onMain {
                app.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                Bubble.show(app)
            }
            null
        } catch (e: ActivityNotFoundException) {
            "«$label» 앱을 열지 못했습니다."
        }
    }

    override fun launch(file: File, mime: String) {
        val uri = FileProvider.getUriForFile(app, app.packageName + ".files", file)
        val intent = Intent(Intent.ACTION_VIEW).setDataAndType(uri, mime)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        if (intent.resolveActivity(app.packageManager) == null) {
            throw DriveError("이 파일(.${file.extension})을 열 앱이 칠판에 없습니다.")
        }
        onMain {
            app.startActivity(intent)
            Bubble.show(app)
        }
    }

    override fun clearWeb() {
        closeWebProcess()
        runCatching { onMain { wipeWebData() } }
    }

    /** 앱 안 브라우저의 쿠키·저장소·캐시·폼 기록을 지운다(메인 스레드) */
    fun wipeWebData() {
        val cookies = CookieManager.getInstance()
        cookies.removeAllCookies(null)
        cookies.flush()
        WebStorage.getInstance().deleteAllData()
        WebViewDatabase.getInstance(app).clearHttpAuthUsernamePassword()
        WebView(app).apply {
            clearCache(true)
            clearFormData()
            clearHistory()
            destroy()
        }
    }

    /** 정리가 끝나면 QR 화면을 앞으로(다른 앱 위에 표시가 허용된 기기에서만 된다) */
    fun bringToFront() {
        runCatching {
            onMain {
                Bubble.hide(app)
                app.startActivity(Intent(app, MainActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT))
            }
        }
    }
}

val Context.classroom: ClassroomApp get() = applicationContext as ClassroomApp
