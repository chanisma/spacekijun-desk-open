package kr.hs.kijun.classroom

import android.database.sqlite.SQLiteDatabase
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.File

/** 보관본에 구글 로그인이 있나 — WebView 쿠키 DB 의 이름·만료만(android.database 라 Robolectric) */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class WebVaultCookieTest {
    @get:Rule val tmp = TemporaryFolder()

    private fun vaultWith(vararg rows: Pair<String, Long>): WebVault {
        val v = WebVault(tmp.root.resolve("data").apply { mkdirs() }, tmp.root.resolve("cache").apply { mkdirs() }, tmp.root.resolve("vault"))
        if (rows.isEmpty()) return v
        val db = File(v.live, "Default/Cookies").apply { parentFile!!.mkdirs() }
        SQLiteDatabase.openOrCreateDatabase(db, null).use { con ->
            con.execSQL("create table cookies (host_key text, name text, encrypted_value blob, expires_utc integer, has_expires integer)")
            for ((name, expires) in rows) {
                con.execSQL("insert into cookies values ('.google.com', ?, x'00', ?, 1)", arrayOf<Any>(name, expires))
            }
        }
        return v
    }

    private fun chrome(ms: Long) = (ms + WebVault.CHROME_EPOCH_MS) * 1000

    @Test fun `구글 SID 가 살아 있으면 true, 만료·다른 쿠키·DB 없음은 false`() {
        val now = System.currentTimeMillis()
        assertEquals(true, vaultWith("SID" to chrome(now + 86_400_000)).googleLoginIn(now))
        tmp.delete(); tmp.create()
        assertEquals(false, vaultWith("SID" to chrome(now - 60_000), "NID" to chrome(now + 86_400_000)).googleLoginIn(now))
        tmp.delete(); tmp.create()
        assertEquals(false, vaultWith().googleLoginIn(now))
    }

    @Test fun `읽을 수 없으면 모름(null)`() {
        val v = vaultWith()
        File(v.live, "Default/Cookies").apply { parentFile!!.mkdirs(); writeText("not a database") }
        assertNull(v.googleLoginIn())
    }
}
