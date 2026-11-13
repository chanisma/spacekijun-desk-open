package kr.hs.kijun.classroom

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.MessageDigest
import java.util.UUID

/**
 * 교실 기기 드라이브 — 선생님 구글 드라이브를 앱 안 탐색기에서 일반 폴더처럼. Windows 판 app/core/classroom_drive.py 를 옮겼다.
 *
 *  · 탐색   폴더 목록(내 드라이브 · 공유 드라이브 · 공유 문서함)
 *  · 열기   수업 폴더(files/sessions/<수업>/drive)에 받아 이 기기의 앱(PowerPoint·PDF 보기 등)으로 연다.
 *           구글 문서·시트·슬라이드·그림은 docx·xlsx·pptx·pdf 로 바꿔 받는다.
 *  · 되올리기 연 파일이 바뀌면(크기·수정 시각이 바뀌고 2초 그대로면) 드라이브의 같은 파일에 새 판으로 올린다.
 *           구글 문서에서 바꿔 받은 파일은 같은 폴더에 «(교실에서 고침)» 새 파일로 올리고, 그 뒤로는 그것을 갱신한다.
 *           (안드로이드 앱에 따라 받은 파일을 읽기만 하고 «사본 저장»만 되는 것도 있다 — 그때는 되올릴 것이 없다)
 *  · 못 올린 파일 끝날 때 토큰이 끝나 못 올린 것은 기기에 남겼다가 같은 선생님이 다음에 연결하면 올리고 지운다.
 */
const val FOLDER = "application/vnd.google-apps.folder"
const val SHORTCUT = "application/vnd.google-apps.shortcut"
const val FULL_DRIVE = "https://www.googleapis.com/auth/drive"
private const val API = "https://www.googleapis.com/drive/v3"
private const val UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
private const val MAX_DOWNLOAD = 500L * 1024 * 1024
private const val LIST_FIELDS = "nextPageToken,files(id,name,mimeType,size,modifiedTime,shortcutDetails,capabilities/canEdit)"
const val UNSENT_FOLDER = "교실에서 올리지 못한 파일"
private const val SETTLE = 2.0

val EXPORTS = mapOf(
    "application/vnd.google-apps.document" to ("application/vnd.openxmlformats-officedocument.wordprocessingml.document" to ".docx"),
    "application/vnd.google-apps.spreadsheet" to ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" to ".xlsx"),
    "application/vnd.google-apps.presentation" to ("application/vnd.openxmlformats-officedocument.presentationml.presentation" to ".pptx"),
    "application/vnd.google-apps.drawing" to ("application/pdf" to ".pdf"),
)

private val MIMES = mapOf(
    "pdf" to "application/pdf", "docx" to EXPORTS.getValue("application/vnd.google-apps.document").first,
    "xlsx" to EXPORTS.getValue("application/vnd.google-apps.spreadsheet").first,
    "pptx" to EXPORTS.getValue("application/vnd.google-apps.presentation").first,
    "doc" to "application/msword", "xls" to "application/vnd.ms-excel", "ppt" to "application/vnd.ms-powerpoint",
    "hwp" to "application/x-hwp", "hwpx" to "application/hwp+zip", "txt" to "text/plain", "csv" to "text/csv",
    "png" to "image/png", "jpg" to "image/jpeg", "jpeg" to "image/jpeg", "gif" to "image/gif", "webp" to "image/webp",
    "mp4" to "video/mp4", "mp3" to "audio/mpeg", "m4a" to "audio/mp4", "zip" to "application/zip",
)

fun mimeOf(name: String): String = MIMES[name.substringAfterLast('.', "").lowercase()] ?: "application/octet-stream"

class DriveError(message: String, val auth: Boolean = false) : Exception(message)

fun safeName(name: String, ext: String = ""): String {
    var stem = name.filter { it.code >= 32 }.map { if (it in "<>:\"/\\|?*") '_' else it }.joinToString("").trim(' ', '.')
    if (stem.isEmpty()) stem = "파일"
    if (ext.isNotEmpty() && !stem.lowercase().endsWith(ext)) stem += ext
    val dot = stem.lastIndexOf('.').takeIf { it > 0 } ?: stem.length
    val root = stem.substring(0, dot)
    val suffix = stem.substring(dot)
    return root.take(120 - suffix.length) + suffix
}

