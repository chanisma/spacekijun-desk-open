package kr.hs.kijun.classroom

import android.content.Intent
import android.net.Uri
import android.provider.DocumentsContract
import android.provider.OpenableColumns
import android.provider.Settings
import android.webkit.JavascriptInterface
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID
import kotlin.system.exitProcess

/**
 * 화면(assets/web/board.js) ↔ 앱. 화면은 `AndroidBridge.invoke(id, 이름, 인자 JSON)` 로 부르고,
 * 결과는 `window.__bridgeDone(id, 결과)` 로 돌아온다(일은 모두 일꾼 스레드에서 — 화면이 멈추지 않게).
 * 이 화면은 앱 안 HTML 만 연다(MainActivity) — 바깥 웹페이지는 이 다리를 받지 못한다.
 */
class Bridge(private val activity: MainActivity) {
    private val app = activity.classroom
    private val controller get() = app.controller

    @JavascriptInterface
    fun invoke(id: String, method: String, args: String) {
        app.executor.execute {
            val result = try {
                encode(call(method, JSONArray(args.ifEmpty { "[]" })))
            } catch (e: Exception) {
                JSONObject().put("ok", false).put("error", e.message ?: "처리하지 못했습니다.")
                    .put("auth", (e as? DriveError)?.auth == true).toString()
            }
            activity.deliver(id, result)
        }
    }

    private fun encode(value: Any?): String = when (value) {
        null, Unit -> "null"
        is String -> JSONObject.quote(value)
        is JSONObject, is JSONArray, is Boolean, is Number -> value.toString()
        else -> JSONObject.quote(value.toString())
    }

    private fun ok() = JSONObject().put("ok", true)
    private fun session(): Session = controller.session as? Session ?: throw IllegalStateException("수업 중이 아닙니다.")

