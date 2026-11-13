package kr.hs.kijun.classroom

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class FakeHost : Host {
    val opened = mutableListOf<String>()
    val web = mutableListOf<String>()
    override fun prepareWeb(profile: JSONObject?): Boolean { web += "prepare:" + profile?.optString("ref"); return profile != null }
    override fun finishWeb(profile: JSONObject?) { web += "finish:" + profile?.optString("ref") }
    override fun forgetWeb(ref: String?) { web += "forget:$ref" }
    override fun webVaultSupported() = true
    override fun openWeb(url: String, title: String, space: JSONObject?) { opened += url }
    override fun launchProgram(key: String): String? = null
    override fun clearWeb() {}
    override fun hasProgram(key: String) = key != "excel"
    override fun launch(file: File, mime: String) {}
}

class SessionTest {
    @get:Rule val tmp = TemporaryFolder()

    private fun session(preset: JSONObject) = Session(
        JSONObject().put("preset", preset).put("teacher", JSONObject().put("name", "권민결").put("email", "t@myschool.hs.kr")),
        FakeHost(), tmp.newFolder("s"), UnsentBox(tmp.newFolder("u")))

    @Test fun `로그인 보관 — 시작에 풀고 끝에 잠그고, 지운 뒤 다시 로그인하면 또 보관`() {
        val host = FakeHost()
        val profile = JSONObject().put("ref", "ref_0123456789abcdef").put("key", "a2V5")
        val s = Session(JSONObject().put("preset", JSONObject().put("title", "t")).put("profile", profile)
            .put("teacher", JSONObject().put("email", "t@myschool.hs.kr")), host, tmp.newFolder("s2"), UnsentBox(tmp.newFolder("u2")))
        s.prepare()
        assertEquals(listOf("prepare:ref_0123456789abcdef"), host.web)
        val login = s.snapshot().getJSONObject("login")
        assertTrue(login.getBoolean("kept") && login.getBoolean("restored"))
        s.end { }
        assertEquals("finish:ref_0123456789abcdef", host.web.last())
        s.forgetLogin()
        assertEquals("forget:ref_0123456789abcdef", host.web.last())
        val after = s.snapshot().getJSONObject("login")
        assertTrue(after.getBoolean("kept") && after.getBoolean("cleared"))   // 보관은 그대로 — 1.3.0 까지는 꺼서 다시 한 로그인이 사라졌다
        s.end { }
        assertEquals("finish:ref_0123456789abcdef", host.web.last())         // 지운 뒤 한 로그인도 잠가 둔다
    }

    @Test fun `보관 열쇠가 없으면 끝에 지우기만`() {
        val host = FakeHost()
        val s = Session(JSONObject().put("preset", JSONObject().put("title", "t")), host, tmp.newFolder("s3"), UnsentBox(tmp.newFolder("u3")))
        s.prepare()
        s.end { }
        assertEquals(listOf("prepare:null", "finish:null"), host.web)
    }

    @Test fun `반이 없는 세팅은 null 글자가 아니라 빈 값`() {
        val snap = session(JSONObject().put("title", "테스트").put("section_name", JSONObject.NULL).put("items", JSONArray())).snapshot()
        assertEquals("", snap.getString("section"))
        assertEquals("테스트", snap.getString("title"))
    }

    @Test fun `항목의 빈 값도 null 글자가 되지 않는다`() {
        val item = JSONObject().put("kind", "url").put("url", "https://padlet.com/").put("name", "패들렛").put("site", JSONObject.NULL)
        val snap = session(JSONObject().put("title", "t").put("items", JSONArray().put(item))).snapshot()
        assertEquals("", snap.getJSONArray("items").getJSONObject(0).getString("site"))
    }

    @Test fun `이 칠판에 없는 프로그램은 흐리게 표시할 수 있게`() {
        val items = JSONArray().put(JSONObject().put("kind", "program").put("program", "excel").put("name", "Excel"))
            .put(JSONObject().put("kind", "program").put("program", "powerpoint").put("name", "PowerPoint"))
        val list = session(JSONObject().put("title", "t").put("items", items)).snapshot().getJSONArray("items")
        assertFalse(list.getJSONObject(0).getBoolean("available"))
        assertTrue(list.getJSONObject(1).getBoolean("available"))
    }
}