private fun q(value: String) = value.replace("\\", "\\\\").replace("'", "\\'")
private fun enc(value: String) = URLEncoder.encode(value, "UTF-8").replace("+", "%20")
private fun query(params: Map<String, String>) = params.entries.joinToString("&") { "${enc(it.key)}=${enc(it.value)}" }

/** HTTP 한 번. 시험에서는 바꿔 끼운다 */
fun interface DriveHttp {
    /** → (상태, 응답 머리글 Location). 본문은 sink(상태, 스트림)으로 */
    fun request(url: String, method: String, headers: Map<String, String>, body: ByteArray?, sink: (Int, InputStream) -> Unit): Pair<Int, String?>
}

object UrlDriveHttp : DriveHttp {
    override fun request(url: String, method: String, headers: Map<String, String>, body: ByteArray?,
                         sink: (Int, InputStream) -> Unit): Pair<Int, String?> {
        val conn = URL(url).openConnection() as HttpURLConnection
        try {
            // HttpURLConnection 은 PATCH 를 못 보낸다 — 구글 API 는 덮어쓰기 머리글을 받는다
            if (method == "PATCH") {
                conn.requestMethod = "POST"
                conn.setRequestProperty("X-HTTP-Method-Override", "PATCH")
            } else {
                conn.requestMethod = method
            }
            conn.connectTimeout = 20_000
            conn.readTimeout = 120_000
            for ((k, v) in headers) conn.setRequestProperty(k, v)
            if (body != null) {
                conn.doOutput = true
                conn.setFixedLengthStreamingMode(body.size)
                conn.outputStream.use { it.write(body) }
            }
            val status = conn.responseCode
            val stream = if (status in 200..299) conn.inputStream else conn.errorStream
            stream?.use { sink(status, it) }
            return status to conn.getHeaderField("Location")
        } finally {
            conn.disconnect()
        }
    }
}

class Drive(private val token: String, private val http: DriveHttp = UrlDriveHttp) {

    private fun open(url: String, method: String = "GET", body: ByteArray? = null,
                     headers: Map<String, String> = emptyMap(), sink: (InputStream) -> Unit = { it.readBytes() }): String? {
        var errorBody = ""
        val (status, location) = try {
            http.request(url, method, mapOf("Authorization" to "Bearer $token") + headers, body) { code, stream ->
                if (code in 200..299) sink(stream) else errorBody = stream.readBytes().toString(Charsets.UTF_8).take(4000)
            }
        } catch (e: DriveError) {
            throw e
        } catch (e: IOException) {
            throw DriveError("인터넷 연결을 확인해 주세요.")
        }
        if (status in 200..299) return location
        when (status) {
            401 -> throw DriveError("드라이브 연결 시간이 끝났습니다. QR 로 다시 연결해 주세요.", auth = true)
            403 -> {
                val lower = errorBody.lowercase()
                if ("insufficient" in lower || "scope" in lower) {
                    throw DriveError("드라이브 전체 권한이 없습니다. QR 승인 때 구글 창에서 허용해 주세요.", auth = true)
                }
                throw DriveError("이 파일·폴더에 대한 권한이 없습니다.")
            }
            404 -> throw DriveError("드라이브에서 찾지 못했습니다(지워졌거나 권한 없음).")
            else -> throw DriveError("드라이브 요청이 실패했습니다($status).")
        }
    }

    private fun json(url: String, method: String = "GET", body: JSONObject? = null): JSONObject {
        var text = ""
        val headers = if (body != null) mapOf("Content-Type" to "application/json; charset=UTF-8") else emptyMap()
        open(url, method, body?.toString()?.toByteArray(), headers) { text = it.readBytes().toString(Charsets.UTF_8) }
        return if (text.isBlank()) JSONObject() else JSONObject(text)
    }

