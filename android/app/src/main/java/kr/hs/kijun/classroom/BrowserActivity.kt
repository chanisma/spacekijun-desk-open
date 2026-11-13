package kr.hs.kijun.classroom

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.webkit.CookieManager
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import org.json.JSONObject
import java.lang.ref.WeakReference
import java.util.UUID

/**
 * 앱 안 브라우저 — 세팅의 웹사이트·구글 앱·스페이스기전 화면. 아래에 ← → ⟳ · 제목 · [수업 화면].
 * 수업이 끝나면 모두 닫고 쿠키·저장소·캐시를 지운다(AppHost.clearWeb) — 누가 로그인해도 다음 수업에 남지 않는다.
 *
 * 🚨 구글은 앱 안 브라우저(WebView)의 로그인을 막을 때가 있다. 사용자 에이전트를 일반 Chrome 처럼 바꿔 두었지만
 *    막히면 이 기기에서는 구글 웹 로그인이 안 된다(드라이브는 앱 안 탐색기로 쓴다 — QR 승인 때 받은 토큰).
 */
class BrowserActivity : Activity() {
    companion object {
        const val EXTRA_URL = "url"
        const val EXTRA_TITLE = "title"
        const val EXTRA_SPACE = "space"
        const val EXTRA_SESSION_CODE = "session_code"
        const val EXTRA_EMAIL = "email"
        private const val PICK = 41

        private val open = mutableListOf<WeakReference<BrowserActivity>>()

        /**
         * 스페이스기전 로그인을 앱 전용 파일로 맡기고 표를 돌려준다 — 브라우저는 다른 프로세스(:web)라 메모리로 넘길 수 없고,
         * 화면 전달(Intent)에는 토큰을 싣지 않는다. 브라우저가 읽자마자 지운다(남은 것은 앱을 켤 때 지운다).
         */
        fun holdSpace(context: android.content.Context, session: JSONObject): String {
            val ticket = UUID.randomUUID().toString()
            val dir = java.io.File(context.filesDir, "handoff").apply { mkdirs() }
            java.io.File(dir, "$ticket.json").writeText(session.toString())
            return ticket
        }

        private fun takeSpace(context: android.content.Context, ticket: String?): JSONObject? {
            if (ticket == null || !Regex("^[0-9a-f-]{36}$").matches(ticket)) return null
            val file = java.io.File(java.io.File(context.filesDir, "handoff"), "$ticket.json")
            return runCatching { JSONObject(file.readText()) }.getOrNull().also { file.delete() }
        }

        fun finishAll() {
            val list = synchronized(open) { open.mapNotNull { it.get() }.also { open.clear() } }
            for (activity in list) activity.closeNow()
        }

        /** app/core/web_login.py install_script 와 같다 — 스페이스기전 웹이 로그인된 것으로 본다 */
        fun installScript(session: JSONObject): String {
            val payload = JSONObject().put("origin", Server.WEB).put("key", Server.STORAGE_KEY)
                .put("owner", Server.OWNER_KEY).put("session", session)
            return """(() => {
              const p = $payload;
              if (location.origin !== p.origin) return false;
              localStorage.setItem(p.key, JSON.stringify(p.session));
              const claims = JSON.parse(atob(p.session.access_token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
              localStorage.setItem(p.owner, p.session.user.id + '|' + claims.session_id);
              localStorage.setItem('auth_login_timestamp', String(Date.now()));
              if (localStorage.getItem('spacekijun_personal_device_user') !== p.session.user.id)
                localStorage.removeItem('spacekijun_personal_device_user');
              return true;
            })()"""
        }
    }

    private lateinit var web: WebView
    private lateinit var titleView: TextView
    private var space: JSONObject? = null
    private var installed = false
    private var target = ""
    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private var fullscreen: View? = null
    private var closed = false
    private lateinit var phoneButton: Button
    @Volatile private var typing: android.app.Dialog? = null
    private lateinit var modeButton: Button
    private var mobileUa = ""
    private var desktop = true
    private val prefs by lazy { getSharedPreferences("browser", MODE_PRIVATE) }

