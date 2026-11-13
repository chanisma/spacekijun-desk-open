package kr.hs.kijun.classroom

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.URLEncoder
import java.util.UUID

/**
 * 교실 프로그램 키 → 이 기기(안드로이드)의 앱. 키는 웹 CLASSROOM_PROGRAMS · Windows PROGRAMS 와 같다.
 * 서버에는 키만 있다 — 교사 계정 하나가 털려도 칠판에서 아무 앱이나 열지 못하게, 여기 적은 앱만 연다.
 * 🚨 패키지 이름을 늘리면 AndroidManifest.xml 의 <queries> 에도 적는다(Android 11+ 는 안 적으면 «없음»으로 보인다).
 */
object Programs {
    val KNOWN: Map<String, Pair<String, List<String>>> = mapOf(
        "powerpoint" to ("PowerPoint" to listOf("com.microsoft.office.powerpoint", "com.microsoft.office.officehubrow")),
        "word" to ("Word" to listOf("com.microsoft.office.word", "com.microsoft.office.officehubrow")),
        "excel" to ("Excel" to listOf("com.microsoft.office.excel", "com.microsoft.office.officehubrow")),
        "hwp" to ("한글" to listOf("com.hancom.office.editor", "com.hancom.androidpc.viewer.launcher", "com.hancom.office.viewer")),
        "whiteboard" to ("Microsoft Whiteboard" to listOf("com.microsoft.whiteboard.publicpreview")),
        "calculator" to ("계산기" to listOf("com.google.android.calculator", "com.sec.android.app.popupcalculator")),
        // Windows 에만 있는 것 — 칠판에서는 «이 기기에 없음»
        "notepad" to ("메모장" to emptyList()),
        "paint" to ("그림판" to emptyList()),
        "snipping" to ("캡처 도구" to emptyList()),
        "osk" to ("화상 키보드" to emptyList()),
    )

    fun label(key: String) = KNOWN[key]?.first ?: key
}

/** 서버 값 읽기 — 없거나 JSON null 이면 "" (org.json 의 optString 은 null 을 "null" 글자로 준다: 칠판에 «null»이 보였다) */
fun JSONObject.str(key: String): String = if (isNull(key)) "" else optString(key)

/** 구글 앱 키 → 구글 수업 도구 탭(로그인 없이, gtools.js) */
val GTOOLS_APPS = mapOf("classroom" to "classroom", "slides" to "slides", "forms" to "forms")

val GOOGLE_APPS: Map<String, Pair<String, String>> = linkedMapOf(
    "classroom" to ("클래스룸" to "https://classroom.google.com/"),
    "drive" to ("드라이브(웹)" to "https://drive.google.com/"),
    "docs" to ("문서" to "https://docs.google.com/document/"),
    "sheets" to ("시트" to "https://docs.google.com/spreadsheets/"),
    "slides" to ("슬라이드" to "https://docs.google.com/presentation/"),
    "forms" to ("설문지" to "https://docs.google.com/forms/"),
    "calendar" to ("캘린더" to "https://calendar.google.com/"),
    "meet" to ("Meet" to "https://meet.google.com/"),
    "gmail" to ("Gmail" to "https://mail.google.com/"),
    "keep" to ("Keep" to "https://keep.google.com/"),
    "sites" to ("사이트" to "https://sites.google.com/"),
    "youtube" to ("YouTube" to "https://www.youtube.com/"),
)

/** 앱 바깥(화면)과 이어지는 일 — MainActivity/ClassroomApp 이 맡는다. 시험에서는 가짜로 */
interface Host : FileLauncher {
    /** 앱 안 브라우저(수업이 끝나면 쿠키·저장소째 지운다). space = 스페이스기전 로그인을 심어 연다 */
    fun openWeb(url: String, title: String, space: JSONObject? = null)
    /** 프로그램 키 → 앱을 연다. 못 열면 오류 문구 */
    fun launchProgram(key: String): String?
    /** 앱 안 브라우저를 모두 닫고 쿠키·저장소·캐시를 지운다 */
    fun clearWeb()
    /** 이 기기에 그 프로그램(앱)이 있나 — 수업 화면에서 없는 것은 흐리게 */
    fun hasProgram(key: String): Boolean = true
    /** 수업 시작 — 앱 안 브라우저를 비우고 보관 로그인을 풀어 넣는다(WebVault) → 풀었으면 true */
    fun prepareWeb(profile: JSONObject?): Boolean = false
    /** 수업 끝 — 앱 안 브라우저를 닫고, 열쇠가 있으면 로그인을 잠가 남긴 뒤 비운다 */
    fun finishWeb(profile: JSONObject?) = clearWeb()
    /** 이 칠판의 로그인 보관 지우기 */
    fun forgetWeb(ref: String?) = clearWeb()
    fun webVaultSupported(): Boolean = false
    /** 풀어 넣은 앱 안 브라우저 데이터에 구글 로그인이 있나(WebVault.googleLoginIn) — 모르면 null */
    fun webGoogleLogin(): Boolean? = null
}