    /** 폴더 안(휴지통 제외). folderId='shared' = «공유 문서함» */
    fun list(folderId: String = "root", driveId: String? = null): List<JSONObject> {
        val params = linkedMapOf(
            "q" to if (folderId == "shared") "sharedWithMe = true and trashed = false" else "'${q(folderId)}' in parents and trashed = false",
            "fields" to LIST_FIELDS, "pageSize" to "200", "orderBy" to "folder,name_natural",
            "supportsAllDrives" to "true", "includeItemsFromAllDrives" to "true",
        )
        if (!driveId.isNullOrEmpty()) {
            params["corpora"] = "drive"
            params["driveId"] = driveId
        }
        val items = mutableListOf<JSONObject>()
        var page: String? = null
        repeat(10) {                                   // 2,000개까지
            if (page != null) params["pageToken"] = page!!
            val result = json("$API/files?" + query(params))
            val files = result.optJSONArray("files") ?: JSONArray()
            for (i in 0 until files.length()) items += files.getJSONObject(i)
            page = result.optString("nextPageToken").ifEmpty { null }
            if (page == null) return items
        }
        return items
    }

    fun sharedDrives(): List<JSONObject> {
        val drives = json("$API/drives?" + query(mapOf("pageSize" to "100", "fields" to "drives(id,name)"))).optJSONArray("drives") ?: JSONArray()
        return (0 until drives.length()).map { drives.getJSONObject(it) }
    }

    fun meta(fileId: String): JSONObject = json("$API/files/${enc(fileId)}?" +
        query(mapOf("fields" to "id,name,mimeType,size,modifiedTime,parents,shortcutDetails,driveId", "supportsAllDrives" to "true")))

    /** 바로가기면 원본으로 */
    fun resolve(meta: JSONObject): JSONObject {
        if (meta.optString("mimeType") != SHORTCUT) return meta
        val target = meta.optJSONObject("shortcutDetails")?.optString("targetId").orEmpty()
        if (target.isEmpty()) throw DriveError("바로가기의 원본을 찾지 못했습니다.")
        return meta(target)
    }

    private fun save(url: String, dest: File) {
        val part = File(dest.path + ".part")
        open(url) { stream ->
            part.outputStream().use { out ->
                val buffer = ByteArray(1 shl 16)
                var written = 0L
                while (true) {
                    val n = stream.read(buffer)
                    if (n < 0) break
                    written += n
                    if (written > MAX_DOWNLOAD) throw DriveError("파일이 너무 큽니다(500MB 넘음).")
                    out.write(buffer, 0, n)
                }
            }
        }
        if (!part.renameTo(dest)) throw DriveError("파일을 저장하지 못했습니다.")
    }

    fun download(meta: JSONObject, dest: File) {
        val mime = meta.optString("mimeType")
        val id = enc(meta.getString("id"))
        when {
            mime in EXPORTS -> save("$API/files/$id/export?" + query(mapOf("mimeType" to EXPORTS.getValue(mime).first)), dest)
            mime.startsWith("application/vnd.google-apps.") -> throw DriveError("이 형식(구글 설문·사이트 등)은 교실 기기에서 열 수 없습니다.")
            meta.optString("size").toLongOrNull()?.let { it > MAX_DOWNLOAD } == true -> throw DriveError("파일이 너무 큽니다(500MB 넘음).")
            else -> save("$API/files/$id?alt=media&supportsAllDrives=true", dest)
        }
    }

    private fun resumable(url: String, method: String, metadata: JSONObject, file: File): JSONObject {
        val mime = mimeOf(file.name)
        val location = open(url, method, metadata.toString().toByteArray(), mapOf(
            "Content-Type" to "application/json; charset=UTF-8",
            "X-Upload-Content-Type" to mime, "X-Upload-Content-Length" to file.length().toString(),
        )) ?: throw DriveError("드라이브에 올리지 못했습니다.")
        var text = ""
        open(location, "PUT", file.readBytes(), mapOf("Content-Type" to mime)) { text = it.readBytes().toString(Charsets.UTF_8) }
        return if (text.isBlank()) JSONObject() else JSONObject(text)
    }

