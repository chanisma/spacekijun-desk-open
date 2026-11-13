package kr.hs.kijun.classroom

import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.qrcode.QRCodeWriter
import com.google.zxing.qrcode.decoder.ErrorCorrectionLevel

/** QR 그림(SVG 문자열) — 화면 크기에 맞춰 늘어나도록 viewBox 만. Windows 판(segno)과 같은 모양·클래스 */
object Qr {
    /** 앱 화면(대화 상자)에 넣을 QR 그림 */
    fun bitmap(text: String, size: Int): android.graphics.Bitmap {
        val hints = mapOf(EncodeHintType.ERROR_CORRECTION to ErrorCorrectionLevel.M, EncodeHintType.MARGIN to 2)
        val m = QRCodeWriter().encode(text, BarcodeFormat.QR_CODE, size, size, hints)
        val pixels = IntArray(m.width * m.height) { i -> if (m.get(i % m.width, i / m.width)) 0xFF111111.toInt() else -1 }
        return android.graphics.Bitmap.createBitmap(pixels, m.width, m.height, android.graphics.Bitmap.Config.ARGB_8888)
    }

    fun svg(text: String): String {
        val hints = mapOf(EncodeHintType.ERROR_CORRECTION to ErrorCorrectionLevel.M, EncodeHintType.MARGIN to 2)
        val m = QRCodeWriter().encode(text, BarcodeFormat.QR_CODE, 0, 0, hints)
        val w = m.width
        val h = m.height
        val path = StringBuilder()
        for (y in 0 until h) {
            var x = 0
            while (x < w) {
                if (!m.get(x, y)) { x++; continue }
                val start = x
                while (x < w && m.get(x, y)) x++
                path.append("M").append(start).append(' ').append(y).append('h').append(x - start).append("v1h-").append(x - start).append('z')
            }
        }
        return "<svg xmlns=\"http://www.w3.org/2000/svg\" class=\"segno\" viewBox=\"0 0 $w $h\" shape-rendering=\"crispEdges\">" +
            "<rect width=\"$w\" height=\"$h\" fill=\"#fff\"/><path fill=\"#111\" d=\"$path\"/></svg>"
    }
}
