package kr.hs.kijun.classroom

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

/** 서버 흉내 — 받은 요청을 적어 두고, 정해 둔 답을 돌려준다 */
class FakeServer : Transport {
    val calls = mutableListOf<JSONObject>()
    val raw = mutableListOf<JSONObject>()
    val urls = mutableListOf<String>()
    var replies = ArrayDeque<Pair<Int, String>>()
    var fail = false

    fun reply(status: Int, body: JSONObject) = replies.addLast(status to body.toString())

    override fun post(url: String, body: String): Pair<Int, String> {
        if (fail) throw IOException("끊김")
        // DB RPC 모양 {p_action, p_device_key, p_args} — 시험은 펼친 모양({action, ...p_args})으로 본다
        val sent = JSONObject(body)
        raw += sent
        urls += url
        val flat = JSONObject().put("action", sent.getString("p_action"))
        val args = sent.getJSONObject("p_args")
        for (k in args.keys()) flat.put(k, args.get(k))
        calls += flat
        return replies.removeFirstOrNull()
            ?: if (flat.getString("action") == "start")       // 정해 둔 답이 없으면 새 QR
                200 to JSONObject().put("code", "Z".repeat(16)).put("expires_at", "2099-01-01T00:00:00Z").toString()
            else 200 to JSONObject().put("status", "pending").toString()
    }
}

class FakeSession(override val email: String = "t@myschool.hs.kr") : ClassSession {
    var prepared = false
    var ended = false
    var google: JSONObject? = null
    var syncs = 0
    override fun prepare() { prepared = true }
    override fun syncDrive() { syncs++ }
    override fun updateGoogle(google: JSONObject?) { this.google = google }
    override fun end(progress: (String) -> Unit): Int { ended = true; progress("정리"); return 0 }
    override fun snapshot() = JSONObject().put("title", "1-3 정보")
}

class ControllerTest {
    // 평일 낮(쉬는 시간이 아니다) — 쉬기 시험은 시각을 따로 정한다
    private var now = at(2026, 11, 12, 9)
    private val server = FakeServer()
    private val made = mutableListOf<FakeSession>()
    private var finished = 0
    private val controller = Controller(
        LinkClient("k".repeat(43), server), { "2-3 교실" },
        { FakeSession().also { made += it } }, { now }, { "<svg>$it</svg>" }, { finished++ },
    )

    private fun at(y: Int, m: Int, d: Int, h: Int) =
        java.time.ZonedDateTime.of(y, m, d, h, 0, 0, 0, java.time.ZoneId.systemDefault()).toEpochSecond().toDouble()

    @Test
    fun sendsRpcShapeToPostgrest() {
        controller.step()
        val sent = server.raw.first()
        assertEquals("start", sent.getString("p_action"))
        assertEquals("k".repeat(43), sent.getString("p_device_key"))
        assertTrue(server.urls.first().endsWith("/rest/v1/rpc/classroom_device_call"))
    }

    @Test
    fun knownErrorInOkBodyGoesOffline() {
        server.reply(200, JSONObject().put("error", "rate_limited"))
        controller.step()
        assertEquals("offline", controller.state().getString("phase"))
        assertTrue(controller.state().getString("error").contains("자주"))
    }

    @Test
    fun sleepsAtNightAndWakesOnTouch() {
        now = at(2026, 11, 14, 22)                                 // 토요일 밤
        controller.wake()                                          // 켠 때부터 센다
        controller.step()                                          // QR
        now += Controller.AWAKE_OFF_HOURS + 1
        controller.step()
        assertEquals("sleep", controller.phase)
        assertEquals("end", server.calls.last().getString("action"))   // 떠 있던 QR 을 닫는다
        val before = server.calls.size
        repeat(5) { controller.step() }
        assertEquals(before, server.calls.size)                    // 쉬는 중에는 서버를 부르지 않는다
        controller.wake()
        assertEquals("qr", controller.phase)
        controller.step()
        assertEquals("start", server.calls.last().getString("action"))
    }

    @Test
    fun schoolHoursNeverSleepAndMorningWakes() {
        controller.step()
        now += 5 * 3600
        controller.step()
        assertEquals("qr", controller.phase)
        now = at(2026, 11, 12, 20)
        controller.step()
        assertEquals("sleep", controller.phase)
        now = at(2026, 11, 13, 7)
        controller.step()
        assertEquals("qr", controller.phase)
    }

    private fun iso(seconds: Double) = java.time.Instant.ofEpochMilli((seconds * 1000).toLong()).toString()

    private fun approve() {
        server.reply(200, JSONObject().put("code", "A".repeat(16)).put("expires_at", iso(now + 180)))
        controller.step()                                   // QR 만들기
        server.reply(200, JSONObject().put("status", "approved").put("ends_at", iso(now + 3000))
            .put("handoff", JSONObject().put("teacher", JSONObject().put("email", "t@myschool.hs.kr")).put("preset", JSONObject())))
        controller.step()                                   // 승인
    }

    @Test fun `처음엔 안드로이드로 QR 을 만든다`() {
        server.reply(200, JSONObject().put("code", "A".repeat(16)).put("expires_at", iso(now + 180)))
        controller.step()
        val start = server.calls.first()
        assertEquals("start", start.getString("action"))
        assertEquals("android", start.getString("platform"))
        assertEquals("2-3 교실", start.getString("name"))
        val state = controller.state()
        assertEquals("qr", state.getString("phase"))
        assertTrue(state.getString("qr").contains("/classroom/link/AAAAAAAAAAAAAAAA"))
        assertEquals(180, state.getInt("qr_left"))
    }

