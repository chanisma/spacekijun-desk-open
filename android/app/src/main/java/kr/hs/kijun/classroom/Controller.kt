package kr.hs.kijun.classroom

import org.json.JSONObject
import java.time.Instant
import java.time.ZoneId

/**
 * 교실 기기의 흐름 — QR → 승인 → 수업 → 정리 → 다시 QR. Windows 판 app/core/classroom_controller.py 를 옮겼다.
 *
 *  qr       QR 을 띄우고 4초마다 승인을 묻는다. QR 은 10분마다 새로(서버가 정한다).
 *  sleep    쉬는 중 — 서버를 부르지 않는다. 평일 07~18시 밖(밤·주말)에 QR 을 10분 띄웠는데 아무도 연결하지 않으면.
 *           화면을 누르면(board.js → wake) 또는 평일 07시가 되면 다시 QR. (2026-11-10 — 호출 수 줄이기)
 *  offline  서버에 닿지 않는다 — 10초 뒤 다시.
 *  session  수업 중 — 수업 화면(타일). 아무것도 저절로 열지 않는다. 20초마다 휴대폰에서 «수업 끝»을 눌렀는지 본다.
 *           끝날 시각이 지나면 정리. 연 드라이브 파일이 바뀌면 되올린다. 드라이브 토큰(1시간)이 끝나면
 *           «드라이브 다시 연결» QR(purpose=drive) — 수업 중인 선생님이 찍으면 토큰만 바뀐다.
 *  ending   정리 중
 */
