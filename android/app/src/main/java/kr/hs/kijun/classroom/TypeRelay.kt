package kr.hs.kijun.classroom

import org.json.JSONObject
import java.math.BigInteger
import java.security.AlgorithmParameters
import java.security.KeyFactory
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.interfaces.ECPrivateKey
import java.security.interfaces.ECPublicKey
import java.security.spec.ECGenParameterSpec
import java.security.spec.ECParameterSpec
import java.security.spec.ECPoint
import java.security.spec.ECPrivateKeySpec
import java.security.spec.ECPublicKeySpec
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.KeyAgreement
import javax.crypto.Mac
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * 휴대폰으로 구글 비밀번호 입력(2026-10-14 사용자 결정) — 전자칠판 쪽. Windows 판 core/classroom_type.py 와 같은 규칙.
 *
 * 칠판에서 구글 비밀번호를 치면 학생들에게 보일 수 있어, 이 기기가 일회용 키(P-256)를 만들어 공개키를 QR 로 보이고,
 * 수업 중인 선생님 휴대폰이 그 공개키로 암호화해 보낸 것을 풀어 앱 안 브라우저의 구글 로그인 칸에 넣는다.
 * ECDH → HKDF-SHA256(salt = 표, info = INFO) → AES-256-GCM. 서버는 암호문만 맡았다 넘긴다. 비밀번호는 저장하지 않는다.
 */
class TypeKey private constructor(private val pair: KeyPair) {
    companion object {
        const val INFO = "spacekijun-classroom-type-v1"
        private val enc = Base64.getUrlEncoder().withoutPadding()
        private val dec = Base64.getUrlDecoder()

        private fun params(): ECParameterSpec = AlgorithmParameters.getInstance("EC").run {
            init(ECGenParameterSpec("secp256r1"))
            getParameterSpec(ECParameterSpec::class.java)
        }

        fun create(): TypeKey = TypeKey(KeyPairGenerator.getInstance("EC").run {
            initialize(ECGenParameterSpec("secp256r1"))
            generateKeyPair()
        })

        /** 시험용 — 정해 둔 비밀 키로 */
        fun fromHex(hex: String): TypeKey {
            val spec = params()
            val factory = KeyFactory.getInstance("EC")
            val d = BigInteger(hex, 16)
            val private = factory.generatePrivate(ECPrivateKeySpec(d, spec)) as ECPrivateKey
            // 공개키 = d·G — JDK 에는 점 곱셈이 드러나 있지 않아 공개키는 쓰지 않는 자리에만(시험은 open 만 본다)
            return TypeKey(KeyPair(null, private))
        }

        private fun fixed(value: BigInteger): ByteArray {
            val raw = value.toByteArray()
            return when {
                raw.size == 32 -> raw
                raw.size > 32 -> raw.copyOfRange(raw.size - 32, raw.size)
                else -> ByteArray(32 - raw.size) + raw
            }
        }

        private fun hkdf(secret: ByteArray, salt: ByteArray, info: ByteArray): ByteArray {
            val mac = Mac.getInstance("HmacSHA256")
            mac.init(SecretKeySpec(salt, "HmacSHA256"))
            val prk = mac.doFinal(secret)
            mac.init(SecretKeySpec(prk, "HmacSHA256"))
            mac.update(info)
            mac.update(1.toByte())
            return mac.doFinal().copyOf(32)
        }

        /** 구글 로그인 화면 한 단계를 채운다 → "password" · "email" · "chooser" · "none" (core/classroom_type.py fill_script 와 같다) */
        fun fillScript(email: String, password: String): String = """(function (email, pw) {
  var vis = function (e) { return !!e && e.offsetParent !== null; };
  var put = function (el, v) {
    var d = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    el.focus(); d.set.call(el, v);
    el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true }));
  };
  var click = function (sel) { var b = document.querySelector(sel); if (b) { b.click(); return true; } return false; };
  // 보이는 첫 칸 — 구글 로그인 화면에는 숨은 비밀번호 칸(hiddenPassword)이 앞에 있다
  var first = function (sels) {
    for (var i = 0; i < sels.length; i++) {
      var list = document.querySelectorAll(sels[i]);
      for (var j = 0; j < list.length; j++) if (vis(list[j])) return list[j];
    }
    return null;
  };
  var pass = first(['input[type=password][name=Passwd]', 'input[type=password]']);
  if (pass) {
    put(pass, pw);
    click('#passwordNext button') || click('#passwordNext') ||
      pass.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
    return 'password';
  }
  var acct = email && document.querySelector('[data-identifier="' + email + '"], [data-email="' + email + '"]');
  if (vis(acct)) { acct.click(); return 'chooser'; }
  // 이메일 칸은 type=text(name=identifier, id=identifierId)다 — 2026-10-14 실제 화면 확인. type=email 만 찾으면 못 찾는다
  var id = first(['#identifierId', 'input[name=identifier]', 'input[type=email]', 'input[autocomplete=username]']);
  if (id && (email || id.value)) {
    if (!id.value && email) put(id, email);
    click('#identifierNext button') || click('#identifierNext') ||
      id.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
    return 'email';
  }
  return 'none';
})(${JSONObject.quote(email)}, ${JSONObject.quote(password)})"""

        fun typeUrl(code: String, public: String) = "${Server.WEB}/classroom/type/$code#k=$public"
    }

    /** 공개키 — 압축하지 않은 점(0x04 · X · Y), base64url */
    val public: String
        get() {
            val w = (pair.public as ECPublicKey).w
            return enc.encodeToString(byteArrayOf(4) + fixed(w.affineX) + fixed(w.affineY))
        }

    /** 휴대폰이 봉한 것을 푼다 — 표(code)가 다르거나 손댔으면 예외 */
    fun open(code: String, payload: JSONObject): String {
        val epk = dec.decode(payload.getString("epk"))
        require(epk.size == 65 && epk[0] == 4.toByte()) { "공개키 모양이 다릅니다." }
        val point = ECPoint(BigInteger(1, epk.copyOfRange(1, 33)), BigInteger(1, epk.copyOfRange(33, 65)))
        val peer = KeyFactory.getInstance("EC").generatePublic(ECPublicKeySpec(point, (pair.private as ECPrivateKey).params))
        val agreement = KeyAgreement.getInstance("ECDH")
        agreement.init(pair.private)
        agreement.doPhase(peer, true)
        val key = hkdf(agreement.generateSecret(), code.toByteArray(Charsets.UTF_8), INFO.toByteArray(Charsets.UTF_8))
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(128, dec.decode(payload.getString("iv"))))
        return String(cipher.doFinal(dec.decode(payload.getString("ct"))), Charsets.UTF_8)
    }
}