    fun uploadNew(file: File, parent: String, name: String = file.name): JSONObject =
        resumable("$UPLOAD?uploadType=resumable&supportsAllDrives=true&fields=id,name,mimeType,modifiedTime", "POST",
            JSONObject().put("name", name).put("parents", JSONArray().put(parent)), file)

    fun updateContent(fileId: String, file: File): JSONObject =
        resumable("$UPLOAD/${enc(fileId)}?uploadType=resumable&supportsAllDrives=true&fields=id,name,modifiedTime", "PATCH", JSONObject(), file)

    fun createFolder(name: String, parent: String): JSONObject =
        json("$API/files?supportsAllDrives=true&fields=id,name,mimeType", "POST",
            JSONObject().put("name", name).put("mimeType", FOLDER).put("parents", JSONArray().put(parent)))

    fun findOrCreateFolder(name: String, parent: String = "root"): String {
        val found = json("$API/files?" + query(mapOf(
            "q" to "name = '${q(name)}' and mimeType = '$FOLDER' and '$parent' in parents and trashed = false",
            "fields" to "files(id)", "pageSize" to "1"))).optJSONArray("files")
        return if (found != null && found.length() > 0) found.getJSONObject(0).getString("id") else createFolder(name, parent).getString("id")
    }
}

/** 파일을 이 기기의 앱으로 연다(MainActivity — FileProvider). 열 앱이 없으면 DriveError */
fun interface FileLauncher {
    fun launch(file: File, mime: String)
}

/**
 * 이번 수업에 연 드라이브 파일들 — 받아 두고, 바뀌면 되올린다. token() 은 지금 쓸 수 있는 토큰(없으면 null).
 */
