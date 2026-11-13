package kr.hs.kijun.classroom

import android.content.Intent
import android.os.Looper
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import java.util.concurrent.TimeUnit

/** 시험에서는 흐름 바퀴를 돌리지 않는다(진짜 서버에 QR 을 만들지 않게) */
class TestApp : ClassroomApp() {
    override fun startLoop() {}
}

/** 에뮬레이터 없이 앱을 띄워 본다 — 시작·QR 화면·다리·앱 안 브라우저가 죽지 않는지 */
@RunWith(org.robolectric.RobolectricTestRunner::class)
@Config(sdk = [34], application = TestApp::class)
class AppSmokeTest {

    @Test fun `앱이 뜨고 화면이 앱 안 HTML 을 연다`() {
        val activity = Robolectric.buildActivity(MainActivity::class.java).setup().get()
        val web = shadowOf(activity.web)
        assertEquals(MainActivity.PAGE, web.lastLoadedUrl)
        assertNotNull(web.getJavascriptInterface("AndroidBridge"))
    }

    @Test fun `다리 — 상태·설정·세팅 QR 이 JSON 으로 돌아온다`() {
        val activity = Robolectric.buildActivity(MainActivity::class.java).setup().get()
        val bridge = shadowOf(activity.web).getJavascriptInterface("AndroidBridge") as Bridge
        for ((id, method) in listOf("1" to "state", "2" to "settings", "3" to "setup_qr", "4" to "모르는것")) {
            bridge.invoke(id, method, "[]")
        }
        val app = RuntimeEnvironment.getApplication() as ClassroomApp
        app.executor.shutdown()
        assertTrue(app.executor.awaitTermination(10, TimeUnit.SECONDS))
        shadowOf(Looper.getMainLooper()).idle()
        val js = shadowOf(activity.web).lastEvaluatedJavascript
        assertTrue(js, js.startsWith("window.__bridgeDone"))
    }

    @Test fun `상태에는 phase 와 기기 이름`() {
        val app = RuntimeEnvironment.getApplication() as ClassroomApp
        val state = app.controller.state()
        assertEquals("qr", state.getString("phase"))
        assertTrue(state.getString("device").isNotBlank())
        assertTrue(DeviceKey.get(app).length in 32..128)
        assertEquals(DeviceKey.get(app), DeviceKey.get(app))           // 한 번 만든 키를 그대로
    }

    @Test fun `앱 안 브라우저 — 스페이스기전은 첫 화면에서 로그인을 심고 간다`() {
        val ticket = BrowserActivity.holdSpace(RuntimeEnvironment.getApplication(), JSONObject().put("access_token", "a.b.c"))
        val intent = Intent(RuntimeEnvironment.getApplication(), BrowserActivity::class.java)
            .putExtra(BrowserActivity.EXTRA_URL, Server.WEB + "/timetable")
            .putExtra(BrowserActivity.EXTRA_TITLE, "시간표")
            .putExtra(BrowserActivity.EXTRA_SPACE, ticket)
        val browser = Robolectric.buildActivity(BrowserActivity::class.java, intent).setup().get()
        assertFalse(browser.isFinishing)
        BrowserActivity.finishAll()
        assertTrue(browser.isFinishing)
    }

    @Test fun `로그인 심기 스크립트는 정해 둔 출처에서만`() {
        val script = BrowserActivity.installScript(JSONObject().put("access_token", "x"))
        assertTrue(script.contains("location.origin !== p.origin"))
        assertTrue(script.contains(Server.STORAGE_KEY))
    }
}