    @Test fun `승인되면 수업 — 아무것도 저절로 열지 않고 준비만`() {
        approve()
        assertEquals("session", controller.phase)
        assertTrue(made.single().prepared)
        assertEquals(3000, controller.state().getInt("remaining"))
    }

    @Test fun `거절되면 새 QR 과 알림`() {
        server.reply(200, JSONObject().put("code", "A".repeat(16)).put("expires_at", iso(now + 180)))
        controller.step()
        server.reply(200, JSONObject().put("status", "cancelled"))
        controller.step()
        assertEquals("휴대폰에서 연결을 거절했습니다.", controller.notice)
        server.reply(200, JSONObject().put("code", "B".repeat(16)).put("expires_at", iso(now + 180)))
        controller.step()
        assertEquals("start", server.calls.last().getString("action"))
    }

    @Test fun `서버에 닿지 않으면 offline 그리고 다시`() {
        server.fail = true
        assertEquals(Controller.RETRY_OFFLINE, controller.step(), 0.0)
        assertEquals("offline", controller.phase)
        assertTrue(controller.state().getString("error").contains("인터넷"))
        server.fail = false
        server.reply(200, JSONObject().put("code", "A".repeat(16)).put("expires_at", iso(now + 180)))
        controller.step()
        assertEquals("qr", controller.phase)
    }

    @Test fun `끝날 시각이 지나면 정리하고 서버에 알린다`() {
        approve()
        now += 3001
        controller.step()
        assertEquals("qr", controller.phase)
        assertTrue(made.single().ended)
        assertEquals("end", server.calls.last().getString("action"))
        assertEquals(1, finished)
        assertTrue(controller.notice.contains("정해 둔 시간"))
    }

    @Test fun `휴대폰에서 끝내면 서버에 다시 알리지 않는다`() {
        approve()
        now += Controller.POLL_SESSION + 1
        server.reply(200, JSONObject().put("status", "ended"))
        controller.step()
        assertEquals("qr", controller.phase)
        assertEquals("poll", server.calls.last().getString("action"))
        assertTrue(made.single().ended)
    }

    @Test fun `드라이브 다시 연결은 같은 선생님 것만 받는다`() {
        approve()
        server.reply(200, JSONObject().put("code", "D".repeat(16)).put("expires_at", iso(now + 180)))
        controller.driveReconnect()
        assertEquals("drive", server.calls.last().getString("purpose"))
        assertNotNull(controller.state().optJSONObject("drive_link"))
        server.reply(200, JSONObject().put("status", "approved").put("handoff", JSONObject()
            .put("teacher", JSONObject().put("email", "other@myschool.hs.kr"))
            .put("google", JSONObject().put("access_token", "x".repeat(30)))))
        controller.step()
        assertNull(made.single().google)
        assertTrue(controller.notice.contains("수업 중인 선생님이 아니라"))
        assertTrue(controller.state().isNull("drive_link"))

        server.reply(200, JSONObject().put("code", "E".repeat(16)).put("expires_at", iso(now + 180)))
        controller.driveReconnect()
        server.reply(200, JSONObject().put("status", "approved").put("handoff", JSONObject()
            .put("teacher", JSONObject().put("email", "t@myschool.hs.kr"))
            .put("google", JSONObject().put("access_token", "y".repeat(30)))))
        controller.step()
        assertEquals("y".repeat(30), made.single().google?.getString("access_token"))
        assertEquals("end", server.calls.last().getString("action"))       // 드라이브 QR 은 토큰만 받고 닫는다
    }

    @Test fun `이름을 바꾸면 QR 을 새 이름으로 다시 만든다`() {
        var name = "옛 이름"
        val c = Controller(LinkClient("k".repeat(43), server), { name }, { FakeSession() }, { now }, { "<svg>$it</svg>" })
        server.reply(200, JSONObject().put("code", "A".repeat(16)).put("expires_at", iso(now + 180)))
        c.step()
        assertEquals("옛 이름", server.calls.last().getString("name"))
        name = "2-3 교실"
        c.renewQr()
        assertEquals("", c.state().getString("qr"))                       // 옛 QR 은 바로 내린다
        server.reply(200, JSONObject().put("code", "B".repeat(16)).put("expires_at", iso(now + 180)))
        c.step()
        assertEquals("start", server.calls.last().getString("action"))
        assertEquals("2-3 교실", server.calls.last().getString("name"))
        assertTrue(c.state().getString("qr").contains("BBBBBBBBBBBBBBBB"))
    }

    @Test fun `수업 중에 이름을 바꿔도 수업은 그대로`() {
        approve()
        controller.renewQr()
        assertEquals("session", controller.phase)
    }

    @Test fun `연장하면 새 끝 시각`() {
        approve()
        server.reply(200, JSONObject().put("status", "active").put("ends_at", iso(now + 3600)))
        controller.extend(10)
        assertEquals(10, server.calls.last().getInt("minutes"))
        assertEquals(3600, controller.state().getInt("remaining"))
    }

    @Test fun `서버 오류 코드는 사람 말로`() {
        server.reply(429, JSONObject().put("error", "rate_limited"))
        controller.step()
        assertTrue(controller.state().getString("error").contains("너무 자주"))
    }

    @Test fun `시각 읽기`() {
        assertEquals(0.0, parseTime("1970-01-01T00:00:00+00:00")!!, 0.0)
        assertEquals(1.5, parseTime("1970-01-01T00:00:01.500000+00:00")!!, 0.0001)
        assertNull(parseTime(null))
        assertNull(parseTime("엉뚱"))
        assertFalse(parseTime("2026-10-14T07:40:00Z") == null)
    }
}