class Controller(
    private val client: LinkClient,
    private val name: () -> String,
    private val sessionFactory: (JSONObject) -> ClassSession,
    private val clock: () -> Double = { System.currentTimeMillis() / 1000.0 },
    private val qr: (String) -> String = Qr::svg,
    /** 정리가 끝났을 때(QR 화면으로 돌아왔다) — 앱을 앞으로 */
    private val onFinished: () -> Unit = {},
) {
    companion object {
        const val POLL_QR = 4.0
        const val SLEEP_CHECK = 2.0
        const val AWAKE_OFF_HOURS = 10 * 60

        /** 평일 07~18시(기기 시각) — QR 을 쉬지 않고 띄워 두는 때 */
        fun schoolHours(epochSeconds: Double): Boolean {
            val t = Instant.ofEpochMilli((epochSeconds * 1000).toLong()).atZone(ZoneId.systemDefault())
            return t.dayOfWeek.value <= 5 && t.hour in 7..17
        }
        const val POLL_SESSION = 20.0
        const val RETRY_OFFLINE = 10.0
        const val WARN_BEFORE = 5 * 60
    }

    private val lock = Any()
    @Volatile var phase = "qr"; private set
    private var code: String? = null
    /** 지금 수업의 연결 코드(휴대폰으로 입력이 쓴다) */
    val sessionCode: String? get() = synchronized(lock) { if (phase == "session") code else null }
    private var qrSvg = ""
    private var expiresAt: Double? = null
    private var endsAt: Double? = null
    private var error = ""
    @Volatile var notice = ""
    private var progress = ""
    @Volatile var session: ClassSession? = null; private set
    private var nextServerCheck = 0.0
    private var driveLink: Triple<String, String, Double>? = null    // (code, qr, expires_at)
    private var nextDrivePoll = 0.0
    @Volatile private var awakeSince = clock()

    /** 한 번 돌고, 다음까지 쉴 초 */
    fun step(): Double = try {
        when (phase) {
            "sleep" -> stepSleep()
            "qr", "offline" -> if (shouldSleep()) { sleep(); SLEEP_CHECK } else stepQr()
            "session" -> stepSession()
            else -> 0.5
        }
    } catch (e: LinkError) {
        synchronized(lock) {
            error = e.message.orEmpty()
            if (phase == "qr" || phase == "offline") {
                phase = "offline"
                code = null
            }
        }
        RETRY_OFFLINE
    }

    // 쉬기 -----------------------------------------------------------------------
    private fun shouldSleep(): Boolean {
        val now = clock()
        return !schoolHours(now) && now - awakeSince >= AWAKE_OFF_HOURS
    }

    private fun sleep() {
        val old = synchronized(lock) {
            code.also {
                code = null
                phase = "sleep"
                qrSvg = ""
                expiresAt = null
                error = ""
            }
        }
        if (old != null) runCatching { client.end(old) }    // 떠 있던 QR 을 닫는다(찍어도 연결되지 않게)
    }

    private fun stepSleep(): Double {
        if (schoolHours(clock())) wake()
        return SLEEP_CHECK
    }

    /** 화면을 눌렀다(쉬는 중이면 다시 QR) — 쉬는 시간에도 10분을 다시 센다 */
    fun wake() = synchronized(lock) {
        awakeSince = clock()
        if (phase == "sleep") {
            phase = "qr"
            code = null
        }
    }

    private fun newQr() {
        val result = client.start(name())
        val newCode = result.getString("code")
        synchronized(lock) {
            code = newCode
            expiresAt = parseTime(result.opt("expires_at")) ?: (clock() + 180)
            qrSvg = qr(approveUrl(newCode))
            phase = "qr"
            error = ""
        }
    }

    private fun stepQr(): Double {
        val current = code
        if (current == null || (expiresAt?.let { clock() > it - 5 } == true)) {
            newQr()
            return POLL_QR
        }
        val result = client.poll(current)
        val status = result.optString("status")
        val handoff = result.optJSONObject("handoff")
        if (status == "approved" && handoff != null) {
            begin(handoff, result.opt("ends_at"))
            return 0.5
        }
        if (status in setOf("expired", "cancelled", "unknown", "ended")) {
            code = null
            if (status == "cancelled") notice = "휴대폰에서 연결을 거절했습니다."
        }
        return POLL_QR
    }

    private fun begin(handoff: JSONObject, ends: Any?) {
        val made = sessionFactory(handoff)
        made.prepare()
        synchronized(lock) {
            session = made
            endsAt = parseTime(ends)
            phase = "session"
            notice = ""
            nextServerCheck = clock() + POLL_SESSION
        }
    }

    private fun stepSession(): Double {
        val now = clock()
        if (endsAt?.let { now >= it } == true) {
            finish("정해 둔 시간이 지나 수업을 정리했습니다.")
            return 0.5
        }
        runCatching { session?.syncDrive() }
        stepDriveLink(now)
        if (now >= nextServerCheck) {
            nextServerCheck = now + POLL_SESSION
            val result = try {
                client.poll(code ?: return 1.0)
            } catch (e: LinkError) {
                return 1.0                       // 잠깐 끊긴 것 — 끝날 시각은 이 기기가 지킨다
            }
            if (result.optString("status") != "active") {
                finish("휴대폰에서 수업을 끝냈습니다.", tellServer = false)
                return 0.5
            }
            parseTime(result.opt("ends_at"))?.let { endsAt = it }
        }
        return 1.0
    }

    /**
     * 기기 이름을 바꿨다 — 떠 있는 QR 은 옛 이름으로 만든 것이라(서버는 QR 을 만들 때의 이름을 적는다) 버리고 다음 바퀴에
     * 새 이름으로 다시 만든다. 서버는 새 QR 을 만들 때 옛 QR 을 취소한다. 수업 중이면 다음 QR 부터.
     */
    fun renewQr() = synchronized(lock) {
        if (phase == "qr" || phase == "offline") {
            code = null
            expiresAt = null
            qrSvg = ""
        }
    }

    // 드라이브 다시 연결 -----------------------------------------------------------
    fun driveReconnect() {
        if (phase != "session") return
        val result = client.start(name(), purpose = "drive")
        val newCode = result.getString("code")
        synchronized(lock) {
            driveLink = Triple(newCode, qr(approveUrl(newCode)), parseTime(result.opt("expires_at")) ?: (clock() + 180))
            nextDrivePoll = 0.0
        }
    }

    fun driveReconnectCancel() {
        val link = synchronized(lock) { driveLink.also { driveLink = null } } ?: return
        runCatching { client.end(link.first) }
    }

    private fun stepDriveLink(now: Double) {
        val link = driveLink ?: return
        if (now < nextDrivePoll) return
        nextDrivePoll = now + POLL_QR
        if (now > link.third - 5) {
            driveLink = null
            return
        }
        val result = try { client.poll(link.first) } catch (e: LinkError) { return }
        val status = result.optString("status")
        val handoff = if (status == "approved") result.optJSONObject("handoff") else null
        if (handoff != null) {
            val current = session
            val same = current != null && handoff.optJSONObject("teacher")?.optString("email") == current.email
            if (same) {
                current!!.updateGoogle(handoff.optJSONObject("google"))
                notice = "드라이브를 다시 연결했습니다."
            } else {
                notice = "수업 중인 선생님이 아니라 드라이브를 연결하지 않았습니다."
            }
            driveLink = null
            runCatching { client.end(link.first) }      // 드라이브 QR 연결은 토큰만 받고 닫는다
        } else if (status in setOf("expired", "cancelled", "unknown", "ended")) {
            driveLink = null
        }
    }

    // 화면 단추 ------------------------------------------------------------------
    fun extend(minutes: Int = 10) {
        val current = synchronized(lock) { if (phase != "session") null else code } ?: return
        val result = client.extend(current, minutes)
        val ends = parseTime(result.opt("ends_at"))
        synchronized(lock) {
            if (result.optString("status") == "active" && ends != null) endsAt = ends
        }
    }

    fun finish(message: String = "수업을 정리했습니다.", tellServer: Boolean = true) {
        val (current, currentCode, link) = synchronized(lock) {
            if (phase != "session") return
            phase = "ending"
            progress = "정리하는 중입니다."
            Triple(session, code, driveLink).also { driveLink = null }
        }
        val codes = listOfNotNull(if (tellServer) currentCode else null, link?.first)
        for (c in codes) runCatching { client.end(c) }   // 못 닿아도 서버는 끝날 시각에 스스로 로그인을 끊는다
        var kept = 0
        try {
            if (current != null) kept = current.end { progress = it }
        } finally {
            synchronized(lock) {
                session = null
                code = null
                endsAt = null
                phase = "qr"
                awakeSince = clock()
                progress = ""
                notice = message + if (kept > 0) " 드라이브에 올리지 못한 파일 ${kept}개는 다음에 연결하면 올립니다." else ""
            }
            onFinished()
        }
    }

    fun state(): JSONObject = synchronized(lock) {
        val now = clock()
        val remaining = endsAt?.let { (it - now).toInt() }
        val link = driveLink
        JSONObject()
            .put("phase", phase)
            .put("device", name())
            .put("qr", if (phase == "qr") qrSvg else "")
            .put("qr_left", if (phase == "qr" && expiresAt != null) (expiresAt!! - now).toInt() else JSONObject.NULL)
            .put("error", if (phase == "offline") error else "")
            .put("notice", notice)
            .put("progress", progress)
            .put("remaining", remaining ?: JSONObject.NULL)
            .put("warn", remaining != null && remaining <= WARN_BEFORE)
            .put("session", session?.snapshot() ?: JSONObject.NULL)
            .put("drive_link", if (link != null) JSONObject().put("qr", link.second).put("left", (link.third - now).toInt()) else JSONObject.NULL)
    }
}
