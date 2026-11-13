package kr.hs.kijun.classroom

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GoogleApiTest {
    @Test fun `허용한 주소만 — 쓰기는 클래스룸 공지 하나`() {
        val ok = listOf(
            "GET" to "https://classroom.googleapis.com/v1/courses?teacherId=me",
            "GET" to "https://forms.googleapis.com/v1/forms/abc/responses?pageSize=5000",
            "GET" to "https://classroom.googleapis.com/v1/userProfiles/me",
            "GET" to "https://slides.googleapis.com/v1/presentations/abc/pages/p1/thumbnail?thumbnailProperties.thumbnailSize=LARGE",
            "GET" to "https://www.googleapis.com/drive/v3/files?q=x",
            "POST" to "https://classroom.googleapis.com/v1/courses/123/announcements",
        )
        val bad = listOf(
            "DELETE" to "https://classroom.googleapis.com/v1/courses/123",
            "POST" to "https://classroom.googleapis.com/v1/courses/123/courseWork",
            "GET" to "https://www.googleapis.com/drive/v3/files/abc?alt=media",
            "GET" to "https://evil.example/v1/courses",
            "GET" to "https://classroom.googleapis.com/v1/courses/../../x",
        )
        ok.forEach { (m, u) -> assertTrue(u, GoogleApi.allowed(m, u)) }
        bad.forEach { (m, u) -> assertFalse(u, GoogleApi.allowed(m, u)) }
    }

    @Test fun `오류는 이유로 — 토큰은 싣지 않는다`() {
        val url = "https://slides.googleapis.com/v1/presentations/x"
        val cases = listOf(401 to "" to "auth", 403 to "SERVICE_DISABLED" to "disabled",
            403 to "ACCESS_TOKEN_SCOPE_INSUFFICIENT" to "scope", 404 to "" to "notfound")
        for ((pair, reason) in cases) {
            val r = GoogleApi.call("tok", "GET", url, null) { _, _, _, _ -> pair }
            assertEquals(reason, r.getString("reason"))
            assertFalse(r.toString().contains("tok"))
        }
        assertEquals("Google Slides", GoogleApi.explain(403, "SERVICE_DISABLED", url).getString("api"))
        assertEquals("auth", GoogleApi.call(null, "GET", url, null).getString("reason"))
    }

    @Test fun `공지는 글과 게시 상태만 보낸다`() {
        var sent = ""
        val r = GoogleApi.call("tok", "POST", "https://classroom.googleapis.com/v1/courses/1/announcements",
            JSONObject().put("text", "내일 준비물").put("state", "DRAFT").put("assigneeMode", "INDIVIDUAL_STUDENTS")) { _, _, _, body ->
            sent = body.orEmpty(); 200 to "{\"id\":\"1\"}"
        }
        assertTrue(r.getBoolean("ok"))
        val body = JSONObject(sent)
        assertEquals("내일 준비물", body.getString("text"))
        assertEquals("PUBLISHED", body.getString("state"))
        assertFalse(body.has("assigneeMode"))
    }
}
