package kr.hs.kijun.classroom

import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.time.OffsetDateTime

/**
 * 교실 기기 ↔ 서버 — Windows 교실판(app/core/classroom_link.py)과 같은 약속.
 *
 * 서버는 SPACEKIJUN 의 DB 함수 `classroom_device_call`(PostgREST RPC, anon 키 — 20261110150000_classroom_device_rpc.sql).
 * 2026-11-10 까지는 Edge Function `classroom-link` 를 불렀는데, QR 대기 중 자주 묻는 호출이 Edge Function 한도를 넘길 만큼
 * 많아 DB 로 옮겼다(교사 쪽 승인만 Edge Function 에 남는다). docs/features/classroom-link.md
 * 이 기기는 **로그인하지 않는다.** 처음 켤 때 만든 임의 키(device key, DeviceKey.kt)로만 자기를 증명한다.
 * 서버는 키의 sha256 만 안다. platform 은 'android' — 승인 화면에 «전자칠판»으로 보인다.
 */
object Server {
    const val SUPABASE = "https://your-project-ref.supabase.co"
    const val RPC = "$SUPABASE/rest/v1/rpc/classroom_device_call"
    // 공개 anon 키(웹·데스크와 같다 — 비밀이 아니다). 권한은 DB 함수가 기기 키로 가린다
    const val ANON_KEY = "YOUR_SUPABASE_ANON_KEY"
    const val WEB = "https://spacekijun.lovable.app"
    const val APPROVE = "$WEB/classroom/link/"
    const val SETUP = "$WEB/classroom"
    // 스페이스기전 웹이 로그인을 보관하는 자리(app/core/web_login.py 와 같다)
    const val STORAGE_KEY = "sb-your-project-ref-auth-token"
    const val OWNER_KEY = "spacekijun-desktop-linked-user"
    // 자동 업데이트 — deploy/classroom-android/build.py 가 올린다
    const val RELEASES = "$SUPABASE/storage/v1/object/public/desk-releases/classroom-android"
    const val PLATFORM = "android"
}

private val ERROR_TEXT = mapOf(
    "rate_limited" to "QR 을 너무 자주 새로 만들었습니다. 잠시 뒤 다시 시도합니다.",
    "invalid_device" to "이 기기의 연결 키가 올바르지 않습니다. 앱을 다시 켜 주세요.",
    "network" to "인터넷에 연결되지 않았습니다. 연결되면 QR 이 다시 나타납니다.",
)

class LinkError(val code: String) :
    Exception(ERROR_TEXT[code] ?: "서버와 연결하지 못했습니다. 잠시 뒤 다시 시도합니다.")

/** POST 한 번 → (상태 코드, 본문). 시험에서는 바꿔 끼운다. 연결 실패는 IOException. */
fun interface Transport {
    fun post(url: String, body: String): Pair<Int, String>
}

object HttpTransport : Transport {
    override fun post(url: String, body: String): Pair<Int, String> {
        val conn = URL(url).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "POST"
            conn.connectTimeout = 15_000
            conn.readTimeout = 15_000
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json")
            conn.setRequestProperty("apikey", Server.ANON_KEY)
            conn.setRequestProperty("Authorization", "Bearer " + Server.ANON_KEY)
            conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            val status = conn.responseCode
            val stream = if (status in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.use { it.readBytes().toString(Charsets.UTF_8) } ?: ""
            return status to text
        } finally {
            conn.disconnect()
        }
    }
}

class LinkClient(
    private val key: String,
    private val transport: Transport = HttpTransport,
    private val url: String = Server.RPC,
) {
    private fun call(action: String, vararg extra: Pair<String, Any>): JSONObject {
        val args = JSONObject()
        for ((k, v) in extra) args.put(k, v)
        val body = JSONObject().put("p_action", action).put("p_device_key", key).put("p_args", args)
        val (status, text) = try {
            transport.post(url, body.toString())
        } catch (e: IOException) {
            throw LinkError("network")
        }
        val json = try {
            JSONObject(text)
        } catch (e: JSONException) {
            throw LinkError(if (status in 200..299) "network" else "server_error")
        }
        if (status !in 200..299) throw LinkError(json.optString("error").ifEmpty { "server_error" })
        // 알려진 오류는 200 에 {"error": 코드}로 온다
        json.optString("error").takeIf { it.isNotEmpty() }?.let { throw LinkError(it) }
        return json
    }

    /** → {code, expires_at}. purpose='drive' = 수업 중 «드라이브 다시 연결» QR */
    fun start(name: String, purpose: String = "session") =
        call("start", "name" to name.take(40), "platform" to Server.PLATFORM, "purpose" to purpose)

    /** → {status: pending|expired|approved|active|ended|cancelled|unknown, handoff?, ends_at?} */
    fun poll(code: String) = call("poll", "code" to code)
    fun extend(code: String, minutes: Int) = call("extend", "code" to code, "minutes" to minutes)
    fun end(code: String) = call("end", "code" to code)

    /** 지금 수업 중인 선생님의 이 기기 로그인 보관 열쇠를 서버에서 지운다 */
    fun forgetProfile(code: String) = call("forget_profile", "code" to code)

    // 휴대폰으로 구글 비밀번호 입력(TypeRelay.kt) — 암호문만 오간다
    fun typeStart(sessionCode: String, devicePub: String) = call("type_start", "code" to sessionCode, "device_pub" to devicePub)
    fun typePoll(code: String) = call("type_poll", "code" to code)
    fun typeCancel(code: String) = call("type_cancel", "code" to code)
}

fun approveUrl(code: String) = Server.APPROVE + code

/** 서버의 ISO 시각 → epoch 초. 못 읽으면 null */
fun parseTime(value: Any?): Double? {
    val text = (value as? String)?.takeIf { it.isNotBlank() && it != "null" } ?: return null
    return try {
        OffsetDateTime.parse(text.replace(" ", "T")).toInstant().toEpochMilli() / 1000.0
    } catch (e: Exception) {
        null
    }
}
