package kr.hs.kijun.classroom

import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * 구글 수업 도구(assets/web/gtools.js)의 구글 API 다리 — 클래스룸·슬라이드 발표·설문지를 «구글 로그인 없이»(2026-10-14).
 * QR 승인 때 받은 토큰으로 기기가 구글 API 를 직접 부른다. 토큰은 화면(JS)에 주지 않는다.
 * 화면이 부를 수 있는 주소는 허용 목록뿐이고 쓰기는 «클래스룸 공지 올리기» 하나. Windows 판 core/google_tools.py 와 같은 규칙.
 */
object GoogleApi {
    private val READ_PREFIXES = listOf(
        "https://classroom.googleapis.com/v1/courses",
        "https://classroom.googleapis.com/v1/userProfiles/",
        "https://forms.googleapis.com/v1/forms/",
        "https://slides.googleapis.com/v1/presentations/",
        "https://www.googleapis.com/drive/v3/files?",
    )
    private val POST_ANNOUNCEMENT = Regex("^https://classroom\\.googleapis\\.com/v1/courses/[A-Za-z0-9_-]+/announcements$")
    private val API_NAMES = mapOf("classroom" to "Google Classroom", "forms" to "Google Forms", "slides" to "Google Slides", "www" to "Google Drive")

    fun allowed(method: String, url: String): Boolean {
        if (".." in url || '#' in url || '@' in url || url.length > 4000) return false
        return when (method) {
            "GET" -> READ_PREFIXES.any { url.startsWith(it) }
            "POST" -> POST_ANNOUNCEMENT.matches(url)
            else -> false
        }
    }

    fun apiName(url: String) = API_NAMES[url.split('/').getOrNull(2)?.substringBefore('.')] ?: "Google"

    /** 구글 오류 → 화면이 알아듣는 이유. 오류 본문·토큰은 싣지 않는다 */
    fun explain(status: Int, text: String, url: String): JSONObject {
        val lower = text.lowercase()
        val out = JSONObject().put("ok", false).put("status", status)
        return when {
            status == 401 -> out.put("reason", "auth")
            status == 403 && listOf("service_disabled", "has not been used", "is disabled", "accessnotconfigured").any { it in lower } ->
                out.put("reason", "disabled").put("api", apiName(url))
            status == 403 && ("insufficient" in lower || "scope" in lower) -> out.put("reason", "scope")
            status == 404 -> out.put("reason", "notfound")
            status == 403 -> out.put("reason", "forbidden").put("error", "이 항목에 대한 권한이 없습니다.")
            else -> out.put("reason", "error").put("error", "구글 요청이 실패했습니다($status).")
        }
    }

    /** HTTP 한 번 → (상태, 본문). 시험에서는 바꿔 끼운다 */
    fun interface Http {
        fun send(url: String, method: String, token: String, body: String?): Pair<Int, String>
    }

    object UrlHttp : Http {
        override fun send(url: String, method: String, token: String, body: String?): Pair<Int, String> {
            val conn = URL(url).openConnection() as HttpURLConnection
            try {
                conn.requestMethod = method
                conn.connectTimeout = 20_000
                conn.readTimeout = 30_000
                conn.setRequestProperty("Authorization", "Bearer $token")
                if (body != null) {
                    conn.doOutput = true
                    conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8")
                    conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                }
                val status = conn.responseCode
                val stream = if (status in 200..299) conn.inputStream else conn.errorStream
                return status to (stream?.use { it.readBytes().toString(Charsets.UTF_8) } ?: "")
            } finally {
                conn.disconnect()
            }
        }
    }

    fun call(token: String?, method: String, url: String, body: JSONObject?, http: Http = UrlHttp): JSONObject {
        val m = method.uppercase()
        if (!allowed(m, url)) return JSONObject().put("ok", false).put("reason", "denied").put("error", "허용하지 않은 요청입니다.")
        if (token.isNullOrEmpty()) return JSONObject().put("ok", false).put("reason", "auth")
        var payload: String? = null
        if (m == "POST") {
            val text = body?.str("text")?.trim().orEmpty()
            if (text.isEmpty()) return JSONObject().put("ok", false).put("reason", "denied").put("error", "공지 내용이 비어 있습니다.")
            // 공지는 글과 게시 상태만 — 화면이 다른 필드(대상 학생 등)를 섞지 못하게
            payload = JSONObject().put("text", text.take(30000)).put("state", "PUBLISHED").toString()
        }
        val (status, text) = try {
            http.send(url, m, token, payload)
        } catch (e: IOException) {
            return JSONObject().put("ok", false).put("reason", "network").put("error", "인터넷 연결을 확인해 주세요.")
        }
        if (status !in 200..299) return explain(status, text, url)
        return JSONObject().put("ok", true).put("data", if (text.isBlank()) JSONObject() else JSONObject(text))
    }
}