    private fun dp(v: Float) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, resources.displayMetrics).toInt()

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        synchronized(open) { open += WeakReference(this) }
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        target = intent.getStringExtra(EXTRA_URL).orEmpty()
        space = takeSpace(this, intent.getStringExtra(EXTRA_SPACE))

        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(Color.WHITE) }
        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(8f), dp(8f), dp(10f), dp(12f))
            setBackgroundColor(0xFFF4F6FB.toInt())
        }
        fun tool(text: String, description: String, action: () -> Unit) = Button(this).apply {
            this.text = text
            contentDescription = description
            textSize = 20f
            setTextColor(0xFF334155.toInt())
            background = null
            minWidth = dp(56f)
            minimumWidth = dp(56f)
            setOnClickListener { action() }
        }
        bar.addView(tool("←", "뒤로") { if (web.canGoBack()) web.goBack() else finish() })
        bar.addView(tool("→", "앞으로") { if (web.canGoForward()) web.goForward() })
        bar.addView(tool("⟳", "새로고침") { web.reload() })
        modeButton = tool("", "PC 화면 / 모바일 화면") {
            applyMode(!desktop)
            prefs.edit().putBoolean("desktop", desktop).apply()
            web.reload()
        }.apply { textSize = 15f; isAllCaps = false }
        bar.addView(modeButton)
        // 구글 로그인 화면일 때만 — 칠판에서 비밀번호를 치지 않게 휴대폰에서 넣는다(TypeRelay.kt)
        phoneButton = Button(this).apply {
            text = "📱 휴대폰으로 입력"
            textSize = 15f
            isAllCaps = false
            setTextColor(Color.WHITE)
            background = GradientDrawable().apply { setColor(0xFF1A73E8.toInt()); cornerRadius = dp(10f).toFloat() }
            setPadding(dp(14f), 0, dp(14f), 0)
            visibility = View.GONE
            setOnClickListener { startPhoneTyping() }
        }
        bar.addView(phoneButton, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(48f)).apply { marginEnd = dp(8f) })
        titleView = TextView(this).apply {
            text = intent.getStringExtra(EXTRA_TITLE).orEmpty()
            textSize = 17f
            setTextColor(0xFF1E293B.toInt())
            typeface = Typeface.DEFAULT_BOLD
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
            setPadding(dp(8f), 0, dp(8f), 0)
        }
        bar.addView(titleView, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        bar.addView(Button(this).apply {
            text = "수업 화면"
            textSize = 16f
            setTextColor(Color.WHITE)
            isAllCaps = false
            background = GradientDrawable().apply { setColor(0xFF4F46E5.toInt()); cornerRadius = dp(10f).toFloat() }
            setPadding(dp(18f), 0, dp(18f), 0)
            setOnClickListener {
                startActivity(Intent(this@BrowserActivity, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT))
            }
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(48f)))
        // 도구 줄은 아래에 — 큰 칠판에서 위쪽 단추는 손이 닿기 어렵다(2026-10-14 요청)
        web = WebView(this)
        root.addView(web, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        root.addView(android.view.View(this).apply { setBackgroundColor(0xFFE3E7F0.toInt()) },
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 1))
        root.addView(bar, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        setContentView(root)

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, true)
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            mediaPlaybackRequiresUserGesture = false
            builtInZoomControls = true
            displayZoomControls = false
            useWideViewPort = true
            loadWithOverviewMode = true
            setSupportMultipleWindows(false)
            allowFileAccess = false
            textZoom = 100
            // https 페이지 안의 http 그림·글꼴(학교 사이트에 흔하다)이 빠지지 않게
            mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
        }
        mobileUa = web.settings.userAgentString.replace("; wv)", ")").replace(Regex("Version/[0-9.]+ "), "")
        applyMode(prefs.getBoolean("desktop", true))
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val scheme = request.url.scheme.orEmpty()
                if (scheme == "http" || scheme == "https") return false
                // intent:// 의 대신 갈 주소가 있으면 그리로. 다른 앱으로 빠지는 주소(market: 등)는 열지 않는다
                if (scheme == "intent") {
                    Regex("S\\.browser_fallback_url=([^;]+)").find(request.url.toString())?.let {
                        view.loadUrl(Uri.decode(it.groupValues[1]))
                    }
                }
                return true
            }

            override fun onPageFinished(view: WebView, url: String) {
                phoneButton.visibility = if (Uri.parse(url).host == "accounts.google.com") View.VISIBLE else View.GONE
                val session = space ?: return
                if (installed || !url.startsWith(Server.WEB)) return
                installed = true
                view.evaluateJavascript(installScript(session)) { result -> if (result == "true") view.loadUrl(target) }
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onReceivedTitle(view: WebView, title: String?) {
                if (!title.isNullOrBlank()) titleView.text = title
            }

            override fun onShowFileChooser(view: WebView, callback: ValueCallback<Array<Uri>>, params: FileChooserParams): Boolean {
                fileCallback?.onReceiveValue(null)
                fileCallback = callback
                return try {
                    startActivityForResult(params.createIntent().putExtra(Intent.EXTRA_ALLOW_MULTIPLE,
                        params.mode == FileChooserParams.MODE_OPEN_MULTIPLE), PICK)
                    true
                } catch (e: Exception) {
                    fileCallback = null
                    false
                }
            }

            override fun onShowCustomView(view: View, callback: CustomViewCallback) {
                fullscreen = view
                (window.decorView as FrameLayout).addView(view, FrameLayout.LayoutParams(-1, -1))
            }

            override fun onHideCustomView() {
                fullscreen?.let { (window.decorView as FrameLayout).removeView(it) }
                fullscreen = null
            }
        }
        web.setDownloadListener { _, _, _, _, _ ->
            Toast.makeText(this, "앱 안 브라우저에서는 내려받기를 지원하지 않습니다. 드라이브는 «내 드라이브»에서 여세요.", Toast.LENGTH_LONG).show()
        }
        // 스페이스기전은 먼저 첫 화면에서 로그인을 심고 → 원래 화면으로
        web.loadUrl(if (space != null) Server.WEB + "/" else target)
    }

    /**
     * PC 화면(기본) — 칠판은 큰 화면이라 휴대폰용 화면(앱 안 브라우저가 «휴대폰»으로 알리면 사이트가 보낸다)이 어색하게 늘어난다.
     * Chrome 의 «데스크톱 사이트 보기»와 같은 방식(일반 PC Chrome 이라고 알린다). 사이트가 깨지면 [모바일 화면]으로.
     */
    private fun applyMode(pc: Boolean) {
        desktop = pc
        val chrome = Regex("Chrome/([0-9.]+)").find(mobileUa)?.groupValues?.get(1) ?: "120.0.0.0"
        web.settings.userAgentString = if (pc)
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/$chrome Safari/537.36"
        else mobileUa
        web.settings.useWideViewPort = true
        web.settings.loadWithOverviewMode = true
        modeButton.text = if (pc) "PC 화면" else "모바일 화면"
    }

    /**
     * 휴대폰으로 구글 비밀번호 입력 — 일회용 키를 만들어 QR 을 보이고, 휴대폰이 보낸 암호문을 풀어 로그인 칸에 넣는다.
     * 비밀번호는 이 함수 안에서만 잠깐 있고 저장하지 않는다.
     */
    private fun startPhoneTyping() {
        // 이 화면은 다른 프로세스(:web) — 수업 코드·이메일은 화면을 열 때 받았고, 서버에는 이 기기 키로 직접 묻는다
        val sessionCode = intent.getStringExtra(EXTRA_SESSION_CODE)
        val email = intent.getStringExtra(EXTRA_EMAIL).orEmpty()
        val link = LinkClient(DeviceKey.get(this))
        if (sessionCode == null) {
            Toast.makeText(this, "수업 중에만 쓸 수 있습니다.", Toast.LENGTH_LONG).show()
            return
        }
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(24f), dp(20f), dp(24f), dp(8f))
        }
        val qr = android.widget.ImageView(this)
        box.addView(qr, LinearLayout.LayoutParams(dp(260f), dp(260f)))
        val status = TextView(this).apply {
            text = "QR 을 만드는 중…"
            textSize = 16f
            setTextColor(0xFF1E293B.toInt())
            gravity = Gravity.CENTER
            setPadding(0, dp(14f), 0, dp(6f))
        }
        box.addView(status)
        box.addView(TextView(this).apply {
            text = "수업을 연 선생님 휴대폰으로 찍고, 휴대폰에서 구글 비밀번호를 넣어 보내세요.\n" +
                "비밀번호는 휴대폰에서 암호화되어 이 칠판만 풀 수 있고, 저장하지 않습니다."
            textSize = 13f
            setTextColor(0xFF64748B.toInt())
            gravity = Gravity.CENTER
        })
        var relay: String? = null
        val dialog = android.app.AlertDialog.Builder(this)
            .setTitle("휴대폰으로 구글 로그인")
            .setView(box)
            .setNegativeButton("닫기", null)
            .create()
        dialog.setOnDismissListener {
            typing = null
            relay?.let { c -> kotlin.concurrent.thread { runCatching { link.typeCancel(c) } } }
        }
        typing = dialog
        dialog.show()
        val key = TypeKey.create()
        kotlin.concurrent.thread {
            val started = runCatching { link.typeStart(sessionCode, key.public) }
            val code = started.getOrNull()?.optString("code").orEmpty()
            if (code.isEmpty()) {
                runOnUiThread { status.text = started.exceptionOrNull()?.message ?: "QR 을 만들지 못했습니다." }
                return@thread
            }
            relay = code
            val bitmap = Qr.bitmap(TypeKey.typeUrl(code, key.public), dp(260f))
            runOnUiThread { qr.setImageBitmap(bitmap); status.text = "휴대폰에서 보내기를 기다리는 중…" }
            while (typing === dialog) {
                Thread.sleep(1500)
                val r = runCatching { link.typePoll(code) }.getOrNull() ?: continue
                when (r.optString("status")) {
                    "expired" -> {
                        relay = null
                        runOnUiThread { qr.setImageDrawable(null); status.text = "QR 이 만료됐습니다. 닫고 다시 눌러 주세요." }
                        return@thread
                    }
                    "sent" -> {
                        relay = null
                        val password = runCatching { key.open(code, r.getJSONObject("payload")) }.getOrNull()
                        runOnUiThread {
                            qr.setImageDrawable(null)
                            if (password == null) status.text = "받은 내용을 풀지 못했습니다. 다시 시도해 주세요."
                            else fillLogin(email, password, 0, status, dialog)
                        }
                        return@thread
                    }
                }
            }
        }
    }

    /** 구글 로그인 화면을 한 단계씩 채운다(이메일 → 비밀번호). 비밀번호 칸에 넣으면 끝 */
    private fun fillLogin(email: String, password: String, tries: Int, status: TextView, dialog: android.app.Dialog) {
        if (tries > 12) {
            status.text = "구글 로그인 칸을 찾지 못했습니다. 로그인 화면이 열려 있는지 확인해 주세요."
            return
        }
        web.evaluateJavascript(TypeKey.fillScript(email, password)) { result ->
            when (result?.trim('"')) {
                "password" -> {
                    status.text = "넣었습니다. 휴대폰에 구글 확인 알림이 오면 «예»를 누르세요."
                    web.postDelayed({ if (dialog.isShowing) dialog.dismiss() }, 4000)
                }
                "email", "chooser" -> web.postDelayed({ fillLogin(email, password, tries + 1, status, dialog) }, 2000)
                else -> web.postDelayed({ fillLogin(email, password, tries + 1, status, dialog) }, 1000)
            }
        }
    }

    @Deprecated("Activity 결과")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode == PICK) {
            fileCallback?.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data))
            fileCallback = null
            return
        }
        super.onActivityResult(requestCode, resultCode, data)
    }

    override fun onResume() {
        super.onResume()
        Bubble.hide(this)
    }

    @Deprecated("뒤로")
    override fun onBackPressed() {
        when {
            fullscreen != null -> web.webChromeClient?.onHideCustomView()
            web.canGoBack() -> web.goBack()
            else -> finish()
        }
    }

    fun closeNow() {
        if (closed) return
        closed = true
        runCatching { web.loadUrl("about:blank"); web.stopLoading() }
        finish()
    }

    override fun onDestroy() {
        typing?.dismiss()
        synchronized(open) { open.removeAll { it.get() == null || it.get() === this } }
        runCatching { (web.parent as? ViewGroup)?.removeView(web); web.destroy() }
        super.onDestroy()
    }
}
