package kr.hs.kijun.classroom

import android.content.Context
import android.os.Build
import android.provider.Settings
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * 이 기기의 연결 키 — 처음 켤 때 만든 임의 값. 안드로이드 키 저장소(AndroidKeyStore)의 AES 키로 감싸 앱 전용
 * 저장소에 둔다(Windows 판의 DPAPI 자리). 백업에서 빠진다(allowBackup=false). 풀리지 않으면 새로 만든다.
 */
object DeviceKey {
    private const val ALIAS = "spacekijun-classroom-device"
    private const val PREFS = "device"

    fun get(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        prefs.getString("key", null)?.let { stored ->
            runCatching { unwrap(stored) }.getOrNull()?.takeIf { it.length in 32..128 }?.let { return it }
        }
        val bytes = ByteArray(32).also { SecureRandom().nextBytes(it) }
        val key = Base64.encodeToString(bytes, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
        prefs.edit().putString("key", wrap(key)).apply()
        return key
    }

    private fun secret(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build()
        )
        return generator.generateKey()
    }

    // 키 저장소가 고장 난 기기(일부 칠판)는 앱 전용 저장소에 그대로 둔다 — 앱 밖에서는 읽을 수 없다
    private fun wrap(value: String): String = try {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, secret())
        "k:" + Base64.encodeToString(cipher.iv, Base64.NO_WRAP) + ":" +
            Base64.encodeToString(cipher.doFinal(value.toByteArray()), Base64.NO_WRAP)
    } catch (e: Exception) {
        "p:$value"
    }

    private fun unwrap(stored: String): String {
        if (stored.startsWith("p:")) return stored.substring(2)
        val parts = stored.split(":")
        require(parts.size == 3 && parts[0] == "k")
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, secret(), GCMParameterSpec(128, Base64.decode(parts[1], Base64.NO_WRAP)))
        return String(cipher.doFinal(Base64.decode(parts[2], Base64.NO_WRAP)))
    }
}

/** 이 기기 설정 — 기기 이름(교사 휴대폰에 보인다) */
class DevicePrefs(context: Context) {
    private val prefs = context.getSharedPreferences("settings", Context.MODE_PRIVATE)
    private val fallback: String = run {
        val named = runCatching { Settings.Global.getString(context.contentResolver, "device_name") }.getOrNull()
        (named?.takeIf { it.isNotBlank() } ?: "${Build.MANUFACTURER} ${Build.MODEL}").trim().ifEmpty { "전자칠판" }
    }

    var name: String
        get() = (prefs.getString("device_name", null)?.trim()?.takeIf { it.isNotEmpty() } ?: fallback).take(40)
        set(value) = prefs.edit().putString("device_name", value.trim().take(40)).apply()
}