/** Controller 가 다루는 수업 한 번 — 시험에서는 가짜로 바꿔 끼운다 */
interface ClassSession {
    val email: String
    fun prepare()
    fun syncDrive()
    fun updateGoogle(google: JSONObject?)
    /** 정리 — 드라이브에 못 올리고 기기에 남긴 파일 수 */
    fun end(progress: (String) -> Unit): Int
    fun snapshot(): JSONObject
}

/**
 * 승인 한 건 = 수업 한 번. 연 것을 기억했다가 end() 에서 걷어 낸다. 아무것도 저절로 열지 않는다
 * (2026-10-13 결정 — «세팅된다» = 수업 화면에 타일로 놓여 쉽게 여는 것).
 *
 *  url     앱 안 브라우저로(구글 앱은 선생님 이메일을 채운 로그인으로). 끝나면 쿠키·저장소째 지운다.
 *  drive   폴더 → 앱 안 탐색기, 파일 → 받아 이 기기 앱으로 열고 바뀌면 되올린다.
 *  program 정해 둔 앱만(Programs).
 *  space   스페이스기전 화면 — 받은 세션을 심은 앱 안 브라우저.
 * 구글 로그인 보관(A+, Windows 판의 Edge 프로필 암호화)은 안드로이드판에 없다 — 받은 열쇠는 쓰지 않는다.
 */
