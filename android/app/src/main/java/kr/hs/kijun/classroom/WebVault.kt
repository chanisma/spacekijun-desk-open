package kr.hs.kijun.classroom

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.security.SecureRandom
import java.util.Base64
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * 앱 안 브라우저의 로그인 보관 — 구글·패들렛 같은 사이트 로그인을 이 칠판에 암호화해 남긴다(2026-10-14 사용자 결정 ①+②).
 * Windows 판 core/classroom_vault.py(A+)와 같은 방식·같은 파일 모양(SKV1 · 12바이트 nonce · AES-256-GCM(zip)).
 *
 *  · 앱 안 브라우저는 따로 도는 프로세스(:web)의 웹 데이터 폴더(app_webview_web)를 쓴다 — 수업마다 그 폴더를 바꿔 끼운다.
 *  · 수업 시작: 승인 때 서버가 준 열쇠(handoff.profile {ref, key})로 그 선생님 보관 파일을 풀어 폴더에 넣는다.
 *  · 수업 끝: 폴더를 묶어 잠가 vault/<ref>.bin 에 두고 폴더는 지운다. 열쇠가 없으면(보관 안 함) 지우기만.
 *  · 열쇠는 이 칠판에 없다 — 같은 선생님이 이 칠판에서 QR 로 승인할 때만 온다. 학생이 만져도 남은 것은 암호문뿐.
 */
class WebVault(private val dataDir: File, private val cacheDir: File, private val vaultDir: File) {
    companion object {
        private val MAGIC = "SKV1".toByteArray()
        private const val MAX_PLAIN = 150L * 1024 * 1024
        private const val KEEP_DAYS = 60L
        val REF = Regex("^[A-Za-z0-9_-]{16,64}$")
        /** 묶지 않는 것 — 다시 받으면 되는 캐시 */
        private val SKIP = setOf("Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache", "GrShaderCache",
            "ShaderCache", "CacheStorage", "ScriptCache", "blob_storage", "Crashpad", "BrowserMetrics")
        private val SKIP_FILES = setOf("lockfile", "LOCK", "SingletonLock", "SingletonCookie", "SingletonSocket")
        const val SUFFIX = "web"
        /** 1601-01-01 → 1970-01-01 (밀리초) — Chromium 쿠키 만료 시각의 기준 */
        const val CHROME_EPOCH_MS = 11_644_473_600_000L
    }

    /** 앱 안 브라우저(:web)가 쓰는 웹 데이터 폴더 */
    val live: File get() = File(dataDir, "app_webview_$SUFFIX")

    private fun key(keyB64: String): ByteArray {
        val key = runCatching { Base64.getDecoder().decode(keyB64) }.getOrNull()
        require(key != null && key.size == 32) { "보관 열쇠가 올바르지 않습니다." }
        return key
    }

    private fun blob(ref: String): File {
        require(REF.matches(ref)) { "보관 이름이 올바르지 않습니다." }
        return File(vaultDir, "$ref.bin")
    }

    /** 앱 안 브라우저의 데이터·캐시를 모두 지운다(:web 프로세스가 꺼져 있을 때) */
    fun wipe() {
        live.deleteRecursively()
        cacheDir.listFiles()?.filter { it.name.startsWith("WebView") && it.name.contains(SUFFIX) }?.forEach { it.deleteRecursively() }
    }

    private fun pack(folder: File): ByteArray {
        val out = ByteArrayOutputStream()
        var total = 0L
        ZipOutputStream(out).use { zip ->
            folder.walkTopDown().onEnter { it == folder || it.name !in SKIP }.filter { it.isFile && it.name !in SKIP_FILES }.forEach { file ->
                total += file.length()
                if (total > MAX_PLAIN) throw IllegalStateException("보관할 것이 너무 큽니다.")
                zip.putNextEntry(ZipEntry(file.relativeTo(folder).invariantSeparatorsPath))
                file.inputStream().use { it.copyTo(zip) }
                zip.closeEntry()
            }
        }
        return out.toByteArray()
    }

    /** 지금 브라우저 데이터를 잠가 둔다 → 보관 크기(바이트) */
    fun save(ref: String, keyB64: String): Int {
        val plain = pack(live)
        val nonce = ByteArray(12).also { SecureRandom().nextBytes(it) }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key(keyB64), "AES"), GCMParameterSpec(128, nonce))
        val sealed = MAGIC + nonce + cipher.doFinal(plain)
        vaultDir.mkdirs()
        val target = blob(ref)
        val temp = File(vaultDir, "$ref.tmp")
        temp.writeBytes(sealed)
        if (!temp.renameTo(target)) { target.delete(); temp.renameTo(target) }
        return sealed.size
    }

    /** 보관 파일을 풀어 브라우저 데이터 폴더에 넣는다 → 풀었으면 true. 열쇠가 맞지 않으면 보관 파일을 지우고 false */
    fun restore(ref: String, keyB64: String): Boolean {
        val file = blob(ref)
        if (!file.exists()) return false
        val data = file.readBytes()
        val plain = try {
            require(data.size > 16 && data.copyOfRange(0, 4).contentEquals(MAGIC))
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(key(keyB64), "AES"), GCMParameterSpec(128, data.copyOfRange(4, 16)))
            cipher.doFinal(data, 16, data.size - 16)
        } catch (e: Exception) {
            file.delete()                         // 열쇠가 바뀌었다(선생님이 지움 등) — 빈 브라우저로
            return false
        }
        live.deleteRecursively()
        live.mkdirs()
        val root = live.canonicalFile
        ZipInputStream(ByteArrayInputStream(plain)).use { zip ->
            while (true) {
                val entry = zip.nextEntry ?: break
                val out = File(root, entry.name).canonicalFile
                if (!out.path.startsWith(root.path + File.separator)) continue      // 폴더 밖으로 나가는 이름은 버린다
                if (entry.isDirectory) { out.mkdirs(); continue }
                out.parentFile?.mkdirs()
                out.outputStream().use { zip.copyTo(it) }
            }
        }
        file.setLastModified(System.currentTimeMillis())
        return true
    }

    /** 앱 안 브라우저 데이터에 구글 로그인 쿠키(SID 등)가 있나 — 이름·만료만, 값은 안 읽는다. :web 이 꺼져 있을 때만. 모르면 null */
    fun googleLoginIn(now: Long = System.currentTimeMillis()): Boolean? {
        val db = listOf(File(live, "Default/Cookies"), File(live, "Cookies")).firstOrNull { it.exists() } ?: return false
        return try {
            android.database.sqlite.SQLiteDatabase.openDatabase(db.path, null, android.database.sqlite.SQLiteDatabase.OPEN_READONLY).use { con ->
                con.rawQuery("select expires_utc, has_expires from cookies where host_key = '.google.com' and name in ('SID','__Secure-1PSID','__Secure-3PSID')",
                    null).use { c ->
                    var found = false
                    while (c.moveToNext()) {
                        if (c.getInt(1) == 0 || c.getLong(0) / 1000 - CHROME_EPOCH_MS > now) found = true
                    }
                    found
                }
            }
        } catch (e: Exception) {
            null
        }
    }

    fun forget(ref: String) {
        runCatching { blob(ref).delete() }
    }

    /** 60일 넘게 안 쓴 보관 파일은 지운다 */
    fun sweep(now: Long = System.currentTimeMillis()) {
        vaultDir.listFiles()?.filter { now - it.lastModified() > KEEP_DAYS * 86_400_000L }?.forEach { it.delete() }
    }
}
