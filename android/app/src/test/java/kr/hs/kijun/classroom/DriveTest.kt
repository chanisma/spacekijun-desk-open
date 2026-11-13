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
import java.io.InputStream

/** 드라이브 API 흉내 — 요청을 적어 두고 길(경로)마다 답한다 */
class FakeDrive : DriveHttp {
    data class Call(val url: String, val method: String, val headers: Map<String, String>, val body: ByteArray?)
    val calls = mutableListOf<Call>()
    val files = mutableMapOf<String, Pair<JSONObject, ByteArray>>()
    var status = 200

    override fun request(url: String, method: String, headers: Map<String, String>, body: ByteArray?,
                         sink: (Int, InputStream) -> Unit): Pair<Int, String?> {
        calls += Call(url, method, headers, body)
        if (status != 200) { sink(status, "{\"error\":{\"message\":\"insufficient scope\"}}".byteInputStream()); return status to null }
        val path = url.substringBefore('?')
        return when {
            url.contains("/upload/drive/") && method != "PUT" -> { sink(200, "".byteInputStream()); 200 to "https://upload.example/session/1" }
            method == "PUT" -> { sink(200, "{\"id\":\"new-id\"}".byteInputStream()); 200 to null }
            path.endsWith("/export") || url.contains("alt=media") -> {
                val id = path.substringAfter("/files/").substringBefore('/')
                sink(200, files.getValue(id).second.inputStream()); 200 to null
            }
            method == "POST" && path.endsWith("/files") -> { sink(200, "{\"id\":\"folder-id\"}".byteInputStream()); 200 to null }
            path.contains("/files/") -> {
                val id = path.substringAfter("/files/")
                sink(200, files.getValue(id).first.toString().byteInputStream()); 200 to null
            }
            else -> { sink(200, "{\"files\":[]}".byteInputStream()); 200 to null }
        }
    }
}

class DriveTest {
    @get:Rule val tmp = TemporaryFolder()
    private var now = 100.0
    private val launched = mutableListOf<File>()

    private fun workspace(http: FakeDrive, token: String? = "tok") =
        Workspace(tmp.newFolder("drive"), { token }, { f, _ -> launched += f }, http, { now })

    @Test fun `받아 열고 바뀌면 같은 파일에 새 판으로 올린다`() {
        val http = FakeDrive()
        http.files["f1"] = JSONObject().put("id", "f1").put("name", "수업.pptx").put("mimeType", "application/x").put("parents", JSONArray().put("p1")) to "v1".toByteArray()
        val ws = workspace(http)
        val file = ws.open("f1")
        assertEquals("수업.pptx", file.name)
        assertEquals(file, launched.single())
        assertEquals(0, ws.sync())                     // 그대로면 올리지 않는다

        file.writeText("v2-고침")
        file.setLastModified(file.lastModified() + 5000)
        assertEquals(0, ws.sync())                     // 바뀐 것을 처음 봤다 — 2초 기다린다
        now += 3
        assertEquals(1, ws.sync())
        val init = http.calls.first { it.url.contains("/upload/drive/") && it.method == "PATCH" }
        assertTrue(init.url.contains("/files/f1?uploadType=resumable"))
        assertEquals(String(http.calls.last().body!!), "v2-고침")
        assertEquals(0, ws.sync())
    }

    @Test fun `구글 문서는 바꿔 받고 고친 것은 새 파일로`() {
        val http = FakeDrive()
        http.files["d1"] = JSONObject().put("id", "d1").put("name", "학습지").put("mimeType", "application/vnd.google-apps.document") to "docx".toByteArray()
        val ws = workspace(http)
        val file = ws.open("d1")
        assertEquals("학습지.docx", file.name)
        assertTrue(http.calls.any { it.url.contains("/files/d1/export?mimeType=application%2Fvnd.openxmlformats") })
        file.writeText("고침")
        file.setLastModified(file.lastModified() + 5000)
        assertEquals(1, ws.sync(final = true))
        val made = http.calls.first { it.url.contains("/upload/drive/") && it.method == "POST" }
        assertTrue(String(made.body!!).contains("학습지 (교실에서 고침).docx"))
        assertEquals("new-id", ws.snapshot().getJSONObject(0).getString("upload_id"))
    }

    @Test fun `토큰이 끝나면 못 올린 것을 남겼다가 다음에 올린다`() {
        val http = FakeDrive()
        http.files["f1"] = JSONObject().put("id", "f1").put("name", "a.txt").put("mimeType", "text/plain") to "a".toByteArray()
        var token: String? = "tok"
        val ws = Workspace(tmp.newFolder("d2"), { token }, { _, _ -> }, http, { now })
        val file = ws.open("f1")
        file.writeText("고침")
        file.setLastModified(file.lastModified() + 5000)
        token = null
        assertEquals(0, ws.sync(final = true))
        assertEquals("failed", ws.snapshot().getJSONObject(0).getString("state"))
        val box = UnsentBox(tmp.newFolder("unsent"))
        assertEquals(1, ws.stashUnsent(box, "T@myschool.hs.kr"))
        assertTrue(box.has("t@myschool.hs.kr"))           // 대소문자·공백은 같은 선생님
        assertFalse(box.has("other@myschool.hs.kr"))
        assertEquals(1, box.send(Drive("tok", http), "t@myschool.hs.kr"))
        assertFalse(box.has("t@myschool.hs.kr"))
    }

    @Test fun `권한 오류는 다시 연결하라고`() {
        val http = FakeDrive().apply { status = 403 }
        val error = runCatching { Drive("tok", http).list() }.exceptionOrNull() as DriveError
        assertTrue(error.auth)
        assertTrue(error.message!!.contains("전체 권한"))
    }

    @Test fun `파일 이름 다듬기`() {
        assertEquals("a_b_c.docx", safeName("a/b:c", ".docx"))
        assertEquals("파일", safeName("  .. "))
        assertEquals("application/pdf", mimeOf("x.PDF"))
    }

    @Test fun `QR 은 SVG`() {
        val svg = Qr.svg("https://spacekijun.lovable.app/classroom/link/ABCDEFGHIJKLMNOP")
        assertTrue(svg.startsWith("<svg") && svg.contains("class=\"segno\"") && svg.contains("<path"))
    }
}
