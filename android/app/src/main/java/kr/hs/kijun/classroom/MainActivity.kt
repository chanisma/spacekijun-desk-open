package kr.hs.kijun.classroom

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import org.json.JSONObject
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit

/**
 * 교실 화면 — QR · 수업 화면(타일) · 드라이브 탐색기 · 기기 설정. 화면은 앱 안 HTML(assets/web/board.*)이고
 * 그 HTML 은 Bridge 로만 이 앱을 부른다(Windows 판의 pywebview api 자리).
 */
class MainActivity : Activity() {
    companion object {
        private const val PICK_FILES = 11
        private const val PICK_TREE = 12
        const val PAGE = "file:///android_asset/web/board.html"
    }

    lateinit var web: WebView
    private var filesWaiting: CompletableFuture<List<Uri>>? = null
    private var treeWaiting: CompletableFuture<Uri?>? = null

    @SuppressLint("SetJavaScriptEnabled", "JavascriptInterface")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        web = WebView(this)
        web.setBackgroundColor(0xFFF4F6FB.toInt())
        setContentView(web)
        immersive()
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            textZoom = 100
            mediaPlaybackRequiresUserGesture = false
        }
        // 이 화면은 앱 안 HTML 만 연다 — 바깥 주소로 옮겨 가지 않는다(Bridge 를 바깥에 넘기지 않게)
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest) =
                !request.url.toString().startsWith("file:///android_asset/web/")
        }
        web.addJavascriptInterface(Bridge(this), "AndroidBridge")
        web.loadUrl(PAGE)
        classroom.startLoop()
    }

    private fun immersive() {
        if (Build.VERSION.SDK_INT >= 30) {
            window.insetsController?.let {
                it.hide(WindowInsets.Type.statusBars())
                it.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_FULLSCREEN or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        }
    }

    override fun onResume() {
        super.onResume()
        Bubble.hide(this)
        immersive()
        web.evaluateJavascript("window.onResumeApp && window.onResumeApp()", null)
    }

    /** 뒤로 — 화면(탐색기·창)이 먼저 받는다. QR·수업 화면에서는 앱을 끝내지 않는다(항상 켜져 있게) */
    @Deprecated("뒤로")
    override fun onBackPressed() {
        web.evaluateJavascript("window.onBack ? window.onBack() : false") { result ->
            if (result != "true") moveTaskToBack(true)
        }
    }

    /** 드라이브에 올릴 파일 고르기(여러 개) — 브리지 스레드에서 기다린다 */
    fun pickFiles(): List<Uri> {
        val future = CompletableFuture<List<Uri>>()
        runOnUiThread {
            filesWaiting?.complete(emptyList())
            filesWaiting = future
            runCatching {
                startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                    .setType("*/*").putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true), PICK_FILES)
            }.onFailure { future.complete(emptyList()) }
        }
        return runCatching { future.get(10, TimeUnit.MINUTES) }.getOrDefault(emptyList())
    }

    /** 기기에 저장할 폴더 고르기 */
    fun pickTree(): Uri? {
        val future = CompletableFuture<Uri?>()
        runOnUiThread {
            treeWaiting?.complete(null)
            treeWaiting = future
            runCatching { startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE), PICK_TREE) }
                .onFailure { future.complete(null) }
        }
        return runCatching { future.get(10, TimeUnit.MINUTES) }.getOrNull()
    }

    @Deprecated("Activity 결과")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        when (requestCode) {
            PICK_FILES -> {
                val uris = mutableListOf<Uri>()
                if (resultCode == RESULT_OK && data != null) {
                    data.clipData?.let { clip -> for (i in 0 until clip.itemCount) uris += clip.getItemAt(i).uri }
                    if (uris.isEmpty()) data.data?.let { uris += it }
                }
                filesWaiting?.complete(uris)
                filesWaiting = null
            }
            PICK_TREE -> {
                treeWaiting?.complete(if (resultCode == RESULT_OK) data?.data else null)
                treeWaiting = null
            }
            else -> super.onActivityResult(requestCode, resultCode, data)
        }
    }

    /** 브리지 결과를 화면에 돌려준다 */
    fun deliver(id: String, result: String) {
        runOnUiThread {
            if (isDestroyed) return@runOnUiThread
            web.evaluateJavascript("window.__bridgeDone && window.__bridgeDone(${JSONObject.quote(id)}, $result)", null)
        }
    }

    override fun onDestroy() {
        filesWaiting?.complete(emptyList())
        treeWaiting?.complete(null)
        web.destroy()
        super.onDestroy()
    }
}
