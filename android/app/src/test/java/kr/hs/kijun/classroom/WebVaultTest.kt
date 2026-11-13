package kr.hs.kijun.classroom

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.Base64
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

class WebVaultTest {
    @get:Rule val tmp = TemporaryFolder()
    private val key = Base64.getEncoder().encodeToString(ByteArray(32) { it.toByte() })
    private val ref = "ref_0123456789abcdef"

    private fun vault() = WebVault(tmp.root.resolve("data").apply { mkdirs() }, tmp.root.resolve("cache").apply { mkdirs() },
        tmp.root.resolve("vault"))

    @Test fun `잠가 두었다 풀면 쿠키·저장소가 그대로, 캐시는 빠진다`() {
        val v = vault()
        File(v.live, "Default").mkdirs()
        File(v.live, "Default/Cookies").writeText("padlet_session=abc")
        File(v.live, "Default/Local Storage/leveldb").mkdirs()
        File(v.live, "Default/Local Storage/leveldb/000003.log").writeText("ls")
        File(v.live, "Default/Cache/data_0").apply { parentFile!!.mkdirs(); writeText("big cache") }
        File(v.live, "lockfile").writeText("")
        v.save(ref, key)
        v.wipe()
        assertFalse(v.live.exists())
        assertTrue(v.restore(ref, key))
        assertEquals("padlet_session=abc", File(v.live, "Default/Cookies").readText())
        assertEquals("ls", File(v.live, "Default/Local Storage/leveldb/000003.log").readText())
        assertFalse(File(v.live, "Default/Cache/data_0").exists())
        assertFalse(File(v.live, "lockfile").exists())
    }

    @Test fun `보관 파일에는 평문이 없다`() {
        val v = vault()
        File(v.live, "Default").mkdirs()
        File(v.live, "Default/Cookies").writeText("secret_cookie_value")
        v.save(ref, key)
        val blob = File(tmp.root, "vault/$ref.bin").readBytes()
        assertFalse(String(blob, Charsets.ISO_8859_1).contains("secret_cookie_value"))
    }

    @Test fun `열쇠가 다르면 보관 파일을 지우고 빈 브라우저로`() {
        val v = vault()
        File(v.live, "x").apply { parentFile!!.mkdirs(); writeText("1") }
        v.save(ref, key)
        val other = Base64.getEncoder().encodeToString(ByteArray(32) { 7 })
        assertFalse(v.restore(ref, other))
        assertFalse(File(tmp.root, "vault/$ref.bin").exists())
    }

    @Test fun `폴더 밖으로 나가는 이름은 풀지 않는다`() {
        val v = vault()
        val zip = ByteArrayOutputStream()
        ZipOutputStream(zip).use { z -> z.putNextEntry(ZipEntry("../../evil.txt")); z.write("x".toByteArray()); z.closeEntry() }
        // 같은 열쇠로 잠근 악의적인 묶음
        val nonce = ByteArray(12)
        val cipher = javax.crypto.Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(javax.crypto.Cipher.ENCRYPT_MODE, javax.crypto.spec.SecretKeySpec(Base64.getDecoder().decode(key), "AES"),
            javax.crypto.spec.GCMParameterSpec(128, nonce))
        File(tmp.root, "vault").mkdirs()
        File(tmp.root, "vault/$ref.bin").writeBytes("SKV1".toByteArray() + nonce + cipher.doFinal(zip.toByteArray()))
        assertTrue(v.restore(ref, key))
        assertFalse(File(tmp.root, "evil.txt").exists())
        assertFalse(File(tmp.root.resolve("data"), "evil.txt").exists())
    }

    @Test fun `이상한 보관 이름은 거절`() {
        assertTrue(runCatching { vault().save("../x", key) }.isFailure)
    }
}
