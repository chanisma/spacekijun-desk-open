package kr.hs.kijun.classroom

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TypeKeyTest {
    // spacekijun 의 sealForDevice(웹 휴대폰 화면)로 만든 표본 — Windows 판 시험과 같다
    private val vector = JSONObject("""{"priv":"7d1c3a5e9b2f4c6d8e0a1b3c5d7e9f0a2b4c6d8e0f1a3b5c7d9e1f3a5b7c9d1e",
        "code":"VectorCode_0123456789ab",
        "epk":"BIsxg7G8hIm1CoEUC1apS_z13nE-Dh2wuG3G24Vp4IwA_jMGqHPIhBmoSVk-GZGAJG0woXe1fCrEZVlt3wLIsa0",
        "iv":"rmsR6qwD7EyRMwGa","ct":"Smt5pvsOkYMHL2zcMc6BT85f8RHxIXRmvfEE4qdZWDKKMdTi7AzRVrg"}""")

    @Test fun `휴대폰이 봉한 것을 푼다`() {
        val key = TypeKey.fromHex(vector.getString("priv"))
        assertEquals("교실 비밀번호 P@ss!", key.open(vector.getString("code"), vector))
    }

    @Test fun `표가 다르면 풀리지 않는다`() {
        val key = TypeKey.fromHex(vector.getString("priv"))
        assertTrue(runCatching { key.open("other-code", vector) }.isFailure)
    }

    @Test fun `새 키의 공개키는 65바이트 점`() {
        val pub = TypeKey.create().public
        assertEquals(65, java.util.Base64.getUrlDecoder().decode(pub).size)
        assertTrue(TypeKey.typeUrl("abc", pub).endsWith("#k=$pub"))
    }

    @Test fun `채우기 스크립트는 값을 문자열로만`() {
        val js = TypeKey.fillScript("t@myschool.hs.kr", "a\"b\\c'</script>")
        assertTrue(js.contains(JSONObject.quote("a\"b\\c'</script>")))
    }

    @Test fun `구글 이메일 칸은 type=text(identifierId) — type=email 만 찾으면 못 넘긴다`() {
        val js = TypeKey.fillScript("t@myschool.hs.kr", "x")
        assertTrue(js.contains("#identifierId") && js.contains("input[name=identifier]"))
        assertTrue(js.contains("first(['input[type=password][name=Passwd]'"))      // 숨은 hiddenPassword 말고 보이는 칸
    }
}