    private fun call(method: String, a: JSONArray): Any? = when (method) {
        "state" -> controller.state().put("update", updateInfo())
        "settings" -> settings()
        "save_name" -> {
            a.optString(0).trim().takeIf { it.isNotEmpty() }?.let {
                app.prefs.name = it
                controller.renewQr()                 // 떠 있는 QR 은 옛 이름 — 새 이름으로 다시(Windows 판 save_name 과 같다)
            }
            ok().put("device_name", app.prefs.name)
        }
        "open_overlay_settings" -> {
            activity.startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + activity.packageName)))
            ok()
        }
        "setup_qr" -> Qr.svg(Server.SETUP)
        "wake" -> { controller.wake(); ok() }
        "check_update" -> {
            val found = app.updater.checkAndDownload()
            ok().put("version", found?.optString("version") ?: JSONObject.NULL)
        }
        "install_update" -> ok().put("message", onMain { app.updater.install(activity) })
        "quit" -> {
            if (controller.phase == "session") controller.finish("앱을 끝내며 수업을 정리했습니다.")
            activity.runOnUiThread { activity.finishAndRemoveTask() }
            Thread.sleep(400)
            exitProcess(0)
        }

        // 수업 ------------------------------------------------------------------
        "open_item" -> session().openItem(a.optInt(0, -1))
        "open_google_app" -> session().openGoogleApp(a.optString(0))
        "extend" -> { controller.extend(a.optInt(0, 10)); ok() }
        "finish" -> { controller.finish("수업을 끝냈습니다."); ok() }
        "drive_reconnect" -> { controller.driveReconnect(); ok() }
        "drive_reconnect_cancel" -> { controller.driveReconnectCancel(); ok() }

        "forget_login" -> {
            // 이 칠판의 로그인 지우기 — 지금 것·보관본. 서버 열쇠는 둔다(다시 로그인하면 끝날 때 새로 보관, 끄기는 승인 화면)
            session().forgetLogin()
            ok()
        }

        // 구글 수업 도구(gtools.js) — 클래스룸·슬라이드 발표·설문지를 로그인 없이 --------------------
        "google_api" -> GoogleApi.call(session().googleToken(), a.optString(0, "GET"), a.optString(1), a.optJSONObject(2))
        "qr_svg" -> a.optString(0).takeIf { it.startsWith("https://") }?.let { Qr.svg(it) } ?: ""
        "open_web" -> {
            val url = a.optString(0)
            if (!url.startsWith("https://")) throw IllegalArgumentException("열 수 없는 주소입니다.")
            app.host.openWeb(url, a.optString(1).ifEmpty { "웹" })
            ok()
        }

        // 드라이브 탐색기 ---------------------------------------------------------
        "drive_start" -> session().let { s ->
            ok().put("email", s.email).put("drive", s.driveState())
        }
        "drive_list" -> {
            val files = session().workspace.drive().list(a.optString(0, "root"), a.optString(1).ifEmpty { null })
            ok().put("files", JSONArray(files))
        }
        "drive_shared_drives" -> ok().put("drives", JSONArray(session().workspace.drive().sharedDrives()))
        "drive_open" -> { session().workspace.open(a.optString(0)); ok() }
        "drive_mkdir" -> ok().put("folder", session().workspace.drive().createFolder(a.optString(1).trim().ifEmpty { "새 폴더" }, a.optString(0, "root")))
        "drive_upload" -> upload(a.optString(0, "root"))
        "drive_save" -> saveToDevice(a.optJSONArray(0) ?: JSONArray())
        else -> throw IllegalArgumentException("모르는 요청입니다: $method")
    }

    private fun updateInfo(): Any {
        val ready = app.updater.ready ?: return JSONObject.NULL
        return JSONObject().put("version", app.updater.latest?.optString("version") ?: ready.name)
    }

    private fun settings(): JSONObject {
        // 칠판의 웹 엔진(Android System WebView) — 오래되면 요즘 사이트가 깨진다
        val engine = runCatching { android.webkit.WebView.getCurrentWebViewPackage()?.versionName }.getOrNull().orEmpty()
        return JSONObject().put("device_name", app.prefs.name).put("overlay", Settings.canDrawOverlays(activity))
            .put("version", BuildConfig.VERSION_NAME).put("update", updateInfo()).put("webview", engine)
    }

    private fun displayName(uri: Uri): String =
        activity.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        } ?: (uri.lastPathSegment ?: "파일")

    /** 이 기기의 파일을 드라이브의 지금 폴더로 올린다 */
    private fun upload(parent: String): JSONObject {
        val s = session()
        val drive = s.workspace.drive()
        val uris = activity.pickFiles()
        var sent = 0
        val errors = JSONArray()
        for (uri in uris) {
            val name = displayName(uri)
            val temp = File(File(s.dir, "upload/" + UUID.randomUUID().toString().take(8)).apply { mkdirs() }, safeName(name))
            try {
                activity.contentResolver.openInputStream(uri)?.use { input -> temp.outputStream().use { input.copyTo(it) } }
                    ?: throw DriveError("파일을 읽지 못했습니다.")
                drive.uploadNew(temp, parent, name)
                sent++
            } catch (e: Exception) {
                errors.put("$name: ${e.message}")
            } finally {
                temp.parentFile?.deleteRecursively()
            }
        }
        return ok().put("count", sent).put("errors", errors)
    }

    /** 고른 드라이브 항목(파일·폴더)을 선생님이 고른 이 기기의 폴더로 — 수업이 끝나도 지우지 않는다 */
    private fun saveToDevice(items: JSONArray): JSONObject {
        val s = session()
        val drive = s.workspace.drive()
        val tree = activity.pickTree() ?: return ok().put("cancelled", true)
        val resolver = activity.contentResolver
        val root = DocumentsContract.buildDocumentUriUsingTree(tree, DocumentsContract.getTreeDocumentId(tree))
        var copied = 0
        var count = 0
        var truncated = false
        val errors = JSONArray()

        fun put(item: JSONObject, parent: Uri, depth: Int) {
            if (count >= 500) { truncated = true; return }
            val meta = if (item.optString("mimeType") == SHORTCUT) drive.resolve(item) else item
            val name = meta.optString("name")
            if (meta.optString("mimeType") == FOLDER) {
                if (depth >= 10) { truncated = true; return }
                val dir = DocumentsContract.createDocument(resolver, parent, DocumentsContract.Document.MIME_TYPE_DIR, safeName(name))
                    ?: throw DriveError("폴더를 만들지 못했습니다.")
                for (child in drive.list(meta.getString("id"))) put(child, dir, depth + 1)
                return
            }
            count++
            try {
                val fileName = safeName(name, EXPORTS[meta.optString("mimeType")]?.second ?: "")
                val local = s.workspace.localCopy(meta.getString("id"))   // 교실에서 고친 최신본이 있으면 그것을
                val source = local ?: File(File(s.dir, "save").apply { mkdirs() }, UUID.randomUUID().toString().take(8)).also {
                    drive.download(meta, it)
                }
                val doc = DocumentsContract.createDocument(resolver, parent, mimeOf(fileName), fileName)
                    ?: throw DriveError("저장하지 못했습니다.")
                resolver.openOutputStream(doc)?.use { out -> source.inputStream().use { it.copyTo(out) } }
                    ?: throw DriveError("저장하지 못했습니다.")
                if (local == null) source.delete()
                copied++
            } catch (e: Exception) {
                errors.put("$name: ${e.message}")
            }
        }

        for (i in 0 until items.length()) items.optJSONObject(i)?.let { put(it, root, 0) }
        return ok().put("copied", copied).put("errors", errors).put("truncated", truncated)
    }
}