class Session(
    handoff: JSONObject,
    private val host: Host,
    root: File,
    private val unsent: UnsentBox,
    http: DriveHttp = UrlDriveHttp,
    private val clock: () -> Double = { System.currentTimeMillis() / 1000.0 },
) : ClassSession {
    private val preset = handoff.optJSONObject("preset") ?: JSONObject()
    val teacher: JSONObject = handoff.optJSONObject("teacher") ?: JSONObject()
    override val email: String get() = teacher.str("email")
    val title: String = preset.str("title")
    val items: List<JSONObject> = preset.optJSONArray("items")?.let { a -> (0 until a.length()).mapNotNull { a.optJSONObject(it) } } ?: emptyList()
    private val status = items.map { JSONObject().put("state", "idle").put("message", "") }
    private val space: JSONObject? = handoff.optJSONObject("space_session")
    /** 로그인 보관 열쇠(승인 화면 «이 기기에 로그인 보관», 서버 classroom_profile_key) — 없으면 보관하지 않는다 */
    @Volatile var profile: JSONObject? = handoff.optJSONObject("profile")
        ?.takeIf { WebVault.REF.matches(it.str("ref")) && it.str("key").isNotEmpty() }
        private set
    /** 보관본에 구글 로그인이 있었나(null = 모름) · 이번 수업에 «지우기»를 눌렀나 — 구글 창 안내에 */
    @Volatile var loginGoogle: Boolean? = null
        private set
    @Volatile var loginCleared = false
        private set
    @Volatile var loginRestored = false
        private set
    val dir = File(root, UUID.randomUUID().toString().replace("-", "").take(12))
    @Volatile private var google: String? = null
    @Volatile private var googleExpires: Double? = null
    @Volatile private var googleScope = ""
    @Volatile var notice = ""
    private val available = java.util.concurrent.ConcurrentHashMap<String, Boolean>()     // 프로그램 키 → 이 기기에 있나(한 번만 찾는다)
    val workspace = Workspace(File(dir, "drive"), ::googleToken, host, http, clock)

    init {
        updateGoogle(handoff.optJSONObject("google"))
    }

    override fun updateGoogle(google: JSONObject?) {
        val token = google?.str("access_token").orEmpty()
        if (token.isEmpty()) return
        this.google = token
        this.googleExpires = google!!.optDouble("expires_at").takeIf { !it.isNaN() && it > 0 }
        this.googleScope = google.str("scope").ifEmpty { FULL_DRIVE }
    }

    fun googleToken(): String? {
        val token = google ?: return null
        val expires = googleExpires
        return if (expires != null && clock() >= expires - 30) null else token
    }

    fun driveState(): JSONObject {
        val connected = googleToken() != null
        val left = googleExpires?.let { (it - clock()).toInt() } ?: 0
        return JSONObject().put("connected", connected).put("left", if (connected) left else 0)
            .put("ever", google != null).put("full", FULL_DRIVE in googleScope.split(' '))
    }

    override fun prepare() {
        dir.mkdirs()
        // 이 칠판에 보관해 둔 이 선생님 로그인(구글·패들렛 등)을 앱 안 브라우저에 풀어 넣는다
        loginRestored = runCatching { host.prepareWeb(profile) }.getOrDefault(false)
        loginGoogle = if (loginRestored) runCatching { host.webGoogleLogin() }.getOrNull() else null
        // 지난 수업에 못 올린 파일이 있으면 지금 올린다
        if (googleToken() != null && unsent.has(email)) {
            runCatching { unsent.send(workspace.drive(), email) }.getOrNull()?.takeIf { it > 0 }?.let {
                notice = "지난 수업에 못 올린 파일 ${it}개를 드라이브 «$UNSENT_FOLDER» 폴더에 올렸습니다."
            }
        }
    }

    override fun syncDrive() {
        workspace.sync()
    }

    private fun mark(index: Int, state: String, message: String = "") {
        status[index].put("state", state).put("message", message)
    }

    /** 선생님 이메일을 채워 둔 구글 로그인 — 이미 로그인했으면 곧바로 continue 로 간다 */
    fun googleUrl(target: String): String {
        if (email.isEmpty()) return target
        val enc = { v: String -> URLEncoder.encode(v, "UTF-8") }
        return "https://accounts.google.com/ServiceLogin?Email=${enc(email)}&continue=${enc(target)}"
    }

    fun openGoogleApp(key: String): JSONObject {
        val (label, url) = GOOGLE_APPS[key] ?: return fail("모르는 구글 앱입니다.")
        host.openWeb(googleUrl(url), label)
        return ok()
    }

    /** 타일을 눌렀다. 드라이브 폴더면 탐색기를 열라고 화면에 돌려준다 */
    fun openItem(index: Int): JSONObject {
        val item = items.getOrNull(index) ?: return fail("항목을 찾지 못했습니다.")
        val name = item.str("name")
        return try {
            when (item.str("kind")) {
                "url" -> {
                    val app = item.str("app")
                    // 클래스룸·슬라이드·설문지는 로그인 없이 구글 수업 도구로(화면이 연다) — 웹은 도구 안 [웹으로 열기]
                    if (app in GTOOLS_APPS) ok().put("gtools", GTOOLS_APPS.getValue(app))
                    else if (app.isNotEmpty() && app in GOOGLE_APPS) openGoogleApp(app)
                    else host.openWeb(item.str("url"), name).let { ok() }
                }
                "drive" -> if (item.str("mimeType") == FOLDER) {
                    ok().put("folder", JSONObject().put("id", item.str("id")).put("name", name))
                } else {
                    mark(index, "opening")
                    workspace.open(item.str("id"))
                    mark(index, "idle")
                    ok()
                }
                "program" -> {
                    val error = host.launchProgram(item.str("program"))
                    if (error != null) { mark(index, "failed", error); fail(error) } else ok()
                }
                "space" -> {
                    host.openWeb(Server.WEB + item.str("path").ifEmpty { "/" }, name.ifEmpty { "스페이스기전" }, space)
                    ok()
                }
                else -> fail("이 기기가 모르는 항목입니다. 앱을 새 판으로 바꿔 주세요.")
            }
        } catch (e: DriveError) {
            mark(index, "failed", e.message.orEmpty())
            fail(e.message.orEmpty(), auth = e.auth)
        }
    }

    /** 이 칠판의 로그인 보관 지우기 — 서버 열쇠는 부른 쪽(Bridge)이 지운다 */
    fun forgetLogin() {
        // 지금 로그인과 보관본을 지운다. 보관은 끄지 않는다 — 지운 뒤 다시 로그인하면 끝날 때 새로 보관(Windows 1.5.5 와 같다).
        // 1.3.0 까지는 «이번 수업도 남기지 않음»이라 지우고 다시 로그인한 것이 사라졌다(2026-10-14 사용자 보고, Windows).
        loginRestored = false
        loginGoogle = null
        loginCleared = true
        runCatching { host.forgetWeb(profile?.str("ref")) }
    }

    override fun snapshot(): JSONObject {
        val list = JSONArray()
        items.forEachIndexed { i, item ->
            list.put(JSONObject().put("kind", item.str("kind")).put("name", item.str("name"))
                .put("folder", item.str("mimeType") == FOLDER).put("mime", item.str("mimeType"))
                .put("app", item.str("app")).put("site", item.str("site")).put("url", item.str("url"))
                .put("program", item.str("program")).put("state", status[i].str("state"))
                .put("available", item.str("kind") != "program" || available.getOrPut(item.str("program")) { host.hasProgram(item.str("program")) })
                .put("message", status[i].str("message")))
        }
        return JSONObject().put("title", title).put("section", preset.str("section_name"))
            .put("teacher", JSONObject().put("name", teacher.str("name")).put("email", email))
            .put("items", list).put("drive", driveState()).put("opened", workspace.snapshot()).put("notice", notice)
            .put("login", JSONObject().put("kept", profile != null).put("restored", loginRestored)
                .put("google", loginGoogle ?: JSONObject.NULL).put("cleared", loginCleared)
                .put("supported", host.webVaultSupported()))
    }

    override fun end(progress: (String) -> Unit): Int {
        progress("고친 파일을 드라이브에 올리는 중입니다.")
        runCatching { workspace.sync(final = true) }
        val kept = runCatching { workspace.stashUnsent(unsent, email) }.getOrDefault(0)
        progress(if (profile != null) "로그인을 이 칠판에 잠가 두는 중입니다." else "열린 화면과 로그인을 지우는 중입니다.")
        runCatching { host.finishWeb(profile) }
        progress("받은 파일을 지우는 중입니다.")
        dir.deleteRecursively()
        return kept
    }

    private fun ok() = JSONObject().put("ok", true)
    private fun fail(message: String, auth: Boolean = false) = JSONObject().put("ok", false).put("error", message).put("auth", auth)
}