class Workspace(
    private val folder: File,
    private val token: () -> String?,
    private val launcher: FileLauncher,
    private val http: DriveHttp = UrlDriveHttp,
    private val clock: () -> Double = { System.currentTimeMillis() / 1000.0 },
) {
    class Entry(
        val key: String, val sourceId: String, val name: String, val exported: Boolean, var uploadId: String?,
        val parent: String, var synced: Pair<Long, Long>?, var seen: Pair<Long, Long>?, var seenAt: Double,
        var state: String = "synced", var message: String = "", var uploadedAt: Double? = null,
    )

    private val entries = LinkedHashMap<File, Entry>()

    fun drive(): Drive = Drive(token() ?: throw DriveError("드라이브가 연결되어 있지 않습니다. QR 로 다시 연결해 주세요.", auth = true), http)

    private fun stamp(file: File): Pair<Long, Long>? = if (file.exists()) file.length() to file.lastModified() else null

    /** 파일을 받아 연다. 이미 받은 파일이면 그대로 연다(고친 내용을 덮지 않는다) */
    fun open(fileId: String): File {
        synchronized(entries) {
            entries.entries.firstOrNull { it.value.sourceId == fileId && it.key.exists() }?.let {
                launcher.launch(it.key, mimeOf(it.key.name))
                return it.key
            }
        }
        val drive = drive()
        val meta = drive.resolve(drive.meta(fileId))
        if (meta.optString("mimeType") == FOLDER) throw DriveError("폴더입니다.")
        val exported = meta.optString("mimeType") in EXPORTS
        val ext = if (exported) EXPORTS.getValue(meta.optString("mimeType")).second else ""
        val dir = File(folder, UUID.randomUUID().toString().take(8)).apply { mkdirs() }
        val file = File(dir, safeName(meta.optString("name"), ext))
        drive.download(meta, file)
        val parents = meta.optJSONArray("parents")
        synchronized(entries) {
            entries[file] = Entry(
                key = UUID.randomUUID().toString().take(10), sourceId = meta.getString("id"), name = file.name,
                exported = exported, uploadId = if (exported) null else meta.getString("id"),
                parent = if (parents != null && parents.length() > 0) parents.getString(0) else "root",
                synced = stamp(file), seen = stamp(file), seenAt = clock(),
            )
        }
        launcher.launch(file, mimeOf(file.name))
        return file
    }

    /** 바뀐 파일을 올린다. final=true 면 기다리지 않고 지금 상태로. 올린 개수 */
    fun sync(final: Boolean = false): Int {
        var sent = 0
        val list = synchronized(entries) { entries.toList() }
        for ((file, entry) in list) {
            val now = stamp(file)
            if (now == null || now == entry.synced) continue
            if (now != entry.seen) {
                entry.seen = now
                entry.seenAt = clock()
                if (!final) { entry.state = "pending"; continue }
            }
            if (!final && clock() - entry.seenAt < SETTLE) continue
            try {
                entry.state = "uploading"
                val drive = drive()
                if (entry.uploadId != null) {
                    drive.updateContent(entry.uploadId!!, file)
                } else {
                    val dot = entry.name.lastIndexOf('.').takeIf { it > 0 } ?: entry.name.length
                    val made = drive.uploadNew(file, entry.parent, entry.name.substring(0, dot) + " (교실에서 고침)" + entry.name.substring(dot))
                    entry.uploadId = made.optString("id").ifEmpty { null }
                }
                entry.synced = now
                entry.state = "synced"
                entry.message = ""
                entry.uploadedAt = clock()
                sent++
            } catch (e: DriveError) {
                entry.state = "failed"
                entry.message = e.message.orEmpty()
            } catch (e: IOException) {
                entry.state = "pending"
                entry.message = "파일이 아직 쓰이는 중입니다."
            }
        }
        return sent
    }

    fun unsynced(): List<File> = synchronized(entries) { entries.filter { stamp(it.key).let { s -> s != null && s != it.value.synced } }.keys.toList() }

    fun snapshot(): JSONArray = synchronized(entries) {
        JSONArray().also { out ->
            for (e in entries.values) out.put(JSONObject().put("key", e.key).put("source_id", e.sourceId)
                .put("upload_id", e.uploadId ?: JSONObject.NULL).put("exported", e.exported).put("name", e.name)
                .put("state", e.state).put("message", e.message).put("uploaded_at", e.uploadedAt ?: JSONObject.NULL))
        }
    }

    /** 이 수업에서 연 파일이면 그 로컬본(교실에서 고친 최신본) */
    fun localCopy(fileId: String): File? = synchronized(entries) {
        entries.entries.firstOrNull { (fileId == it.value.sourceId || fileId == it.value.uploadId) && it.key.exists() }?.key
    }

    fun entryFile(key: String): File? = synchronized(entries) { entries.entries.firstOrNull { it.value.key == key }?.key }

    fun stashUnsent(box: UnsentBox, email: String): Int {
        val files = unsynced()
        if (files.isEmpty() || email.isEmpty()) return 0
        val dir = box.dir(email).apply { mkdirs() }
        for (file in files) {
            val name = synchronized(entries) { entries[file]?.name } ?: file.name
            runCatching { file.copyTo(File(dir, UUID.randomUUID().toString().take(8) + "_" + name)) }
        }
        return files.size
    }
}

/** 수업이 끝날 때 못 올린 파일 — files/unsent/<선생님 해시>/ */
class UnsentBox(private val root: File) {
    fun dir(email: String): File {
        val digest = MessageDigest.getInstance("SHA-256").digest(email.trim().lowercase().toByteArray())
        return File(root, digest.joinToString("") { "%02x".format(it) }.take(24))
    }

    fun has(email: String) = email.isNotEmpty() && (dir(email).listFiles()?.isNotEmpty() == true)

    /** 지난 수업에 못 올린 파일을 «교실에서 올리지 못한 파일» 폴더로 올리고 지운다 */
    fun send(drive: Drive, email: String): Int {
        val files = dir(email).listFiles()?.sortedBy { it.name } ?: return 0
        if (files.isEmpty()) return 0
        val folder = drive.findOrCreateFolder(UNSENT_FOLDER)
        var sent = 0
        for (file in files) {
            drive.uploadNew(file, folder, file.name.substringAfter('_'))
            file.delete()
            sent++
        }
        return sent
    }
}
